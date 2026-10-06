"""BotSpec: the declarative description of a bot.

The agent never writes executable code. It turns the owner's natural-language request
into a BotSpec, which the deterministic engine (engine.py) executes. This keeps every
generated bot safe, testable and versionable.
"""
from typing import Literal, Optional

from pydantic import BaseModel, Field, model_validator

FieldName = Literal["name", "phone", "address", "note"]


class Session(BaseModel):
    id: str = Field(description="Stable short id, e.g. 'w1'. Never change ids of existing sessions.")
    title: str
    when: str = Field(description="Human readable date/time, e.g. 'پنجشنبه ۱۵ آبان، ساعت ۱۰ تا ۱۲'")
    capacity: int = Field(ge=1, le=5000)
    price: int = Field(default=0, ge=0, description="0 means free")
    description: str = ""


class Waitlist(BaseModel):
    enabled: bool = False
    max_size: int = Field(default=0, ge=0, description="0 = unlimited")


class WorkshopConfig(BaseModel):
    sessions: list[Session] = Field(min_length=1)
    allow_cancel: bool = True
    max_per_user: int = Field(default=1, ge=1, description="Max number of sessions one user may register for")
    waitlist: Waitlist = Waitlist()
    collect_fields: list[FieldName] = ["name", "phone"]
    require_payment: bool = Field(default=False, description="Online payment (Bale/Telegram invoice) is required before a "
                                  "registration for a paid session is confirmed; the seat is held meanwhile")
    payment_hold_minutes: int = Field(default=15, ge=5, le=120, description="How long a seat is held awaiting payment")


class MenuItem(BaseModel):
    id: str = Field(description="Stable short id, e.g. 'i1'")
    name: str
    price: int = Field(ge=0)
    category: str = ""
    available: bool = True
    options: list[str] = Field(default_factory=list, description="e.g. ['کوچک','بزرگ']; customer must pick one")
    description: str = ""


class OrderRules(BaseModel):
    min_order_total: int = Field(default=0, ge=0)
    max_qty_per_item: int = Field(default=10, ge=1)
    max_items_per_order: int = Field(default=30, ge=1)
    delivery: bool = False
    delivery_fee: int = Field(default=0, ge=0)
    free_delivery_over: int = Field(default=0, ge=0, description="0 = never free")
    open_hour: Optional[int] = Field(default=None, ge=0, le=23, description="Ordering opens at this hour (local)")
    close_hour: Optional[int] = Field(default=None, ge=0, le=24, description="Ordering closes at this hour (local)")


class OrderConfig(BaseModel):
    items: list[MenuItem] = Field(min_length=1)
    rules: OrderRules = OrderRules()
    collect_fields: list[FieldName] = ["name", "phone"]
    require_payment: bool = Field(default=False, description="Orders must be paid online (invoice) before they are accepted")
    payment_hold_minutes: int = Field(default=15, ge=5, le=120, description="How long an unpaid order stays valid")


class BotSpec(BaseModel):
    template: Literal["workshop", "order"]
    business_name: str = Field(min_length=1)
    welcome_message: str = Field(min_length=1)
    currency: str = "تومان"
    support_contact: str = ""
    workshop: Optional[WorkshopConfig] = None
    order: Optional[OrderConfig] = None

    @model_validator(mode="after")
    def _check(self):
        if self.template == "workshop":
            if not self.workshop:
                raise ValueError("template 'workshop' requires the 'workshop' section")
            ids = [s.id for s in self.workshop.sessions]
            titles = [s.title.strip() for s in self.workshop.sessions]
            if len(set(ids)) != len(ids):
                raise ValueError("session ids must be unique")
            if len(set(titles)) != len(titles):
                raise ValueError("session titles must be unique")
            self.order = None
        else:
            if not self.order:
                raise ValueError("template 'order' requires the 'order' section")
            ids = [i.id for i in self.order.items]
            names = [i.name.strip() for i in self.order.items]
            if len(set(ids)) != len(ids):
                raise ValueError("item ids must be unique")
            if len(set(names)) != len(names):
                raise ValueError("item names must be unique")
            r = self.order.rules
            if (r.open_hour is None) != (r.close_hour is None):
                raise ValueError("open_hour and close_hour must be set together")
            self.workshop = None
        return self


EXAMPLE_WORKSHOP = {
    "template": "workshop",
    "business_name": "آموزشگاه نقاشی رنگین",
    "welcome_message": "سلام! به ربات ثبت‌نام کارگاه‌های آموزشگاه رنگین خوش آمدید 🎨",
    "currency": "تومان",
    "support_contact": "09120000000",
    "workshop": {
        "sessions": [
            {"id": "w1", "title": "آبرنگ مقدماتی", "when": "پنجشنبه ساعت ۱۰ تا ۱۲", "capacity": 12, "price": 450000},
        ],
        "allow_cancel": True,
        "max_per_user": 1,
        "waitlist": {"enabled": False, "max_size": 0},
        "collect_fields": ["name", "phone"],
    },
}

EXAMPLE_ORDER = {
    "template": "order",
    "business_name": "کافه بهار",
    "welcome_message": "سلام! منوی کافه بهار در خدمت شماست ☕️",
    "currency": "تومان",
    "support_contact": "",
    "order": {
        "items": [
            {"id": "i1", "name": "اسپرسو", "price": 85000, "category": "نوشیدنی گرم", "available": True, "options": []},
            {"id": "i2", "name": "پیتزا مخصوص", "price": 320000, "category": "غذا", "available": True,
             "options": ["متوسط", "بزرگ"]},
        ],
        "rules": {"min_order_total": 150000, "max_qty_per_item": 5, "max_items_per_order": 20, "delivery": True,
                  "delivery_fee": 40000, "free_delivery_over": 600000, "open_hour": 9, "close_hour": 23},
        "collect_fields": ["name", "phone", "address"],
    },
}
