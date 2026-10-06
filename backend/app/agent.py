"""The BotLab agent.

Graph of one owner turn:

    analyze ──(needs info)──> ask clarifying questions ──> END
       │
       └─(ready)──> build/patch spec ⟲ validate ──> write acceptance tests
                         ──> run sandbox tests ──(failures)──> repair ⟲ (max 2 rounds)
                         ──> save new version (draft) ──> report to owner ──> END

Publishing is an explicit owner action (needs the bot token) handled in api.py.
"""
import json
import threading
import traceback
from typing import Optional

from pydantic import ValidationError

from .db import Bot, BotVersion, Message, SessionLocal
from .engine import FIELD_PROMPTS, L
from .llm import LLMError, chat_json
from .spec import EXAMPLE_ORDER, EXAMPLE_WORKSHOP, BotSpec
from .testing import TestCase, auto_tests, run_suite

MAX_CLARIFY_ROUNDS = 2
MAX_REPAIR_ROUNDS = 2

CAPABILITIES = """
Supported bot templates (the ONLY things you can build):
1) workshop — booking bot for workshops/classes/events:
   - list of sessions (title, date/time text, capacity, price, description)
   - registration with capacity control, collecting fields from: name, phone, address, note
   - "my registrations", optional self-cancellation (allow_cancel)
   - max sessions per user (max_per_user)
   - optional waitlist (enabled, max_size): when full, users can join; on cancellation the first in line is
     auto-registered and notified
   - optional online payment (require_payment, payment_hold_minutes): for paid sessions the seat is held for N
     minutes and the registration is confirmed ONLY after the platform confirms payment; unpaid holds expire and
     the seat goes back (or to the waitlist)
2) order — ordering bot for a limited menu (cafe, restaurant, bakery, shop):
   - menu items (name, price, category, available flag, options like size that customer must choose)
   - cart (add/remove), checkout collecting fields from: name, phone, address, note
   - rules: min_order_total, max_qty_per_item, max_items_per_order, delivery with delivery_fee and
     free_delivery_over threshold, ordering hours (open_hour, close_hour)
   - optional online payment (require_payment): the order is accepted only after payment
Common: business_name, welcome_message, currency (default تومان), support_contact.
Payments run inside Bale (rial, Bale wallet) or Telegram via the platform's invoice system.
NOT supported: refunds (handled by the business manually), discount codes, scheduled reminders, AI chat inside the bot, images, group chats, discount codes,
multi-language, other payment gateways. Received data (registrations/orders) is visible to the owner in the web dashboard.
"""


