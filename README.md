# BotLab

ایجنتی که از روی توضیح عادی صاحب کسب‌وکار، بات **بله / تلگرام** می‌سازد، ابهام‌ها را می‌پرسد، در محیط آزمایشی تست
می‌کند، منتشر می‌کند و تغییرات بعدی را با نسخهٔ جدید و آزمون رگرسیون اعمال می‌کند.

قالب‌های نسخهٔ اول: **رزرو کارگاه** (ظرفیت، ثبت‌نام، لغو، فهرست انتظار) و **ثبت سفارش از منو** (سبد، گزینه‌ها، حداقل
سفارش، هزینهٔ ارسال، ساعت کاری).

## معماری در یک نگاه

```
React (Vite, RTL)  ──HTTP──>  FastAPI
                               ├─ agent.py     ایجنت: تحلیل → سؤال ابهام → ساخت Spec → نوشتن آزمون → اجرا → اصلاح → نسخه
                               ├─ spec.py      BotSpec (Pydantic) — توصیف اعلانی بات
                               ├─ engine.py    موتور قطعی اجرای Spec (همان موتور در شبیه‌ساز، تست و بات واقعی)
                               ├─ testing.py   اجرای آزمون‌ها در حافظه + تولید خودکار آزمون‌های پایه
                               ├─ platforms.py اتصال بله/تلگرام (webhook یا long-polling)
                               └─ db.py        SQLite (لوکال) / Postgres (Neon)
LLM: هر سرویس OpenAI-compatible (پیش‌فرض Gemini 2.5 Flash رایگان)
```

ایجنت هیچ‌وقت کد اجرایی تولید نمی‌کند؛ خروجی او یک `BotSpec` اعتبارسنجی‌شده است. به همین دلیل بات‌ها امن،
قابل آزمون و نسخه‌پذیرند.

## اجرای لوکال

```bash
# backend
cd backend
python -m venv .venv
.venv/Scripts/pip install -r requirements.txt     # لینوکس/مک: .venv/bin/pip
cp .env.example .env                              # LLM_API_KEY را پر کنید
.venv/Scripts/uvicorn app.main:app --reload --port 8000

# frontend (ترمینال دوم)
cd frontend
npm install
npm run dev        # http://localhost:5173
```

یا فرانت را build کنید (`npm run build`) تا FastAPI خودش آن را روی `http://localhost:8000` سرو کند.

آزمون سرتاسری (بدون مصرف LLM، با مدل ساختگی):

```bash
cd backend && .venv/Scripts/python tests/test_flow.py
```

## دیپلوی رایگان (Render + Neon)

1. در [neon.tech](https://neon.tech) یک دیتابیس رایگان بسازید و Connection string را بردارید.
2. کلید رایگان Gemini را از [aistudio.google.com/apikey](https://aistudio.google.com/apikey) بگیرید.
3. پروژه را در GitHub بگذارید؛ در [render.com](https://render.com) گزینهٔ **New → Blueprint** را بزنید و مخزن را
   انتخاب کنید (`render.yaml` خوانده می‌شود).
4. مقادیر `DATABASE_URL` و `LLM_API_KEY` را وارد کنید. آدرس عمومی به‌طور خودکار برای webhook بات‌ها استفاده می‌شود.

نکته: سرویس رایگان Render پس از ۱۵ دقیقه بی‌کاری می‌خوابد و اولین درخواست حدود ۳۰–۶۰ ثانیه طول می‌کشد. قبل از
دموی داوری یک بار صفحه را باز کنید.
