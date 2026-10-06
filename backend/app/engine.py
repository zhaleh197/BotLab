"""Deterministic runtime that executes a BotSpec.

`Engine.handle(uid, text)` consumes one incoming message and returns the outgoing
messages (possibly addressed to other users, e.g. waitlist promotions). All state lives
in the plain-JSON `data` dict so it can be persisted anywhere and reset for tests.
"""
import re
import time
from dataclasses import dataclass, field
from datetime import datetime
from typing import Optional
from zoneinfo import ZoneInfo

from .config import TIMEZONE
from .spec import BotSpec


@dataclass
class Out:
    to: str
    text: str
    buttons: list[list[str]] = field(default_factory=list)
    # A payment request: {"payload", "title", "description", "amount"} (amount in the spec currency).
    invoice: Optional[dict] = None

    def as_dict(self):
        d = {"to": self.to, "text": self.text, "buttons": self.buttons}
        if self.invoice:
            d["invoice"] = self.invoice
        return d


class L:
    """Button labels. Exposed to the agent so it can write exact test steps."""
    BACK = "🏠 منوی اصلی"
    CONFIRM = "✅ تأیید"
    ABORT = "✖️ انصراف"
    # workshop
    W_LIST = "📅 کارگاه‌ها"
    W_MY = "🎟 ثبت‌نام‌های من"
    W_CANCEL = "❌ لغو ثبت‌نام"
    W_JOIN_WAIT = "⏳ عضویت در فهرست انتظار"
    W_SESSION = "📝 "        # + session title
    W_CANCEL_ITEM = "🚫 "    # + session title
    W_PAY = "💳 پرداخت "     # + session title (re-send the invoice of a held seat)
    # order
    O_MENU = "🍽 منو"
    O_CART = "🛒 سبد خرید"
    O_CHECKOUT = "✅ ثبت سفارش"
    O_CLEAR = "🗑 خالی کردن سبد"
    O_ADD = "➕ "            # + item name
    O_REMOVE = "➖ "         # + item name (+ " (option)")
    O_OPTION = "🔸 "         # + option


FIELD_PROMPTS = {
    "name": "👤 لطفاً نام و نام خانوادگی خود را بنویسید:",
    "phone": "📞 شماره موبایل خود را بنویسید (مثلاً 09121234567):",
    "address": "📍 آدرس کامل تحویل را بنویسید:",
    "note": "📝 توضیحات اضافه را بنویسید (اگر ندارید «-» بفرستید):",
}
FIELD_LABELS = {"name": "نام", "phone": "موبایل", "address": "آدرس", "note": "توضیحات"}
FIELD_ERRORS = {
    "name": "نام واردشده معتبر نیست. لطفاً دوباره بنویسید:",
    "phone": "شماره موبایل معتبر نیست. نمونهٔ درست: 09121234567",
    "address": "آدرس خیلی کوتاه است. لطفاً کامل‌تر بنویسید:",
    "note": "",
}

_FA_DIGITS = str.maketrans("۰۱۲۳۴۵۶۷۸۹٠١٢٣٤٥٦٧٨٩", "01234567890123456789")


def normalize(s: str) -> str:
    """Lenient normalization used for matching buttons and test expectations."""
    s = (s or "").translate(_FA_DIGITS)
    s = s.replace("ي", "ی").replace("ك", "ک").replace("‌", "").replace("️", "")
    s = re.sub(r"(?<=\d)[,٬](?=\d)", "", s)
    s = re.sub(r"\s+", " ", s)
    return s.strip().lower()


def _strip_icon(s: str) -> str:
    return re.sub(r"^[^\w؀-ۿ]+", "", s).strip()


def matches(text: str, label: str) -> bool:
    t, l = normalize(text), normalize(label)
    if t == l:
        return True
    # Plain typed text (no leading icon) may match a button by its words only.
    return t != "" and t == _strip_icon(t) and t == _strip_icon(l)


def valid_field(name: str, value: str) -> Optional[str]:
    v = value.strip()
    if name == "phone":
        p = re.sub(r"[\s\-]", "", v.translate(_FA_DIGITS))
        return p if re.fullmatch(r"(?:\+98|0098|0)?9\d{9}", p) else None
    if name == "name":
        return v if 2 <= len(v) <= 80 else None
    if name == "address":
        return v if len(v) >= 5 else None
    return v or "-"


