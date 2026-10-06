"""Bale / Telegram Bot API connector (Bale's API is Telegram-compatible)."""
import copy
import threading
import time
from typing import Optional

import httpx
from sqlalchemy.orm.attributes import flag_modified

from .config import PUBLIC_URL, TELEGRAM_PAYMENT_CURRENCY, TOMAN_PER_USD
from .db import Bot, BotData, BotVersion, SessionLocal
from .engine import Engine, Out
from .spec import BotSpec

API_BASE = {"bale": "https://tapi.bale.ai/bot{token}/", "telegram": "https://api.telegram.org/bot{token}/"}
_locks: dict[int, threading.Lock] = {}
_locks_guard = threading.Lock()


class PlatformError(Exception):
    pass


def lock_for(bot_id: int) -> threading.Lock:
    with _locks_guard:
        return _locks.setdefault(bot_id, threading.Lock())


def call(platform: str, token: str, method: str, payload: Optional[dict] = None, timeout: float = 20) -> dict:
    url = API_BASE[platform].format(token=token) + method
    try:
        r = httpx.post(url, json=payload or {}, timeout=timeout)
        data = r.json()
    except Exception as e:
        raise PlatformError(f"عدم دسترسی به سرور {'بله' if platform == 'bale' else 'تلگرام'}: {e}")
    if not data.get("ok"):
        raise PlatformError(data.get("description") or f"خطای {r.status_code}")
    return data.get("result")


def platform_amount(platform: str, amount: int, currency_label: str) -> tuple[str, int]:
    """Convert a spec price into (currency, smallest-unit amount) for the platform's invoice.

    Bale charges in rials. Telegram's payment providers have no rial, so for Telegram (demo/test) the toman
    price is converted to TELEGRAM_PAYMENT_CURRENCY cents at TOMAN_PER_USD.
    """
    rial = amount * 10 if "تومان" in currency_label else amount
    if platform == "bale":
        return "IRR", rial
    return TELEGRAM_PAYMENT_CURRENCY, max(100, round(rial / 10 / TOMAN_PER_USD * 100))


def send(bot: dict, out: Out, currency_label: str = "تومان"):
    """bot = {"platform", "token", "payment_token"}"""
    platform, token = bot["platform"], bot["token"]
    payload = {"chat_id": out.to, "text": out.text}
    if out.buttons:
        payload["reply_markup"] = {"keyboard": [[{"text": b} for b in row] for row in out.buttons],
                                   "resize_keyboard": True}
    try:
        call(platform, token, "sendMessage", payload)
    except PlatformError as e:
        print(f"[send] {platform} chat={out.to}: {e}")
    if not out.invoice:
        return
    if not bot.get("payment_token"):
        try:
            call(platform, token, "sendMessage", {"chat_id": out.to, "text":
                 "⚠️ پرداخت آنلاین هنوز توسط کسب‌وکار فعال نشده است. لطفاً با پشتیبانی تماس بگیرید."})
        except PlatformError:
            pass
        return
    inv = out.invoice
    currency, amount = platform_amount(platform, inv["amount"], currency_label)
    try:
        call(platform, token, "sendInvoice", {
            "chat_id": out.to, "title": inv["title"], "description": inv["description"],
            "payload": inv["payload"], "provider_token": bot["payment_token"], "currency": currency,
            "prices": [{"label": inv["title"], "amount": amount}]})
    except PlatformError as e:
        print(f"[invoice] {platform} chat={out.to}: {e}")
        try:
            call(platform, token, "sendMessage", {"chat_id": out.to, "text": f"⚠️ صدور صورت‌حساب ناموفق بود: {e}"})
        except PlatformError:
            pass


def load_data(db, bot_id: int, scope: str) -> BotData:
    row = db.query(BotData).filter(BotData.bot_id == bot_id, BotData.scope == scope).first()
    if not row:
        row = BotData(bot_id=bot_id, scope=scope, data={})
        db.add(row)
        db.flush()
    return row


def save_data(row: BotData, data: dict):
    row.data = data
    flag_modified(row, "data")


def _bot_info(bot: Bot) -> dict:
    return {"platform": bot.platform, "token": bot.token, "payment_token": bot.payment_token or ""}


