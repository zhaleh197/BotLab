"""Sandbox test harness: runs scripted conversations against a BotSpec in memory."""
import traceback
from typing import Literal, Optional

from pydantic import BaseModel, Field

from .engine import FIELD_PROMPTS, Engine, L, normalize
from .spec import BotSpec


class TestStep(BaseModel):
    user: str = "u1"
    send: str
    expect: list[str] = Field(default_factory=list, description="Substrings that must appear in replies to `user`")
    expect_not: list[str] = Field(default_factory=list)
    notify: dict[str, list[str]] = Field(default_factory=dict,
                                         description="Other users that must receive a message containing these")


class TestCase(BaseModel):
    name: str
    description: str = ""
    origin: Literal["auto", "agent"] = "agent"
    now_hour: Optional[int] = Field(default=None, ge=0, le=23)
    steps: list[TestStep] = Field(min_length=1)


def _flatten(outs) -> str:
    return "\n".join(o.text + "\n" + " | ".join(b for row in o.buttons for b in row) for o in outs)


def run_test(spec: BotSpec, tc: TestCase) -> dict:
    data: dict = {}
    eng = Engine(spec, data, now_hour=tc.now_hour if tc.now_hour is not None else 12)
    transcript = []
    for i, step in enumerate(tc.steps):
        try:
            outs = eng.handle(step.user, step.send, name=f"کاربر {step.user}")
        except Exception as e:  # engine bug: report, never crash the agent
            return {"name": tc.name, "origin": tc.origin, "passed": False, "failed_step": i,
                    "reason": f"خطای اجرای بات: {e}", "trace": traceback.format_exc()[-800:],
                    "transcript": transcript}
        transcript.append({"user": step.user, "send": step.send, "replies": [o.as_dict() for o in outs]})
        mine = normalize(_flatten([o for o in outs if o.to == step.user]))
        problems = [f"انتظار «{e}» در پاسخ بود" for e in step.expect if normalize(e) not in mine]
        problems += [f"«{e}» نباید در پاسخ باشد" for e in step.expect_not if normalize(e) in mine]
        for other, exps in step.notify.items():
            theirs = normalize(_flatten([o for o in outs if o.to == other]))
            problems += [f"کاربر {other} باید پیام «{e}» را دریافت کند" for e in exps if normalize(e) not in theirs]
        if problems:
            return {"name": tc.name, "origin": tc.origin, "passed": False, "failed_step": i,
                    "reason": "؛ ".join(problems), "transcript": transcript}
    return {"name": tc.name, "origin": tc.origin, "passed": True, "failed_step": None, "reason": "",
            "transcript": transcript}


def run_suite(spec: BotSpec, tests: list[TestCase]) -> dict:
    results = [run_test(spec, t) for t in tests]
    passed = sum(r["passed"] for r in results)
    return {"passed": passed, "failed": len(results) - passed, "total": len(results), "results": results}


# ---------------------------------------------------------------------------
# Automatic regression tests derived from the spec itself.
# ---------------------------------------------------------------------------

def _field_values(fields, i: int) -> list[str]:
    sample = {"name": f"کاربر شماره {i}", "phone": f"0912{1000000 + i}",
              "address": f"تهران، خیابان آزادی، پلاک {i}", "note": "-"}
    return [sample[f] for f in fields]


def _fill(user: str, fields, i: int) -> list[TestStep]:
    vals = _field_values(fields, i)
    steps = []
    for k, v in enumerate(vals):
        nxt = FIELD_PROMPTS[fields[k + 1]] if k + 1 < len(fields) else L.CONFIRM
        steps.append(TestStep(user=user, send=v, expect=[nxt[:12]]))
    return steps


def auto_tests(spec: BotSpec) -> list[TestCase]:
    tests = [TestCase(name="شروع و منوی اصلی", origin="auto",
                      description="ارسال /start باید پیام خوش‌آمد و منوی اصلی را نشان دهد.",
                      steps=[TestStep(send="/start", expect=[spec.welcome_message[:20]])])]
    if spec.template == "workshop":
        tests += _workshop_auto(spec)
    else:
        tests += _order_auto(spec)
    return tests