def engine_contract(template: str) -> str:
    common = f"""Bot UX contract (exact texts the runtime uses; tests must use these exact button labels):
- "/start" -> welcome_message + main menu. "{L.BACK}" and "{L.ABORT}" always return to main menu.
- Field prompts (asked one by one, in the order of collect_fields): {json.dumps(FIELD_PROMPTS, ensure_ascii=False)}
  phone must look like 09121234567; name >= 2 chars; address >= 5 chars; note any text ("-" for none).
- After the last field a summary is shown with "{L.CONFIRM}" / "{L.ABORT}" buttons.
- Money is printed like "450,000 تومان" (expectations are compared after removing thousands separators,
  converting Persian digits, so "450000" also matches). Price 0 prints "رایگان".
"""
    if template == "workshop":
        return common + f"""Workshop runtime:
- Main menu buttons: "{L.W_LIST}", "{L.W_MY}", and "{L.W_CANCEL}" (only if allow_cancel).
- "{L.W_LIST}" lists sessions with "ظرفیت باقی‌مانده: N از C" or "ظرفیت تکمیل است"; buttons "{L.W_SESSION}<title>".
- Pressing "{L.W_SESSION}<title>": if already registered -> "قبلاً ... ثبت‌نام کرده‌اید"; if reached max_per_user ->
  "حداکثر در N کارگاه"; if full and waitlist has room -> "ظرفیت ... تکمیل است" + button "{L.W_JOIN_WAIT}";
  if full and no waitlist -> "ظرفیت ... تکمیل است"; else asks fields.
- Confirm registration -> "ثبت‌نام شما در کارگاه «<title>» انجام شد" + "کد پیگیری".
- Joining the waitlist ALWAYS takes: press "{L.W_SESSION}<title>" of the full session (bot replies that it is full and
  shows "{L.W_JOIN_WAIT}"), then press "{L.W_JOIN_WAIT}", then the fields, then "{L.CONFIRM}" ->
  "شما نفر K فهرست انتظار". The session list itself never shows a join button.
- "{L.W_MY}" lists registrations ("✅ <title>") and waitlist positions.
- "{L.W_CANCEL}" shows buttons "{L.W_CANCEL_ITEM}<title>"; pressing one -> "لغو شد"; if waitlist enabled the first
  waiting user receives "جا باز شد" (use step.notify to check another user got it).
- "{L.W_MY}" shows a pending (unpaid) seat as "در انتظار پرداخت" with a button "{L.W_PAY}<title>".
""" + PAYMENT_CONTRACT
    return common + f"""Order runtime:
- Main menu buttons: "{L.O_MENU}", "{L.O_CART}", "{L.O_CHECKOUT}", "{L.O_CLEAR}".
- "{L.O_MENU}" lists items with prices ("(ناموجود)" for unavailable) and buttons "{L.O_ADD}<name>" only for
  available items.
- "{L.O_ADD}<name>": if item has options asks "با کدام گزینه" with buttons "{L.O_OPTION}<option>"; adding replies
  "به سبد اضافه شد (تعداد: N)" and "جمع سبد: X". Over max_qty_per_item -> "حداکثر N عدد"; over max_items_per_order
  -> "حداکثر N قلم".
- "{L.O_CART}" shows lines, "جمع اقلام", "هزینهٔ ارسال", "مبلغ قابل پرداخت"; buttons "{L.O_REMOVE}<name>" or
  "{L.O_REMOVE}<name> (<option>)".
- "{L.O_CHECKOUT}": empty cart -> "سبد خرید شما خالی است"; outside hours -> "سفارش‌گیری بسته است";
  below minimum -> "حداقل مبلغ سفارش"; else asks fields (address is added automatically if delivery is on).
- Confirm -> "سفارش شما ثبت شد" + "شماره سفارش" + "مبلغ کل: X".
- Test cases may set "now_hour" (0-23) to simulate the local time; default is 12.
""" + PAYMENT_CONTRACT


PAYMENT_CONTRACT = """Online payment (only when require_payment is true and the price/total is > 0):
- Confirming a paid registration/order does NOT confirm it: the reply says it is held and contains "پرداخت"
  plus an invoice, which tests see as "💳 صورت‌حساب". It must NOT contain "کد پیگیری" yet.
- A step {"user": "u1", "pay": true} pays the latest invoice of that user -> "پرداخت انجام شد" and "قطعی شد".
- A step {"wait_minutes": N} (optionally with "send") moves the clock forward first; after payment_hold_minutes
  an unpaid hold expires -> that user gets "مهلت پرداخت" and the seat is freed; paying later -> "پرداخت رد شد".
- A step must have at least one of: send, pay, wait_minutes.
"""

SPEC_SCHEMA = json.dumps(BotSpec.model_json_schema(), ensure_ascii=False)


# ---------------------------------------------------------------------------
# step logging (shown live in the UI)
# ---------------------------------------------------------------------------
class Steps:
    def __init__(self, bot_id: int):
        self.bot_id = bot_id

    def start(self, title: str) -> int:
        with SessionLocal() as db:
            m = Message(bot_id=self.bot_id, role="step", content=title, meta={"status": "running"})
            db.add(m)
            db.commit()
            return m.id

    def done(self, step_id: int, detail: str = "", status: str = "done"):
        with SessionLocal() as db:
            m = db.get(Message, step_id)
            m.meta = {**(m.meta or {}), "status": status, "detail": detail}
            db.commit()


def say(bot_id: int, content: str, meta: Optional[dict] = None):
    with SessionLocal() as db:
        db.add(Message(bot_id=bot_id, role="assistant", content=content, meta=meta or {}))
        db.commit()


