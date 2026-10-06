import copy
import re
import secrets

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel, Field

from . import agent, platforms
from .auth import check_password, current_user, hash_password, make_token
from .config import LLM_API_KEY, LLM_MODEL, PUBLIC_URL
from .db import Bot, BotData, BotVersion, Message, SessionLocal, User
from .engine import Engine, Out
from .spec import BotSpec

router = APIRouter()


# ----------------------------- auth -----------------------------
class RegisterIn(BaseModel):
    name: str = Field(min_length=1, max_length=120)
    email: str = Field(min_length=3, max_length=200)
    password: str = Field(min_length=6, max_length=100)


class LoginIn(BaseModel):
    email: str
    password: str


def _user_out(u: User):
    return {"id": u.id, "name": u.name, "email": u.email}


@router.post("/api/auth/register")
def register(body: RegisterIn):
    email = body.email.strip().lower()
    if not re.fullmatch(r"[^@\s]+@[^@\s]+\.[^@\s]+", email):
        raise HTTPException(400, "ایمیل معتبر نیست")
    with SessionLocal() as db:
        if db.query(User).filter(User.email == email).first():
            raise HTTPException(400, "این ایمیل قبلاً ثبت شده است؛ وارد شوید")
        u = User(email=email, name=body.name.strip(), password_hash=hash_password(body.password))
        db.add(u)
        db.commit()
        return {"token": make_token(u.id), "user": _user_out(u)}


@router.post("/api/auth/login")
def login(body: LoginIn):
    with SessionLocal() as db:
        u = db.query(User).filter(User.email == body.email.strip().lower()).first()
    if not u or not check_password(body.password, u.password_hash):
        raise HTTPException(400, "ایمیل یا رمز عبور اشتباه است")
    return {"token": make_token(u.id), "user": _user_out(u)}


@router.get("/api/me")
def me(user: User = Depends(current_user)):
    return _user_out(user)


@router.get("/api/health")
def health():
    return {"ok": True, "llm_configured": bool(LLM_API_KEY), "model": LLM_MODEL,
            "mode": "webhook" if PUBLIC_URL else "polling"}


@router.get("/api/health/platforms")
def health_platforms():
    """Whether this server can reach the Bale and Telegram APIs."""
    return platforms.reachability()


# ----------------------------- bots -----------------------------
def _own(db, bot_id: int, user: User) -> Bot:
    bot = db.get(Bot, bot_id)
    if not bot or bot.owner_id != user.id:
        raise HTTPException(404, "بات یافت نشد")
    return bot


def _version_brief(v: BotVersion, live_id):
    rep = v.test_report or {}
    return {"id": v.id, "number": v.number, "created_at": v.created_at.isoformat(), "change_note": v.change_note,
            "passed": rep.get("passed", 0), "total": rep.get("total", 0), "is_live": v.id == live_id}


def _bot_out(db, bot: Bot, full=False):
    versions = db.query(BotVersion).filter(BotVersion.bot_id == bot.id).order_by(BotVersion.number.desc()).all()
    live = next((v for v in versions if v.id == bot.live_version_id), None)
    out = {
        "id": bot.id, "name": bot.name, "template": bot.template, "platform": bot.platform,
        "bot_username": bot.bot_username, "has_token": bool(bot.token),
        "token_hint": (bot.token[:6] + "…" + bot.token[-4:]) if bot.token else "",
        "has_payment_token": bool(bot.payment_token),
        "payment_hint": (bot.payment_token[:8] + "…" + bot.payment_token[-4:]) if bot.payment_token else "",
        "payment_test": bool(bot.payment_token) and ("TEST" in bot.payment_token.upper()),
        "agent_status": bot.agent_status, "created_at": bot.created_at.isoformat(),
        "live_version": live.number if live else None,
        "latest_version": versions[0].number if versions else None,
    }
    if full:
        out["versions"] = [_version_brief(v, bot.live_version_id) for v in versions]
        out["requirements"] = bot.requirements
    return out


@router.get("/api/bots")
def list_bots(user: User = Depends(current_user)):
    with SessionLocal() as db:
        bots = db.query(Bot).filter(Bot.owner_id == user.id).order_by(Bot.id.desc()).all()
        return [_bot_out(db, b) for b in bots]


class CreateBotIn(BaseModel):
    message: str = ""


@router.post("/api/bots")
def create_bot(body: CreateBotIn, user: User = Depends(current_user)):
    with SessionLocal() as db:
        bot = Bot(owner_id=user.id, webhook_secret=secrets.token_hex(16))
        db.add(bot)
        db.commit()
        bot_id = bot.id
    if body.message.strip():
        agent.start_turn(bot_id, body.message.strip())
    return {"id": bot_id}