class Engine:
    def __init__(self, spec: BotSpec, data: dict, now_hour: Optional[int] = None, now: Optional[float] = None):
        self.spec = spec
        self.data = data
        self.now_hour = now_hour
        self.now = now if now is not None else time.time()
        data.setdefault("users", {})
        data.setdefault("seq", 0)
        if spec.template == "workshop":
            data.setdefault("regs", {})
            data.setdefault("wait", {})
        else:
            data.setdefault("orders", [])

    # ---------- helpers ----------
    def money(self, n: int) -> str:
        return "رایگان" if n == 0 else f"{n:,} {self.spec.currency}"

    def _user(self, uid: str, name: str = "") -> dict:
        u = self.data["users"].setdefault(uid, {"state": None, "cart": [], "name": name})
        if name:
            u["name"] = name
        return u

    def _code(self, prefix: str) -> str:
        self.data["seq"] += 1
        return f"{prefix}-{100 + self.data['seq']}"

    def _hour(self) -> int:
        if self.now_hour is not None:
            return self.now_hour
        return datetime.now(ZoneInfo(TIMEZONE)).hour

    def main_buttons(self) -> list[list[str]]:
        if self.spec.template == "workshop":
            row2 = [L.W_MY] + ([L.W_CANCEL] if self.spec.workshop.allow_cancel else [])
            return [[L.W_LIST], row2]
        return [[L.O_MENU, L.O_CART], [L.O_CHECKOUT, L.O_CLEAR]]

    def _main_labels(self) -> list[str]:
        return [b for row in self.main_buttons() for b in row]

    def _menu(self, uid: str, text: str) -> Out:
        return Out(uid, text, self.main_buttons())

    # ---------- entry point ----------
    def handle(self, uid: str, text: str, name: str = "") -> list[Out]:
        expired = self.sweep()
        return expired + self._handle(str(uid), text, name)

    def _handle(self, uid: str, text: str, name: str = "") -> list[Out]:
        u = self._user(uid, name)
        text = (text or "").strip()

        if text.startswith("/start") or matches(text, L.BACK) or matches(text, L.ABORT):
            u["state"] = None
            if text.startswith("/start"):
                msg = self.spec.welcome_message
                if self.spec.support_contact:
                    msg += f"\n\n☎️ پشتیبانی: {self.spec.support_contact}"
                return [self._menu(uid, msg + "\n\nاز دکمه‌های زیر استفاده کنید 👇")]
            return [self._menu(uid, "منوی اصلی 👇")]

        # Main-menu buttons always win over an in-progress flow.
        if u["state"] and any(matches(text, b) for b in self._main_labels()):
            u["state"] = None

        if self.spec.template == "workshop":
            return self._workshop(uid, u, text)
        return self._order(uid, u, text)

    # ---------- payments ----------
    def _hold_seconds(self) -> int:
        cfg = self.spec.workshop or self.spec.order
        return cfg.payment_hold_minutes * 60

    def _left_minutes(self, entry) -> int:
        return max(1, int((entry["expires"] - self.now + 59) // 60))

    def sweep(self) -> list[Out]:
        """Release seats/orders whose payment window has passed (and promote the waitlist)."""
        outs: list[Out] = []
        if self.spec.template == "workshop":
            for s in self.spec.workshop.sessions:
                regs = self._regs(s.id)
                gone = [r for r in regs if r.get("status") == "pending" and r["expires"] <= self.now]
                if not gone:
                    continue
                regs[:] = [r for r in regs if r not in gone]
                for r in gone:
                    outs.append(Out(r["uid"], f"⌛ مهلت پرداخت کارگاه «{s.title}» تمام شد و جای رزروشده آزاد شد.",
                                    self.main_buttons()))
                outs += self._promote(s)
        else:
            for o in self.data["orders"]:
                if o.get("status") == "pending_payment" and o["expires"] <= self.now:
                    o["status"] = "expired"
                    outs.append(Out(o["uid"], f"⌛ مهلت پرداخت سفارش {o['code']} تمام شد و سفارش لغو شد.",
                                    self.main_buttons()))
        return outs

    def _find_payable(self, payload: str):
        kind, _, code = (payload or "").partition(":")
        if kind == "W" and self.spec.template == "workshop":
            for s in self.spec.workshop.sessions:
                for r in self._regs(s.id):
                    if r.get("code") == code:
                        return s, r
        if kind == "O" and self.spec.template == "order":
            for o in self.data["orders"]:
                if o.get("code") == code:
                    return None, o
        return None, None

    def pre_checkout(self, uid: str, payload: str) -> tuple[Optional[str], list[Out]]:
        """Called by the platform right before charging. Returns (error or None, outgoing messages)."""
        outs = self.sweep()
        _, entry = self._find_payable(payload)
        if not entry or entry.get("uid") != str(uid):
            return "این صورت‌حساب معتبر نیست.", outs
        if entry.get("status") not in ("pending", "pending_payment"):
            return "مهلت پرداخت این صورت‌حساب تمام شده یا قبلاً پرداخت شده است.", outs
        return None, outs

    def payment_success(self, uid: str, payload: str, charge_id: str = "", amount: int = 0) -> list[Out]:
        """Called when the platform confirms the money was received. Only this confirms a paid booking."""
        uid = str(uid)
        s, entry = self._find_payable(payload)
        support = f"\n☎️ {self.spec.support_contact}" if self.spec.support_contact else ""
        if not entry or entry.get("status") not in ("pending", "pending_payment"):
            self.data.setdefault("unmatched_payments", []).append(
                {"uid": uid, "payload": payload, "charge_id": charge_id, "amount": amount, "at": self.now})
            return [self._menu(uid, "پرداخت شما دریافت شد اما مهلت رزرو تمام شده بود. "
                                    "برای پیگیری و بازگشت وجه با پشتیبانی تماس بگیرید." + support)]
        entry.pop("expires", None)
        entry["charge_id"] = charge_id
        receipt = f"\n🧾 شمارهٔ تراکنش: {charge_id}" if charge_id else ""
        if s:  # workshop seat
            entry["status"] = "paid"
            return [self._menu(uid, f"✅ پرداخت انجام شد و ثبت‌نام شما در کارگاه «{s.title}» قطعی شد.\n"
                                    f"🗓 {s.when}\n🔖 کد پیگیری: {entry['code']}" + receipt)]
        entry["status"], entry["paid"] = "new", True
        return [self._menu(uid, f"✅ پرداخت انجام شد و سفارش {entry['code']} قطعی شد.\n"
                                f"💳 مبلغ: {self.money(entry['total'])}\nاز خرید شما متشکریم 🙏" + receipt)]

    # ---------- shared: field collection ----------
    def _start_fields(self, uid, u, fields: list[str], ctx: dict) -> list[Out]:
        u["state"] = {"step": "fields", "fields": list(fields), "idx": 0, "values": {}, **ctx}
        return self._next_field(uid, u)

    def _next_field(self, uid, u) -> list[Out]:
        st = u["state"]
        if st["idx"] < len(st["fields"]):
            return [Out(uid, FIELD_PROMPTS[st["fields"][st["idx"]]], [[L.ABORT]])]
        st["step"] = "confirm"
        return [Out(uid, self._summary(u) + "\n\nآیا اطلاعات بالا را تأیید می‌کنید؟", [[L.CONFIRM, L.ABORT]])]

    def _take_field(self, uid, u, text) -> list[Out]:
        st = u["state"]
        fname = st["fields"][st["idx"]]
        val = valid_field(fname, text)
        if val is None:
            return [Out(uid, FIELD_ERRORS[fname], [[L.ABORT]])]
        st["values"][fname] = val
        st["idx"] += 1
        return self._next_field(uid, u)

    def _fields_text(self, values: dict) -> str:
        return "\n".join(f"{FIELD_LABELS[k]}: {v}" for k, v in values.items())

    def _summary(self, u) -> str:
        st = u["state"]
        if self.spec.template == "workshop":
            s = self._session(st["sid"])
            head = "📋 ثبت‌نام در" if st["mode"] == "reg" else "📋 عضویت در فهرست انتظار"
            out = f"{head} «{s.title}»\n🗓 {s.when}\n💰 {self.money(s.price)}"
        else:
            out = "📋 خلاصهٔ سفارش:\n" + self._cart_text(u)
        if st["values"]:
            out += "\n\n" + self._fields_text(st["values"])
        return out

    # ==================== WORKSHOP ====================
    def _session(self, sid):
        return next((s for s in self.spec.workshop.sessions if s.id == sid), None)

    def _regs(self, sid) -> list:
        return self.data["regs"].setdefault(sid, [])

    def _wait(self, sid) -> list:
        return self.data["wait"].setdefault(sid, [])

    def _remaining(self, s) -> int:
        return max(0, s.capacity - len(self._regs(s.id)))

    def _user_regs(self, uid) -> list:
        return [s for s in self.spec.workshop.sessions if any(r["uid"] == uid for r in self._regs(s.id))]

    def _user_waits(self, uid) -> list:
        return [s for s in self.spec.workshop.sessions if any(r["uid"] == uid for r in self._wait(s.id))]

    def _needs_payment(self, s) -> bool:
        return self.spec.workshop.require_payment and s.price > 0

    def _invoice(self, s, entry) -> dict:
        return {"payload": f"W:{entry['code']}", "title": s.title[:32],
                "description": f"ثبت‌نام در کارگاه {s.title} — {s.when}"[:255], "amount": s.price}

    def _hold_out(self, uid, s, entry, head: str) -> Out:
        return Out(uid, f"{head}\n⏳ این جا تا {self._left_minutes(entry)} دقیقه برای شما نگه داشته می‌شود.\n"
                        f"💳 برای قطعی شدن ثبت‌نام، مبلغ {self.money(s.price)} را با صورت‌حساب زیر پرداخت کنید. "
                        f"بدون پرداخت، ثبت‌نام قطعی نمی‌شود.", self.main_buttons(), invoice=self._invoice(s, entry))

    def _w_resend_invoice(self, uid, s) -> Out:
        entry = next((r for r in self._regs(s.id) if r["uid"] == uid and r.get("status") == "pending"), None)
        if not entry:
            return self._menu(uid, f"پرداخت معوقی برای کارگاه «{s.title}» ندارید.")
        return self._hold_out(uid, s, entry, f"🧾 صورت‌حساب کارگاه «{s.title}»")

    def _promote(self, s) -> list[Out]:
        """Fill free seats from the waitlist; paid sessions get a payment hold instead of a confirmed seat."""
        outs, wait, regs = [], self._wait(s.id), self._regs(s.id)
        while self.spec.workshop.waitlist.enabled and wait and self._remaining(s) > 0:
            nxt = wait.pop(0)
            nxt["code"] = self._code("W")
            if self._needs_payment(s):
                nxt["status"], nxt["expires"] = "pending", self.now + self._hold_seconds()
                regs.append(nxt)
                outs.append(self._hold_out(nxt["uid"], s, nxt, f"🎉 خبر خوب! در کارگاه «{s.title}» جا باز شد."))
            else:
                regs.append(nxt)
                outs.append(Out(nxt["uid"], f"🎉 خبر خوب! در کارگاه «{s.title}» جا باز شد و ثبت‌نام شما قطعی شد.\n"
                                            f"🗓 {s.when}\n🔖 کد پیگیری: {nxt['code']}", self.main_buttons()))
        return outs

    def _waitlist_has_room(self, s) -> bool:
        w = self.spec.workshop.waitlist
        return w.enabled and (w.max_size == 0 or len(self._wait(s.id)) < w.max_size)

    def _workshop(self, uid, u, text) -> list[Out]:
        cfg = self.spec.workshop
        st = u["state"]
        if st:
            if st["step"] == "fields":
                return self._take_field(uid, u, text)
            if st["step"] == "confirm":
                if matches(text, L.CONFIRM):
                    return self._w_commit(uid, u)
                return [Out(uid, "لطفاً «تأیید» یا «انصراف» را انتخاب کنید.", [[L.CONFIRM, L.ABORT]])]
            if st["step"] == "wait_offer":
                if matches(text, L.W_JOIN_WAIT):
                    return self._start_fields(uid, u, cfg.collect_fields, {"sid": st["sid"], "mode": "wait"})
                u["state"] = None

        if matches(text, L.W_JOIN_WAIT):
            # Pressed outside the offer flow: use the last full session this user looked at.
            s = self._session(u.get("last_full"))
            if s and self._remaining(s) == 0 and self._waitlist_has_room(s):
                return self._start_fields(uid, u, cfg.collect_fields, {"sid": s.id, "mode": "wait"})
            return [self._menu(uid, "ابتدا از «کارگاه‌ها»، کارگاه تکمیل‌شدهٔ موردنظر را انتخاب کنید.")]
        if matches(text, L.W_LIST):
            return [self._w_list(uid)]
        for s in cfg.sessions:
            if matches(text, L.W_PAY + s.title):
                return [self._w_resend_invoice(uid, s)]
        if matches(text, L.W_MY):
            return [self._w_my(uid)]
        if cfg.allow_cancel and matches(text, L.W_CANCEL):
            return [self._w_cancel_menu(uid)]

        for s in cfg.sessions:
            if matches(text, L.W_SESSION + s.title):
                return self._w_select(uid, u, s)
            if cfg.allow_cancel and matches(text, L.W_CANCEL_ITEM + s.title):
                return self._w_cancel(uid, s)

        return [self._menu(uid, "متوجه نشدم 🤔 لطفاً از دکمه‌های زیر استفاده کنید.")]

    def _w_list(self, uid) -> Out:
        cfg = self.spec.workshop
        lines = [f"📅 کارگاه‌های {self.spec.business_name}:"]
        for s in cfg.sessions:
            rem = self._remaining(s)
            cap = f"👥 ظرفیت باقی‌مانده: {rem} از {s.capacity}" if rem else "⛔️ ظرفیت تکمیل است"
            if not rem and cfg.waitlist.enabled:
                cap += f" (فهرست انتظار: {len(self._wait(s.id))} نفر)"
            block = f"\n🔹 {s.title}\n🗓 {s.when}\n💰 {self.money(s.price)}\n{cap}"
            if s.description:
                block += f"\nℹ️ {s.description}"
            lines.append(block)
        lines.append("\nبرای ثبت‌نام، کارگاه موردنظر را انتخاب کنید 👇")
        buttons = [[L.W_SESSION + s.title] for s in cfg.sessions] + [[L.BACK]]
        return Out(uid, "\n".join(lines), buttons)

    def _w_select(self, uid, u, s) -> list[Out]:
        cfg = self.spec.workshop
        mine = next((r for r in self._regs(s.id) if r["uid"] == uid), None)
        if mine and mine.get("status") == "pending":
            return [self._hold_out(uid, s, mine, f"رزرو شما در کارگاه «{s.title}» در انتظار پرداخت است.")]
        if mine:
            return [self._menu(uid, f"شما قبلاً در کارگاه «{s.title}» ثبت‌نام کرده‌اید ✅")]
        pos = next((i + 1 for i, r in enumerate(self._wait(s.id)) if r["uid"] == uid), None)
        if pos:
            return [self._menu(uid, f"شما نفر {pos} فهرست انتظار «{s.title}» هستید ⏳")]
        if len(self._user_regs(uid)) >= cfg.max_per_user:
            return [self._menu(uid, f"هر نفر حداکثر در {cfg.max_per_user} کارگاه می‌تواند ثبت‌نام کند.")]
        if self._remaining(s) == 0:
            return [self._w_full(uid, u, s)]
        return self._start_fields(uid, u, cfg.collect_fields, {"sid": s.id, "mode": "reg"})

    def _w_full(self, uid, u, s) -> Out:
        if self._waitlist_has_room(s):
            u["state"] = {"step": "wait_offer", "sid": s.id}
            u["last_full"] = s.id
            return Out(uid, f"⛔️ ظرفیت کارگاه «{s.title}» تکمیل است.\n"
                            f"می‌خواهید در فهرست انتظار قرار بگیرید؟ در صورت آزاد شدن جا، به‌ترتیب نوبت ثبت‌نام می‌شوید.",
                       [[L.W_JOIN_WAIT], [L.BACK]])
        u["state"] = None
        if self.spec.workshop.waitlist.enabled:
            return self._menu(uid, f"⛔️ ظرفیت کارگاه «{s.title}» و فهرست انتظار آن تکمیل است.")
        return self._menu(uid, f"⛔️ متأسفانه ظرفیت کارگاه «{s.title}» تکمیل است.")

    def _w_commit(self, uid, u) -> list[Out]:
        st = u["state"]
        s = self._session(st["sid"])
        if not s:
            u["state"] = None
            return [self._menu(uid, "این کارگاه دیگر موجود نیست.")]
        entry = {"uid": uid, "name": u.get("name", ""), "fields": st["values"]}
        if st["mode"] == "reg":
            if self._remaining(s) == 0:
                return [self._w_full(uid, u, s)]
            entry["code"] = self._code("W")
            u["state"] = None
            if self._needs_payment(s):
                entry["status"], entry["expires"] = "pending", self.now + self._hold_seconds()
                self._regs(s.id).append(entry)
                return [self._hold_out(uid, s, entry, f"📝 اطلاعات شما برای کارگاه «{s.title}» ثبت شد.")]
            self._regs(s.id).append(entry)
            return [self._menu(uid, f"✅ ثبت‌نام شما در کارگاه «{s.title}» انجام شد.\n🗓 {s.when}\n"
                                    f"🔖 کد پیگیری: {entry['code']}")]
        if not self._waitlist_has_room(s):
            u["state"] = None
            return [self._menu(uid, f"⛔️ فهرست انتظار «{s.title}» تکمیل است.")]
        entry["code"] = self._code("Q")
        self._wait(s.id).append(entry)
        u["state"] = None
        pos = len(self._wait(s.id))
        return [self._menu(uid, f"⏳ شما نفر {pos} فهرست انتظار کارگاه «{s.title}» هستید.\n"
                                f"به محض آزاد شدن ظرفیت، ثبت‌نام شما قطعی و به شما اطلاع داده می‌شود.")]

    def _w_my(self, uid) -> Out:
        regs, waits = self._user_regs(uid), self._user_waits(uid)
        if not regs and not waits:
            return self._menu(uid, "شما هنوز در هیچ کارگاهی ثبت‌نام نکرده‌اید.")
        lines = ["🎟 ثبت‌نام‌های شما:"]
        pay_buttons = []
        for s in regs:
            r = next(r for r in self._regs(s.id) if r["uid"] == uid)
            if r.get("status") == "pending":
                lines.append(f"💳 {s.title} — در انتظار پرداخت (تا {self._left_minutes(r)} دقیقه)")
                pay_buttons.append([L.W_PAY + s.title])
            else:
                lines.append(f"✅ {s.title} — {s.when} (کد: {r['code']})")
        for s in waits:
            pos = next(i + 1 for i, r in enumerate(self._wait(s.id)) if r["uid"] == uid)
            lines.append(f"⏳ {s.title} — نفر {pos} فهرست انتظار")
        return Out(uid, "\n".join(lines), pay_buttons + self.main_buttons())

    def _w_cancel_menu(self, uid) -> Out:
        items = self._user_regs(uid) + [s for s in self._user_waits(uid)]
        if not items:
            return self._menu(uid, "ثبت‌نامی برای لغو ندارید.")
        return Out(uid, "کدام ثبت‌نام را می‌خواهید لغو کنید؟",
                   [[L.W_CANCEL_ITEM + s.title] for s in items] + [[L.BACK]])

    def _w_cancel(self, uid, s) -> list[Out]:
        regs, wait = self._regs(s.id), self._wait(s.id)
        if any(r["uid"] == uid for r in wait):
            wait[:] = [r for r in wait if r["uid"] != uid]
            return [self._menu(uid, f"شما از فهرست انتظار «{s.title}» خارج شدید.")]
        if not any(r["uid"] == uid for r in regs):
            return [self._menu(uid, f"شما در کارگاه «{s.title}» ثبت‌نام نکرده‌اید.")]
        was_paid = any(r["uid"] == uid and r.get("status") == "paid" for r in regs)
        regs[:] = [r for r in regs if r["uid"] != uid]
        msg = f"❌ ثبت‌نام شما در کارگاه «{s.title}» لغو شد."
        if was_paid:
            msg += "\nبرای بازگشت وجه با پشتیبانی تماس بگیرید." + (
                f"\n☎️ {self.spec.support_contact}" if self.spec.support_contact else "")
        return [self._menu(uid, msg)] + self._promote(s)

    # ==================== ORDER ====================
    def _item(self, iid):
        return next((i for i in self.spec.order.items if i.id == iid), None)

    def _clean_cart(self, u) -> list[str]:
        """Drop cart lines whose item was removed or became unavailable (e.g. after a new version)."""
        removed, keep = [], []
        for line in u["cart"]:
            it = self._item(line["item"])
            if it and it.available and (not it.options or line["option"] in it.options):
                keep.append(line)
            else:
                removed.append(it.name if it else "یک آیتم")
        u["cart"] = keep
        return removed

    def _totals(self, u):
        r = self.spec.order.rules
        sub = sum(self._item(l["item"]).price * l["qty"] for l in u["cart"])
        fee = 0
        if r.delivery and u["cart"]:
            fee = 0 if (r.free_delivery_over and sub >= r.free_delivery_over) else r.delivery_fee
        return sub, fee, sub + fee

    def _line_name(self, line) -> str:
        it = self._item(line["item"])
        return it.name + (f" ({line['option']})" if line["option"] else "")

    def _cart_text(self, u) -> str:
        if not u["cart"]:
            return "🛒 سبد خرید شما خالی است."
        lines = []
        for l in u["cart"]:
            it = self._item(l["item"])
            lines.append(f"• {self._line_name(l)} × {l['qty']} = {self.money(it.price * l['qty'])}")
        sub, fee, total = self._totals(u)
        lines.append(f"\nجمع اقلام: {self.money(sub)}")
        if self.spec.order.rules.delivery:
            lines.append(f"هزینهٔ ارسال: {self.money(fee) if fee else 'رایگان'}")
        lines.append(f"💳 مبلغ قابل پرداخت: {self.money(total)}")
        return "\n".join(lines)

    def _order_buttons(self) -> list[list[str]]:
        avail = [i for i in self.spec.order.items if i.available]
        rows = [[L.O_ADD + i.name for i in avail[k:k + 2]] for k in range(0, len(avail), 2)]
        return rows + [[L.O_CART, L.O_CHECKOUT], [L.BACK]]

    def _order(self, uid, u, text) -> list[Out]:
        cfg = self.spec.order
        st = u["state"]
        if st:
            if st["step"] == "fields":
                return self._take_field(uid, u, text)
            if st["step"] == "confirm":
                if matches(text, L.CONFIRM):
                    return self._o_commit(uid, u)
                return [Out(uid, "لطفاً «تأیید» یا «انصراف» را انتخاب کنید.", [[L.CONFIRM, L.ABORT]])]
            if st["step"] == "option":
                it = self._item(st["item"])
                for opt in it.options if it else []:
                    if matches(text, L.O_OPTION + opt):
                        u["state"] = None
                        return [self._o_add(uid, u, it, opt)]
                u["state"] = None

        if matches(text, L.O_MENU):
            return [self._o_menu(uid)]
        if matches(text, L.O_CART):
            return [self._o_cart(uid, u)]
        if matches(text, L.O_CLEAR):
            u["cart"] = []
            return [self._menu(uid, "🗑 سبد خرید خالی شد.")]
        if matches(text, L.O_CHECKOUT):
            return self._o_checkout(uid, u)

        for it in cfg.items:
            if matches(text, L.O_ADD + it.name):
                if not it.available:
                    return [Out(uid, f"«{it.name}» در حال حاضر موجود نیست.", self._order_buttons())]
                if it.options:
                    u["state"] = {"step": "option", "item": it.id}
                    return [Out(uid, f"«{it.name}» را با کدام گزینه می‌خواهید؟",
                                [[L.O_OPTION + o] for o in it.options] + [[L.BACK]])]
                return [self._o_add(uid, u, it, "")]
        for l in list(u["cart"]):
            if matches(text, L.O_REMOVE + self._line_name(l)):
                l["qty"] -= 1
                if l["qty"] <= 0:
                    u["cart"].remove(l)
                return [self._o_cart(uid, u)]
        return [self._menu(uid, "متوجه نشدم 🤔 لطفاً از دکمه‌های زیر استفاده کنید.")]

    def _o_menu(self, uid) -> Out:
        cfg = self.spec.order
        lines = [f"🍽 منوی {self.spec.business_name}:"]
        cats: dict[str, list] = {}
        for it in cfg.items:
            cats.setdefault(it.category or "", []).append(it)
        for cat, items in cats.items():
            if cat:
                lines.append(f"\n— {cat} —")
            for it in items:
                line = f"• {it.name}: {self.money(it.price)}"
                if it.options:
                    line += f" [{'، '.join(it.options)}]"
                if not it.available:
                    line += " (ناموجود)"
                if it.description:
                    line += f"\n   {it.description}"
                lines.append(line)
        r = cfg.rules
        notes = []
        if r.min_order_total:
            notes.append(f"حداقل سفارش: {self.money(r.min_order_total)}")
        if r.delivery:
            d = f"هزینهٔ ارسال: {self.money(r.delivery_fee)}" if r.delivery_fee else "ارسال رایگان"
            if r.delivery_fee and r.free_delivery_over:
                d += f" (رایگان برای سفارش بالای {self.money(r.free_delivery_over)})"
            notes.append(d)
        if r.open_hour is not None:
            notes.append(f"ساعت سفارش‌گیری: {r.open_hour} تا {r.close_hour}")
        if notes:
            lines.append("\n" + "\n".join("ℹ️ " + n for n in notes))
        lines.append("\nبرای افزودن به سبد، روی آیتم بزنید 👇")
        return Out(uid, "\n".join(lines), self._order_buttons())

    def _o_add(self, uid, u, it, opt) -> Out:
        r = self.spec.order.rules
        qty_item = sum(l["qty"] for l in u["cart"] if l["item"] == it.id)
        qty_all = sum(l["qty"] for l in u["cart"])
        if qty_item >= r.max_qty_per_item:
            return Out(uid, f"⚠️ از «{it.name}» حداکثر {r.max_qty_per_item} عدد در هر سفارش مجاز است.",
                       self._order_buttons())
        if qty_all >= r.max_items_per_order:
            return Out(uid, f"⚠️ هر سفارش حداکثر {r.max_items_per_order} قلم می‌تواند داشته باشد.",
                       self._order_buttons())
        line = next((l for l in u["cart"] if l["item"] == it.id and l["option"] == opt), None)
        if line:
            line["qty"] += 1
        else:
            line = {"item": it.id, "option": opt, "qty": 1}
            u["cart"].append(line)
        sub, _, _ = self._totals(u)
        return Out(uid, f"✅ «{self._line_name(line)}» به سبد اضافه شد (تعداد: {line['qty']}).\n"
                        f"جمع سبد: {self.money(sub)}", self._order_buttons())

    def _o_cart(self, uid, u) -> Out:
        removed = self._clean_cart(u)
        text = self._cart_text(u)
        if removed:
            text = f"⚠️ این موارد دیگر موجود نیستند و از سبد حذف شدند: {'، '.join(removed)}\n\n" + text
        if not u["cart"]:
            return Out(uid, text, [[L.O_MENU], [L.BACK]])
        rows = [[L.O_REMOVE + self._line_name(l)] for l in u["cart"]]
        return Out(uid, text, rows + [[L.O_CHECKOUT, L.O_CLEAR], [L.O_MENU, L.BACK]])

    def _o_checkout(self, uid, u) -> list[Out]:
        r = self.spec.order.rules
        removed = self._clean_cart(u)
        if removed:
            return [self._o_cart(uid, u)]
        if not u["cart"]:
            return [Out(uid, "🛒 سبد خرید شما خالی است. ابتدا از منو انتخاب کنید.", [[L.O_MENU], [L.BACK]])]
        if r.open_hour is not None:
            h, o, c = self._hour(), r.open_hour, r.close_hour
            is_open = (o <= h < c) if o < c else (h >= o or h < c)
            if not is_open:
                return [self._menu(uid, f"⏰ در حال حاضر سفارش‌گیری بسته است. ساعت سفارش‌گیری: {o} تا {c}")]
        sub, _, _ = self._totals(u)
        if sub < r.min_order_total:
            return [Out(uid, f"⚠️ حداقل مبلغ سفارش {self.money(r.min_order_total)} است. "
                             f"جمع فعلی سبد: {self.money(sub)}", self._order_buttons())]
        fields = list(self.spec.order.collect_fields)
        if r.delivery and "address" not in fields:
            fields.append("address")
        return self._start_fields(uid, u, fields, {})

    def _o_commit(self, uid, u) -> list[Out]:
        if self._clean_cart(u) or not u["cart"]:
            u["state"] = None
            return [self._o_cart(uid, u)]
        sub, fee, total = self._totals(u)
        order = {
            "code": self._code("O"), "uid": uid, "name": u.get("name", ""),
            "lines": [{"item": self._line_name(l), "qty": l["qty"], "price": self._item(l["item"]).price}
                      for l in u["cart"]],
            "subtotal": sub, "delivery_fee": fee, "total": total,
            "fields": u["state"]["values"], "status": "new",
        }
        u["cart"], u["state"] = [], None
        if self.spec.order.require_payment and total > 0:
            order["status"], order["expires"] = "pending_payment", self.now + self._hold_seconds()
            self.data["orders"].append(order)
            return [Out(uid, f"📝 سفارش {order['code']} ثبت شد و تا {self._left_minutes(order)} دقیقه منتظر پرداخت است.\n"
                             f"💳 مبلغ قابل پرداخت: {self.money(total)}\nبدون پرداخت، سفارش قطعی نمی‌شود.",
                        self.main_buttons(),
                        invoice={"payload": f"O:{order['code']}", "title": f"سفارش {order['code']}"[:32],
                                 "description": f"سفارش از {self.spec.business_name}"[:255], "amount": total})]
        self.data["orders"].append(order)
        return [self._menu(uid, f"✅ سفارش شما ثبت شد.\n🔖 شماره سفارش: {order['code']}\n"
                                f"💳 مبلغ کل: {self.money(total)}\nاز خرید شما متشکریم 🙏")]