# ---------------------------------------------------------------------------
# LLM nodes
# ---------------------------------------------------------------------------
def node_analyze(history: str, requirements: str, current_spec: Optional[dict], must_proceed: bool) -> dict:
    system = f"""You are "BotLab", an AI agent that builds and maintains Telegram/Bale bots for small businesses
from plain Persian descriptions written by the business owner. Always write user-facing text in fluent Persian.
{CAPABILITIES}
Your task now: read the conversation and decide the next action. Return ONE JSON object:
{{
 "intent": "build" | "change" | "chat",
 "template": "workshop" | "order" | null,
 "ready": true/false,
 "questions": ["..."],
 "unsupported": ["..."],
 "requirements": "...",
 "reply": "..."
}}
Rules:
- "build": no bot exists yet and the owner describes one. "change": a bot exists and the owner wants to modify it.
  "chat": greeting/question/thanks or a request that fits no template (explain politely what you can build).
- Ask questions ONLY for information that really changes behavior and has no sensible default. For a new
  workshop bot the essentials are: the sessions (title, time, capacity) and price; for an order bot: the menu
  items with prices. Everything else (cancel policy, fields, delivery, limits) can be defaulted.
  Max 4 short questions; each must propose the default you'll use, e.g. "... (اگر نگویید: X)".
- If something costs money (a paid session or an order) and the owner has not said whether customers must
  pay online before confirmation, include that question (default: پرداخت آنلاین لازم نیست).
- If the owner already gave the essentials, set ready=true with no questions. Prefer fewer questions.
- must_proceed={str(must_proceed).lower()}: if true you MUST set ready=true and use reasonable defaults.
- For "change", ready=true unless the change is truly ambiguous.
- "unsupported": requested features outside the capabilities; in "reply" say so briefly and offer the closest
  supported behavior.
- "requirements": a COMPLETE, consolidated Persian description of the bot as it should be after this turn
  (merge previous requirements + everything the owner said, including concrete numbers). This is your memory.
- "reply": a short friendly Persian message to the owner (if asking questions, introduce them; do not repeat
  them inside reply)."""
    user = f"""Previous consolidated requirements:
{requirements or "(none)"}

Current bot spec (null if no bot yet):
{json.dumps(current_spec, ensure_ascii=False) if current_spec else "null"}

Conversation (latest last):
{history}"""
    return chat_json(system, user)


def node_build_spec(requirements: str, template: str, current_spec: Optional[dict], feedback: str = "") -> dict:
    example = EXAMPLE_WORKSHOP if template == "workshop" else EXAMPLE_ORDER
    fix = ("Your previous attempt was invalid. Fix these validation errors:\n" + feedback) if feedback else ""
    system = f"""You convert bot requirements into a BotSpec JSON that a deterministic runtime executes.
{CAPABILITIES}
BotSpec JSON schema:
{SPEC_SCHEMA}
Example ({template}):
{json.dumps(example, ensure_ascii=False)}
Rules:
- Output ONE JSON object: {{"spec": <BotSpec>, "assumptions": ["Persian sentences about defaults you chose"],
  "change_summary": ["Persian bullet of what changed vs current spec (empty for a new bot)"]}}
- All texts in Persian. Prices are integers in the currency (toman unless stated). Use stable ids (w1, w2 / i1, i2).
- When a current spec exists, start from it and change ONLY what the requirements ask; keep ids of existing
  sessions/items unchanged.
- Write a warm welcome_message mentioning the business name."""
    user = f"""Template: {template}
Requirements:
{requirements}

Current spec:
{json.dumps(current_spec, ensure_ascii=False) if current_spec else "null"}
{fix}"""
    return chat_json(system, user)


def node_write_tests(requirements: str, spec: dict, change_summary: list, existing: list) -> list:
    system = f"""You are a QA engineer writing acceptance tests (scripted chats) for a bot.
{engine_contract(spec["template"])}
Test case JSON: {{"name": "short name in Persian (not English)", "description": "Persian", "now_hour": null or 0-23,
 "steps": [{{"user": "u1", "send": "text or exact button label", "expect": ["substring"], "expect_not": [],
            "notify": {{"u2": ["substring"]}}}}]}}
Each test starts with an EMPTY bot (no registrations/orders). Different users: u1, u2, u3...
Return ONE JSON object: {{"tests": [ ... ]}} with 2-4 tests that verify the owner's SPECIFIC requirements
{"and especially the latest change" if change_summary else ""} (concrete capacities, prices, rules, waitlist,
options...). Basic happy paths are already covered by automatic tests; focus on business rules and edge cases.
Keep expectations to short distinctive substrings taken from the contract above or from the spec values.
When you must fill fields use valid values (e.g. name "علی رضایی", phone "09121234567", address "تهران، خیابان ولیعصر، پلاک ۱۰")."""
    user = f"""Requirements:
{requirements}

Change summary: {json.dumps(change_summary, ensure_ascii=False)}

Spec:
{json.dumps(spec, ensure_ascii=False)}

Existing acceptance tests (do not duplicate): {json.dumps([t["name"] for t in existing], ensure_ascii=False)}"""
    out = chat_json(system, user)
    return out.get("tests", [])