def process_update(bot_id: int, update: dict) -> list[Out]:
    """Run one incoming platform update (message, payment check or payment receipt) through the live version."""
    pcq = update.get("pre_checkout_query")
    msg = update.get("message") or update.get("edited_message")
    if not pcq:
        if not msg or msg.get("chat", {}).get("type", "private") != "private":
            return []
        if "text" not in msg and "successful_payment" not in msg:
            return []
    answer = None
    with lock_for(bot_id), SessionLocal() as db:
        bot = db.get(Bot, bot_id)
        if not bot or not bot.live_version_id:
            return []
        spec = BotSpec.model_validate(db.get(BotVersion, bot.live_version_id).spec)
        row = load_data(db, bot_id, "live")
        data = copy.deepcopy(row.data or {})
        eng = Engine(spec, data)
        if pcq:
            # The platform asks whether it may charge the user; must be answered within 10 seconds.
            err, outs = eng.pre_checkout(str(pcq["from"]["id"]), pcq.get("invoice_payload", ""))
            answer = {"pre_checkout_query_id": pcq["id"], "ok": err is None}
            if err:
                answer["error_message"] = err
        elif "successful_payment" in msg:
            sp = msg["successful_payment"]
            charge = sp.get("provider_payment_charge_id") or sp.get("telegram_payment_charge_id") or ""
            outs = eng.payment_success(str(msg["chat"]["id"]), sp.get("invoice_payload", ""), str(charge),
                                       sp.get("total_amount", 0))
        else:
            name = (msg.get("from") or {}).get("first_name", "")
            outs = eng.handle(str(msg["chat"]["id"]), msg["text"], name=name)
        save_data(row, data)
        db.commit()
        info = _bot_info(bot)
    if answer:
        try:
            call(info["platform"], info["token"], "answerPreCheckoutQuery", answer, timeout=8)
        except PlatformError as e:
            print(f"[pre_checkout] bot {bot_id}: {e}")
    for o in outs:
        send(info, o, spec.currency)
    return outs


def sweep_all():
    """Release expired payment holds of live bots and notify the affected users."""
    with SessionLocal() as db:
        ids = [b.id for b in db.query(Bot).filter(Bot.live_version_id.isnot(None)).all()]
    for bot_id in ids:
        try:
            with lock_for(bot_id), SessionLocal() as db:
                bot = db.get(Bot, bot_id)
                spec = BotSpec.model_validate(db.get(BotVersion, bot.live_version_id).spec)
                cfg = spec.workshop or spec.order
                if not cfg.require_payment:
                    continue
                row = load_data(db, bot_id, "live")
                data = copy.deepcopy(row.data or {})
                outs = Engine(spec, data).sweep()
                if not outs:
                    continue
                save_data(row, data)
                db.commit()
                info = _bot_info(bot)
            for o in outs:
                send(info, o, spec.currency)
        except Exception as e:
            print(f"[sweep] bot {bot_id}: {e}")


def _sweep_loop():
    while True:
        time.sleep(60)
        sweep_all()


def reachability() -> dict:
    """Can this server reach the messenger APIs? (Bale may be unreachable from outside Iran.)"""
    out = {}
    for name, base in API_BASE.items():
        try:
            r = httpx.get(base.format(token="0:check") + "getMe", timeout=8)
            out[name] = {"reachable": True, "status": r.status_code}
        except Exception as e:
            out[name] = {"reachable": False, "error": str(e)[:200]}
    return out


# ---------------------------------------------------------------------------
# connect / disconnect
# ---------------------------------------------------------------------------
_pollers: dict[int, threading.Event] = {}


def connect(bot: Bot) -> str:
    """Point the platform at us. Returns the mode used ('webhook' or 'polling')."""
    if PUBLIC_URL:
        url = f"{PUBLIC_URL}/hook/{bot.id}/{bot.webhook_secret}"
        call(bot.platform, bot.token, "setWebhook",
             {"url": url, "allowed_updates": ["message", "pre_checkout_query"]})
        return "webhook"
    try:
        call(bot.platform, bot.token, "deleteWebhook", {})
    except PlatformError:
        pass
    start_polling(bot.id)
    return "polling"


def disconnect(bot: Bot):
    stop_polling(bot.id)
    if bot.token:
        try:
            call(bot.platform, bot.token, "deleteWebhook", {})
        except PlatformError:
            pass


def start_polling(bot_id: int):
    if bot_id in _pollers:
        return
    stop = threading.Event()
    _pollers[bot_id] = stop
    threading.Thread(target=_poll_loop, args=(bot_id, stop), daemon=True).start()


def stop_polling(bot_id: int):
    ev = _pollers.pop(bot_id, None)
    if ev:
        ev.set()


def _poll_loop(bot_id: int, stop: threading.Event):
    offset = 0
    while not stop.is_set():
        with SessionLocal() as db:
            bot = db.get(Bot, bot_id)
            if not bot or not bot.live_version_id or not bot.token:
                break
            platform, token = bot.platform, bot.token
        try:
            updates = call(platform, token, "getUpdates", {"offset": offset, "timeout": 20}, timeout=30) or []
        except PlatformError as e:
            print(f"[poll] bot {bot_id}: {e}")
            stop.wait(5)
            continue
        for up in updates:
            offset = max(offset, up["update_id"] + 1)
            try:
                process_update(bot_id, up)
            except Exception as e:
                print(f"[poll] bot {bot_id} update failed: {e}")
    _pollers.pop(bot_id, None)


def resume_all():
    """On startup: re-register live bots (needed for polling mode and after redeploys) and start the sweeper."""
    threading.Thread(target=_sweep_loop, daemon=True).start()
    with SessionLocal() as db:
        bots = db.query(Bot).filter(Bot.live_version_id.isnot(None)).all()
    for b in bots:
        try:
            connect(b)
        except Exception as e:
            print(f"[resume] bot {b.id}: {e}")
        time.sleep(0.2)