def _workshop_auto(spec: BotSpec) -> list[TestCase]:
    cfg = spec.workshop
    f = cfg.collect_fields
    tests = []
    s0 = cfg.sessions[0]
    steps = [TestStep(send="/start"), TestStep(send=L.W_LIST, expect=[s0.title])]
    steps.append(TestStep(send=L.W_SESSION + s0.title, expect=[FIELD_PROMPTS[f[0]][:12]] if f else [L.CONFIRM]))
    steps += _fill("u1", f, 1)
    steps.append(TestStep(send=L.CONFIRM, expect=["ثبت‌نام شما", "کد پیگیری"]))
    steps.append(TestStep(send=L.W_MY, expect=[s0.title]))
    tests.append(TestCase(name="ثبت‌نام موفق", origin="auto",
                          description=f"یک کاربر در «{s0.title}» ثبت‌نام می‌کند.", steps=steps))

    s = min(cfg.sessions, key=lambda x: x.capacity)
    if s.capacity <= 40:
        steps = []
        for i in range(1, s.capacity + 1):
            uid = f"u{i}"
            steps.append(TestStep(user=uid, send=L.W_SESSION + s.title))
            steps += _fill(uid, f, i)
            steps.append(TestStep(user=uid, send=L.CONFIRM, expect=["ثبت‌نام شما"]))
        extra = f"u{s.capacity + 1}"
        if cfg.waitlist.enabled:
            steps.append(TestStep(user=extra, send=L.W_SESSION + s.title, expect=["تکمیل", L.W_JOIN_WAIT]))
            steps.append(TestStep(user=extra, send=L.W_JOIN_WAIT))
            steps += _fill(extra, f, s.capacity + 1)
            steps.append(TestStep(user=extra, send=L.CONFIRM, expect=["فهرست انتظار"]))
            if cfg.allow_cancel:
                steps.append(TestStep(user="u1", send=L.W_CANCEL, expect=[L.W_CANCEL_ITEM + s.title]))
                steps.append(TestStep(user="u1", send=L.W_CANCEL_ITEM + s.title, expect=["لغو شد"],
                                      notify={extra: ["ثبت‌نام شما قطعی شد"]}))
            name, desc = "ظرفیت و فهرست انتظار", "پس از تکمیل ظرفیت، نفر بعدی به فهرست انتظار می‌رود."
        else:
            steps.append(TestStep(user=extra, send=L.W_SESSION + s.title, expect=["تکمیل"],
                                  expect_not=[L.W_JOIN_WAIT]))
            name, desc = "کنترل ظرفیت", f"پس از {s.capacity} ثبت‌نام، ثبت‌نام جدید پذیرفته نمی‌شود."
        tests.append(TestCase(name=name, origin="auto", description=desc, steps=steps))
    return tests


def _order_auto(spec: BotSpec) -> list[TestCase]:
    cfg = spec.order
    r = cfg.rules
    tests = []
    avail = [i for i in cfg.items if i.available]
    unavail = [i for i in cfg.items if not i.available]
    open_h = r.open_hour if r.open_hour is not None else 12

    def add(it) -> list[TestStep]:
        if it.options:
            return [TestStep(send=L.O_ADD + it.name, expect=[L.O_OPTION + it.options[0]]),
                    TestStep(send=L.O_OPTION + it.options[0], expect=["به سبد اضافه شد"])]
        return [TestStep(send=L.O_ADD + it.name, expect=["به سبد اضافه شد"])]

    menu_step = TestStep(send=L.O_MENU, expect=[avail[0].name] if avail else [],
                         expect_not=[L.O_ADD + i.name for i in unavail])
    if avail:
        # Greedily add items (respecting per-item / per-order limits) until the minimum order is reached.
        plan, total, count = [], 0, 0
        for it in sorted(avail, key=lambda x: -x.price):
            q = 0
            while total < max(r.min_order_total, 1) and q < r.max_qty_per_item and count < r.max_items_per_order:
                plan.append(it)
                total += it.price
                q += 1
                count += 1
        if total >= r.min_order_total:
            fields = list(cfg.collect_fields) + (["address"] if r.delivery and "address" not in cfg.collect_fields else [])
            steps = [TestStep(send="/start"), menu_step]
            for it in plan:
                steps += add(it)
            steps.append(TestStep(send=L.O_CHECKOUT, expect=[FIELD_PROMPTS[fields[0]][:12]] if fields else [L.CONFIRM]))
            steps += _fill("u1", fields, 1)
            steps.append(TestStep(send=L.CONFIRM, expect=["سفارش شما ثبت شد"]))
            tests.append(TestCase(name="سفارش کامل", origin="auto", now_hour=open_h,
                                  description="افزودن آیتم‌ها، ثبت اطلاعات و نهایی کردن سفارش.", steps=steps))

        cheap = min(avail, key=lambda x: x.price)
        if r.min_order_total and cheap.price < r.min_order_total:
            steps = [TestStep(send="/start")] + add(cheap) + [TestStep(send=L.O_CHECKOUT, expect=["حداقل مبلغ سفارش"])]
            tests.append(TestCase(name="قانون حداقل سفارش", origin="auto", now_hour=open_h,
                                  description="سفارش کمتر از حداقل مبلغ نباید ثبت شود.", steps=steps))

        if r.open_hour is not None and r.close_hour is not None and r.close_hour < 24:
            steps = [TestStep(send="/start")] + add(cheap) + [TestStep(send=L.O_CHECKOUT, expect=["سفارش‌گیری بسته است"])]
            tests.append(TestCase(name="ساعت کاری", origin="auto", now_hour=r.close_hour % 24,
                                  description="خارج از ساعت کاری سفارش ثبت نمی‌شود.", steps=steps))
    return tests