def node_repair(requirements: str, spec: dict, failures: list, tests: list) -> dict:
    system = f"""You are debugging a bot built from a BotSpec. Some sandbox tests failed.
{engine_contract(spec["template"])}
For each failure decide: is the SPEC wrong (doesn't match requirements) or is the TEST wrong (wrong label,
wrong expectation, or it tests behavior the owner intentionally changed)? Never weaken a test that correctly
encodes the owner's requirements.
Return ONE JSON object:
{{"diagnosis": "ONE short sentence, in Persian only", "spec": <fixed full BotSpec or null if spec is fine>,
  "tests": [<fixed full test case objects with the same name>], "drop": ["names of obsolete tests"]}}
Only "agent" tests may be fixed or dropped; "auto" tests are generated from the spec and can only be fixed by
fixing the spec."""
    user = f"""Requirements:
{requirements}

Spec:
{json.dumps(spec, ensure_ascii=False)}

Failed tests (with transcript up to the failing step):
{json.dumps(failures, ensure_ascii=False)[:20000]}

Current agent tests:
{json.dumps([t for t in tests if t.get("origin") == "agent"], ensure_ascii=False)[:8000]}"""
    return chat_json(system, user)


# ---------------------------------------------------------------------------
# helpers
# ---------------------------------------------------------------------------
def spec_diff(old, new, path="") -> list[str]:
    if isinstance(old, dict) and isinstance(new, dict):
        out = []
        for k in sorted(set(old) | set(new), key=str):
            out += spec_diff(old.get(k), new.get(k), f"{path}.{k}" if path else k)
        return out
    if isinstance(old, list) and isinstance(new, list) and all(isinstance(x, dict) and "id" in x for x in old + new):
        o, n = {x["id"]: x for x in old}, {x["id"]: x for x in new}
        out = []
        for k in list(o) + [k for k in n if k not in o]:
            if k not in n:
                out.append(f"- {path}[{k}] حذف شد")
            elif k not in o:
                out.append(f"+ {path}[{k}] اضافه شد: {n[k].get('title') or n[k].get('name')}")
            else:
                out += spec_diff(o[k], n[k], f"{path}[{k}]")
        return out
    if old != new:
        return [f"~ {path}: {json.dumps(old, ensure_ascii=False)} → {json.dumps(new, ensure_ascii=False)}"]
    return []


def _validate_tests(raw: list, origin: str = "agent") -> list[dict]:
    out = []
    for t in raw or []:
        try:
            t = {**t, "origin": origin}
            out.append(TestCase.model_validate(t).model_dump())
        except (ValidationError, TypeError):
            continue
    return out


def _failures_for_llm(report: dict) -> list:
    out = []
    for r in report["results"]:
        if not r["passed"]:
            out.append({"name": r["name"], "origin": r["origin"], "failed_step": r["failed_step"],
                        "reason": r["reason"], "transcript": r["transcript"]})
    return out


def _history(db, bot_id: int, limit: int = 24) -> tuple[str, int]:
    msgs = (db.query(Message).filter(Message.bot_id == bot_id, Message.role.in_(["user", "assistant"]))
            .order_by(Message.id.desc()).limit(limit).all())[::-1]
    lines, clar = [], 0
    for m in msgs:
        who = "OWNER" if m.role == "user" else "AGENT"
        text = m.content
        if m.meta and m.meta.get("questions"):
            text += "\n" + "\n".join("- " + q for q in m.meta["questions"])
        lines.append(f"{who}: {text}")
        kind = (m.meta or {}).get("kind")
        if kind == "result":
            clar = 0
        elif kind == "questions":
            clar += 1
    return "\n".join(lines), clar


# ---------------------------------------------------------------------------
# the turn
# ---------------------------------------------------------------------------
def run_turn(bot_id: int):
    steps = Steps(bot_id)
    try:
        _run_turn(bot_id, steps)
    except LLMError as e:
        say(bot_id, f"⚠️ ارتباط با مدل زبانی برقرار نشد: {e}\nلطفاً چند لحظهٔ دیگر دوباره پیام بدهید.", {"kind": "error"})
    except Exception as e:  # pragma: no cover
        traceback.print_exc()
        say(bot_id, f"⚠️ خطای غیرمنتظره در اجرای ایجنت: {e}", {"kind": "error"})
    finally:
        with SessionLocal() as db:
            # close any step left "running"
            for m in db.query(Message).filter(Message.bot_id == bot_id, Message.role == "step").all():
                if (m.meta or {}).get("status") == "running":
                    m.meta = {**m.meta, "status": "error"}
            bot = db.get(Bot, bot_id)
            bot.agent_status = "idle"
            db.commit()