@router.get("/api/bots/{bot_id}")
def get_bot(bot_id: int, user: User = Depends(current_user)):
    with SessionLocal() as db:
        return _bot_out(db, _own(db, bot_id, user), full=True)


@router.delete("/api/bots/{bot_id}")
def delete_bot(bot_id: int, user: User = Depends(current_user)):
    with SessionLocal() as db:
        bot = _own(db, bot_id, user)
        platforms.disconnect(bot)
        for model in (Message, BotVersion, BotData):
            db.query(model).filter(model.bot_id == bot_id).delete()
        db.delete(bot)
        db.commit()
    return {"ok": True}


@router.get("/api/bots/{bot_id}/messages")
def get_messages(bot_id: int, user: User = Depends(current_user)):
    with SessionLocal() as db:
        bot = _own(db, bot_id, user)
        msgs = db.query(Message).filter(Message.bot_id == bot_id).order_by(Message.id).all()
        return {"agent_status": bot.agent_status,
                "messages": [{"id": m.id, "role": m.role, "content": m.content, "meta": m.meta or {},
                              "created_at": m.created_at.isoformat()} for m in msgs]}


class MessageIn(BaseModel):
    text: str = Field(min_length=1, max_length=4000)


@router.post("/api/bots/{bot_id}/messages")
def post_message(bot_id: int, body: MessageIn, user: User = Depends(current_user)):
    with SessionLocal() as db:
        _own(db, bot_id, user)
    if not agent.start_turn(bot_id, body.text.strip()):
        raise HTTPException(409, "ایجنت در حال کار است؛ چند لحظه صبر کنید")
    return {"ok": True}


@router.get("/api/bots/{bot_id}/versions/{vid}")
def get_version(bot_id: int, vid: int, user: User = Depends(current_user)):
    with SessionLocal() as db:
        bot = _own(db, bot_id, user)
        v = db.get(BotVersion, vid)
        if not v or v.bot_id != bot_id:
            raise HTTPException(404, "نسخه یافت نشد")
        return {**_version_brief(v, bot.live_version_id), "spec": v.spec, "tests": v.tests,
                "test_report": v.test_report, "assumptions": v.assumptions}


# ----------------------------- simulator -----------------------------
class SimIn(BaseModel):
    text: str = Field(min_length=1, max_length=1000)
    user: str = Field(default="u1", max_length=20)
    version_id: int


@router.post("/api/bots/{bot_id}/sim")
def simulate(bot_id: int, body: SimIn, user: User = Depends(current_user)):
    with platforms.lock_for(bot_id), SessionLocal() as db:
        _own(db, bot_id, user)
        v = db.get(BotVersion, body.version_id)
        if not v or v.bot_id != bot_id:
            raise HTTPException(404, "نسخه یافت نشد")
        row = platforms.load_data(db, bot_id, "sandbox")
        data = copy.deepcopy(row.data or {})
        names = {"u1": "علی", "u2": "سارا", "u3": "رضا"}
        outs = Engine(BotSpec.model_validate(v.spec), data).handle(body.user, body.text, name=names.get(body.user, body.user))
        platforms.save_data(row, data)
        db.commit()
    return {"replies": [o.as_dict() for o in outs]}


class SimPayIn(BaseModel):
    payload: str = Field(min_length=1, max_length=128)
    user: str = Field(default="u1", max_length=20)
    version_id: int


@router.post("/api/bots/{bot_id}/sim/pay")
def simulate_payment(bot_id: int, body: SimPayIn, user: User = Depends(current_user)):
    """Sandbox payment: the same pre-checkout + success path a real Bale/Telegram payment takes."""
    with platforms.lock_for(bot_id), SessionLocal() as db:
        _own(db, bot_id, user)
        v = db.get(BotVersion, body.version_id)
        if not v or v.bot_id != bot_id:
            raise HTTPException(404, "نسخه یافت نشد")
        row = platforms.load_data(db, bot_id, "sandbox")
        data = copy.deepcopy(row.data or {})
        eng = Engine(BotSpec.model_validate(v.spec), data)
        err, outs = eng.pre_checkout(body.user, body.payload)
        if err:
            outs.append(Out(body.user, "❌ پرداخت رد شد: " + err))
        else:
            outs += eng.payment_success(body.user, body.payload, f"SANDBOX-{secrets.token_hex(3).upper()}")
        platforms.save_data(row, data)
        db.commit()
    return {"replies": [o.as_dict() for o in outs]}


