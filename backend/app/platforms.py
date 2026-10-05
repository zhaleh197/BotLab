"""Bale / Telegram Bot API connector (Bale's API is Telegram-compatible)."""
import copy
import threading
import time
from typing import Optional

import httpx
from sqlalchemy.orm.attributes import flag_modified

from .config import PUBLIC_URL
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


def send(platform: str, token: str, out: Out):
    payload = {"chat_id": out.to, "text": out.text}
    if out.buttons:
        payload["reply_markup"] = {"keyboard": [[{"text": b} for b in row] for row in out.buttons],
                                   "resize_keyboard": True}
    try:
        call(platform, token, "sendMessage", payload)
    except PlatformError as e:
        print(f"[send] {platform} chat={out.to}: {e}")


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


def process_update(bot_id: int, update: dict) -> list[Out]:
    """Run one incoming platform update through the live version and send the replies."""
    msg = update.get("message") or update.get("edited_message")
    if not msg or "text" not in msg or msg.get("chat", {}).get("type", "private") != "private":
        return []
    chat_id = str(msg["chat"]["id"])
    name = (msg.get("from") or {}).get("first_name", "")
    with lock_for(bot_id), SessionLocal() as db:
        bot = db.get(Bot, bot_id)
        if not bot or not bot.live_version_id:
            return []
        v = db.get(BotVersion, bot.live_version_id)
        row = load_data(db, bot_id, "live")
        data = copy.deepcopy(row.data or {})
        outs = Engine(BotSpec.model_validate(v.spec), data).handle(chat_id, msg["text"], name=name)
        save_data(row, data)
        db.commit()
        platform, token = bot.platform, bot.token
    for o in outs:
        send(platform, token, o)
    return outs


# ---------------------------------------------------------------------------
# connect / disconnect
# ---------------------------------------------------------------------------
_pollers: dict[int, threading.Event] = {}


def connect(bot: Bot) -> str:
    """Point the platform at us. Returns the mode used ('webhook' or 'polling')."""
    if PUBLIC_URL:
        url = f"{PUBLIC_URL}/hook/{bot.id}/{bot.webhook_secret}"
        call(bot.platform, bot.token, "setWebhook", {"url": url})
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
    """On startup: re-register live bots (needed for polling mode and after redeploys)."""
    with SessionLocal() as db:
        bots = db.query(Bot).filter(Bot.live_version_id.isnot(None)).all()
    for b in bots:
        try:
            connect(b)
        except Exception as e:
            print(f"[resume] bot {b.id}: {e}")
        time.sleep(0.2)