def _run_turn(bot_id: int, steps: Steps):
    with SessionLocal() as db:
        bot = db.get(Bot, bot_id)
        latest = db.query(BotVersion).filter(BotVersion.bot_id == bot_id).order_by(BotVersion.number.desc()).first()
        history, clar_rounds = _history(db, bot_id)
        requirements = bot.requirements
    current_spec = latest.spec if latest else None

    # 1) analyze -----------------------------------------------------------------
    s = steps.start("🔎 تحلیل درخواست و بررسی ابهام‌ها")
    a = node_analyze(history, requirements, current_spec, must_proceed=clar_rounds >= MAX_CLARIFY_ROUNDS)
    intent = a.get("intent", "chat")
    template = a.get("template") or (current_spec or {}).get("template")
    new_req = (a.get("requirements") or requirements or "").strip()
    with SessionLocal() as db:
        b = db.get(Bot, bot_id)
        b.requirements = new_req
        db.commit()

    if intent == "chat" or not template:
        steps.done(s, "پاسخ گفتگو")
        say(bot_id, a.get("reply") or "چطور می‌توانم کمکتان کنم؟", {"kind": "chat", "unsupported": a.get("unsupported", [])})
        return
    questions = [q for q in a.get("questions") or [] if q]
    if not a.get("ready") and questions:
        steps.done(s, f"{len(questions)} سؤال برای رفع ابهام")
        say(bot_id, a.get("reply") or "برای ساخت دقیق بات چند سؤال کوتاه دارم:",
            {"kind": "questions", "questions": questions[:4], "unsupported": a.get("unsupported", [])})
        return
    steps.done(s, "درخواست کامل است — " + ("ساخت بات جدید" if not current_spec else "اعمال تغییر روی بات"))
    if current_spec and current_spec.get("template") != template:
        template = current_spec["template"]

    # 2) build / patch spec --------------------------------------------------------
    s = steps.start("🧩 طراحی مشخصات بات" if not current_spec else "🧩 اعمال تغییر روی مشخصات بات")
    spec_obj, built, feedback = None, {}, ""
    for _ in range(3):
        built = node_build_spec(new_req, template, current_spec, feedback)
        try:
            spec_obj = BotSpec.model_validate(built.get("spec") or {})
            break
        except ValidationError as e:
            feedback = str(e)[:2000]
    if not spec_obj:
        steps.done(s, "مشخصات معتبر ساخته نشد", "error")
        say(bot_id, "⚠️ نتوانستم مشخصات معتبری برای بات بسازم. لطفاً درخواست را کمی واضح‌تر توضیح دهید.", {"kind": "error"})
        return
    spec = spec_obj.model_dump()
    diff = spec_diff(current_spec, spec) if current_spec else []
    if current_spec and not diff:
        steps.done(s, "تغییری لازم نبود")
        say(bot_id, "این درخواست تغییری در رفتار بات ایجاد نمی‌کند؛ بات فعلی همین حالا این‌طور کار می‌کند. "
                    + (a.get("reply") or ""), {"kind": "chat"})
        return
    steps.done(s, f"{len(diff)} تغییر در مشخصات" if current_spec else "مشخصات معتبر ساخته شد")

    # 3) tests -----------------------------------------------------------------------
    s = steps.start("🧪 طراحی سناریوهای آزمون")
    prev_agent_tests = [t for t in (latest.tests if latest else []) if t.get("origin") == "agent"]
    try:
        new_tests = _validate_tests(node_write_tests(new_req, spec, built.get("change_summary") or [], prev_agent_tests))
        note = ""
    except LLMError:  # degrade gracefully: automatic + regression tests still run
        new_tests, note = [], " (مدل در دسترس نبود؛ فقط آزمون‌های خودکار و رگرسیون)"
    new_names = {t["name"] for t in new_tests}
    agent_tests = [t for t in prev_agent_tests if t["name"] not in new_names] + new_tests
    steps.done(s, f"{len(new_tests)} آزمون جدید" + (f" + {len(agent_tests) - len(new_tests)} آزمون رگرسیون قبلی" if prev_agent_tests else "") + note)

    # 4) run + repair loop --------------------------------------------------------------
    def suite():
        tests = [t.model_dump() for t in auto_tests(spec_obj)] + agent_tests
        return tests, run_suite(spec_obj, [TestCase.model_validate(t) for t in tests])

    s = steps.start("▶️ اجرای آزمون‌ها در محیط آزمایشی")
    tests, report = suite()
    steps.done(s, f"{report['passed']} از {report['total']} آزمون موفق", "done" if not report["failed"] else "warn")

    for rnd in range(MAX_REPAIR_ROUNDS):
        if not report["failed"]:
            break
        s = steps.start(f"🛠 عیب‌یابی و اصلاح (دور {rnd + 1})")
        try:
            fix = node_repair(new_req, spec, _failures_for_llm(report), tests)
        except LLMError:
            steps.done(s, "مدل در دسترس نبود؛ اصلاح انجام نشد", "warn")
            break
        notes = [fix.get("diagnosis", "")]
        if fix.get("spec"):
            try:
                spec_obj = BotSpec.model_validate(fix["spec"])
                spec = spec_obj.model_dump()
                notes.append("مشخصات اصلاح شد")
            except ValidationError:
                notes.append("اصلاح مشخصات نامعتبر بود و نادیده گرفته شد")
        fixed = {t["name"]: t for t in _validate_tests(fix.get("tests"))}
        drop = set(fix.get("drop") or [])
        agent_tests = [fixed.get(t["name"], t) for t in agent_tests if t["name"] not in drop]
        tests, report = suite()
        steps.done(s, " — ".join(n for n in notes if n) + f" | نتیجه: {report['passed']}/{report['total']}",
                   "done" if not report["failed"] else "warn")

    # 5) save version ------------------------------------------------------------------
    s = steps.start("📦 ساخت نسخهٔ جدید")
    diff = spec_diff(current_spec, spec) if current_spec else []
    change_summary = built.get("change_summary") or []
    with SessionLocal() as db:
        number = (latest.number + 1) if latest else 1
        v = BotVersion(bot_id=bot_id, number=number, spec=spec, tests=tests, test_report=report,
                       change_note="\n".join(change_summary) if current_spec else "نسخهٔ اولیه",
                       assumptions=built.get("assumptions") or [])
        db.add(v)
        b = db.get(Bot, bot_id)
        b.template = spec["template"]
        if not current_spec:
            b.name = spec["business_name"]
        db.commit()
        vid, is_live = v.id, b.live_version_id is not None
    steps.done(s, f"نسخهٔ {number}")

    ok = report["failed"] == 0
    lines = []
    if current_spec:
        lines.append(f"✅ تغییر روی بات اعمال شد و **نسخهٔ {number}** ساخته شد.")
        if change_summary:
            lines.append("تغییرات:\n" + "\n".join("• " + c for c in change_summary))
    else:
        lines.append(f"✅ بات {spec['business_name']} ساخته شد (**نسخهٔ {number}**).")
    if built.get("assumptions"):
        lines.append("فرض‌هایی که در نظر گرفتم:\n" + "\n".join("• " + x for x in built["assumptions"]))
    lines.append(f"🧪 آزمون‌ها: {report['passed']} از {report['total']} موفق" + ("" if ok else " — جزئیات موارد ناموفق در تب «آزمون‌ها» است."))
    lines.append("می‌توانید بات را در «شبیه‌ساز» امتحان کنید و سپس " +
                 ("نسخهٔ جدید را منتشر کنید." if is_live else "آن را روی بله یا تلگرام منتشر کنید."))
    say(bot_id, "\n\n".join(lines), {"kind": "result", "version_id": vid, "version": number,
                                     "passed": report["passed"], "total": report["total"], "diff": diff,
                                     "unsupported": a.get("unsupported", [])})


def start_turn(bot_id: int, text: str) -> bool:
    with SessionLocal() as db:
        bot = db.get(Bot, bot_id)
        if bot.agent_status == "running":
            return False
        bot.agent_status = "running"
        db.add(Message(bot_id=bot_id, role="user", content=text, meta={}))
        db.commit()
    threading.Thread(target=run_turn, args=(bot_id,), daemon=True).start()
    return True