@router.post("/api/bots/{bot_id}/sim/reset")
def sim_reset(bot_id: int, user: User = Depends(current_user)):
    with platforms.lock_for(bot_id), SessionLocal() as db:
        _own(db, bot_id, user)
        platforms.save_data(platforms.load_data(db, bot_id, "sandbox"), {})
        db.commit()
    return {"ok": True}


# ----------------------------- data -----------------------------
@router.get("/api/bots/{bot_id}/data")
def bot_data(bot_id: int, scope: str = "live", user: User = Depends(current_user)):
    if scope not in ("live", "sandbox"):
        raise HTTPException(400, "scope نامعتبر")
    with SessionLocal() as db:
        bot = _own(db, bot_id, user)
        vid = bot.live_version_id if scope == "live" else None
        if not vid:
            latest = db.query(BotVersion).filter(BotVersion.bot_id == bot_id).order_by(BotVersion.number.desc()).first()
            vid = latest.id if latest else None
        if not vid:
            return {"template": None}
        spec = BotSpec.model_validate(db.get(BotVersion, vid).spec)
        data = platforms.load_data(db, bot_id, scope).data or {}
        db.commit()
    if spec.template == "workshop":
        sessions = []
        for s in spec.workshop.sessions:
            regs = data.get("regs", {}).get(s.id, [])
            wait = data.get("wait", {}).get(s.id, [])
            sessions.append({"id": s.id, "title": s.title, "when": s.when, "capacity": s.capacity,
                             "registrations": [{"code": r.get("code"), "status": r.get("status", "confirmed"),
                                                **r.get("fields", {})} for r in regs],
                             "waitlist": [{"code": r.get("code"), **r.get("fields", {})} for r in wait]})
        return {"template": "workshop", "sessions": sessions}
    return {"template": "order", "orders": list(reversed(data.get("orders", [])))}


# ----------------------------- publish -----------------------------
class PublishIn(BaseModel):
    version_id: int
    platform: str = "bale"
    token: str = ""
    payment_token: str = ""  # empty = keep the saved one


@router.post("/api/bots/{bot_id}/publish")
def publish(bot_id: int, body: PublishIn, user: User = Depends(current_user)):
    if body.platform not in ("bale", "telegram"):
        raise HTTPException(400, "پلتفرم نامعتبر")
    with SessionLocal() as db:
        bot = _own(db, bot_id, user)
        v = db.get(BotVersion, body.version_id)
        if not v or v.bot_id != bot_id:
            raise HTTPException(404, "نسخه یافت نشد")
        token = body.token.strip() or (bot.token if bot.platform == body.platform else "")
        if not token:
            raise HTTPException(400, "توکن بات را وارد کنید")
        try:
            me = platforms.call(body.platform, token, "getMe")
        except platforms.PlatformError as e:
            raise HTTPException(400, f"توکن تأیید نشد: {e}")
        if bot.token and (bot.token != token or bot.platform != body.platform):
            platforms.disconnect(bot)
        if bot.platform != body.platform and not body.payment_token.strip():
            bot.payment_token = ""  # a payment token belongs to one platform
        bot.platform, bot.token = body.platform, token
        if body.payment_token.strip():
            bot.payment_token = body.payment_token.strip()
        bot.bot_username = me.get("username", "")
        bot.live_version_id = v.id
        db.commit()
        try:
            mode = platforms.connect(bot)
        except platforms.PlatformError as e:
            bot.live_version_id = None
            db.commit()
            raise HTTPException(400, f"اتصال بات ناموفق بود: {e}")
        return {"ok": True, "mode": mode, "username": bot.bot_username, "version": v.number}


@router.post("/api/bots/{bot_id}/unpublish")
def unpublish(bot_id: int, user: User = Depends(current_user)):
    with SessionLocal() as db:
        bot = _own(db, bot_id, user)
        bot.live_version_id = None
        db.commit()
        platforms.disconnect(bot)
    return {"ok": True}


# ----------------------------- webhook -----------------------------
@router.post("/hook/{bot_id}/{secret}")
async def webhook(bot_id: int, secret: str, request: Request):
    with SessionLocal() as db:
        bot = db.get(Bot, bot_id)
        if not bot or not secrets.compare_digest(bot.webhook_secret, secret):
            raise HTTPException(404)
    update = await request.json()
    try:
        platforms.process_update(bot_id, update)
    except Exception as e:  # never make the platform retry forever
        print(f"[webhook] bot {bot_id}: {e}")
    return {"ok": True}
