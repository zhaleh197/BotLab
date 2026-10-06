"""Platform-level payment flow with a fake Bale API: invoice in rials -> pre-checkout -> successful_payment."""
import copy
import os
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
os.environ["DATABASE_URL"] = "sqlite:///" + os.path.join(tempfile.mkdtemp(), "p.db")

from app import platforms  # noqa: E402
from app.db import Bot, BotVersion, SessionLocal, User, init_db  # noqa: E402
from app.spec import EXAMPLE_WORKSHOP  # noqa: E402

sent = []


def fake_call(platform, token, method, payload=None, timeout=20):
    sent.append((method, payload or {}))
    return {}


platforms.call = fake_call


def msg(chat, text=None, **extra):
    m = {"chat": {"id": chat, "type": "private"}, "from": {"id": chat, "first_name": "Ali"}, **extra}
    if text is not None:
        m["text"] = text
    return {"message": m}


def main():
    init_db()
    spec = copy.deepcopy(EXAMPLE_WORKSHOP)
    spec["workshop"]["require_payment"] = True
    with SessionLocal() as db:
        u = User(email="a@b.c", name="a", password_hash="x")
        db.add(u)
        db.commit()
        bot = Bot(owner_id=u.id, platform="bale", token="T", payment_token="WALLET-TEST-1111111111111111",
                  webhook_secret="s")
        db.add(bot)
        db.commit()
        v = BotVersion(bot_id=bot.id, number=1, spec=spec, tests=[], test_report={})
        db.add(v)
        db.commit()
        bot.live_version_id = v.id
        db.commit()
        bid = bot.id

    for t in ["/start", "📝 آبرنگ مقدماتی", "علی رضایی", "09121234567", "✅ تأیید"]:
        platforms.process_update(bid, msg(42, t))
    inv = [p for m, p in sent if m == "sendInvoice"]
    assert inv, sent[-3:]
    inv = inv[-1]
    assert inv["currency"] == "IRR" and inv["prices"][0]["amount"] == 4_500_000, inv  # 450,000 toman = 4.5M rial
    assert inv["provider_token"].startswith("WALLET-TEST"), inv

    platforms.process_update(bid, {"pre_checkout_query": {"id": "q1", "from": {"id": 42},
                                                          "invoice_payload": inv["payload"]}})
    ans = [p for m, p in sent if m == "answerPreCheckoutQuery"][-1]
    assert ans["ok"] is True, ans

    # someone else trying to pay the same invoice is refused
    platforms.process_update(bid, {"pre_checkout_query": {"id": "q2", "from": {"id": 99},
                                                          "invoice_payload": inv["payload"]}})
    ans = [p for m, p in sent if m == "answerPreCheckoutQuery"][-1]
    assert ans["ok"] is False and ans["error_message"], ans

    platforms.process_update(bid, msg(42, successful_payment={
        "currency": "IRR", "total_amount": 4_500_000, "invoice_payload": inv["payload"],
        "telegram_payment_charge_id": "tg1", "provider_payment_charge_id": "BALE-778899"}))
    last = [p for m, p in sent if m == "sendMessage"][-1]
    assert "قطعی شد" in last["text"] and "BALE-778899" in last["text"], last
    print("PAYMENTS OK")


if __name__ == "__main__":
    main()
