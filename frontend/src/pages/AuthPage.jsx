import { useState } from 'react'
import { FlaskConical, MessagesSquare, Rocket, RefreshCcw } from 'lucide-react'
import { api } from '../api'
import { useUser } from '../App'
import { Button, Card, Input, Logo } from '../components/ui'

const features = [
  { icon: MessagesSquare, title: 'به زبان خودتان بگویید', text: 'نیازتان را مثل گفتگو با یک همکار توضیح دهید؛ ایجنت ابهام‌ها را می‌پرسد.' },
  { icon: FlaskConical, title: 'قبل از انتشار آزموده می‌شود', text: 'ایجنت سناریوهای آزمون می‌نویسد، در محیط آزمایشی اجرا می‌کند و اشکال‌ها را خودش رفع می‌کند.' },
  { icon: Rocket, title: 'انتشار با یک کلیک', text: 'بات روی بله یا تلگرام منتشر می‌شود و ثبت‌نام‌ها و سفارش‌ها را در داشبورد می‌بینید.' },
  { icon: RefreshCcw, title: 'تغییر با یک جمله', text: '«فهرست انتظار اضافه کن» — ایجنت نسخهٔ جدید می‌سازد و دوباره آزمایش می‌کند.' },
]

export default function AuthPage() {
  const { login } = useUser()
  const [mode, setMode] = useState('register')
  const [form, setForm] = useState({ name: '', email: '', password: '' })
  const [err, setErr] = useState('')
  const [loading, setLoading] = useState(false)
  const set = (k) => (e) => setForm({ ...form, [k]: e.target.value })

  const submit = async (e) => {
    e.preventDefault()
    setErr(''); setLoading(true)
    try {
      const body = mode === 'register' ? form : { email: form.email, password: form.password }
      login(await api(`/api/auth/${mode}`, { method: 'POST', body }))
    } catch (e) { setErr(e.message) } finally { setLoading(false) }
  }

  return (
    <div className="min-h-full bg-gradient-to-br from-brand-50 via-white to-violet-50">
      <div className="mx-auto grid max-w-6xl gap-10 px-4 py-10 lg:grid-cols-[1.2fr_1fr] lg:py-20">
        <div className="flex flex-col justify-center">
          <Logo />
          <h1 className="mt-8 text-3xl font-bold leading-[1.6] sm:text-4xl sm:leading-[1.5]">
            بات بله و تلگرام کسب‌وکارتان را
            <span className="bg-gradient-to-l from-brand-600 to-violet-600 bg-clip-text text-transparent"> فقط با توضیح دادن </span>
            بسازید
          </h1>
          <p className="mt-4 max-w-xl text-slate-600 leading-8">
            باتساز یک ایجنت هوشمند است که بات رزرو کارگاه یا ثبت سفارش شما را می‌سازد، آزمایش می‌کند، منتشر می‌کند و
            هر وقت خواستید تغییرش می‌دهد — بدون یک خط کدنویسی.
          </p>
          <div className="mt-8 grid gap-3 sm:grid-cols-2">
            {features.map(({ icon: Icon, title, text }) => (
              <div key={title} className="rounded-2xl border border-white bg-white/70 p-4 shadow-sm">
                <Icon className="size-5 text-brand-600" />
                <div className="mt-2 font-medium">{title}</div>
                <div className="mt-1 text-sm leading-6 text-slate-600">{text}</div>
              </div>
            ))}
          </div>
        </div>

        <Card className="self-center p-6 sm:p-8">
          <div className="mb-6 grid grid-cols-2 rounded-xl bg-slate-100 p-1 text-sm">
            {[['register', 'ساخت حساب'], ['login', 'ورود']].map(([m, t]) => (
              <button key={m} onClick={() => { setMode(m); setErr('') }}
                className={`rounded-lg py-2 font-medium transition cursor-pointer ${mode === m ? 'bg-white shadow-sm text-ink' : 'text-slate-500'}`}>
                {t}
              </button>
            ))}
          </div>
          <form onSubmit={submit} className="space-y-4">
            {mode === 'register' && <Input label="نام شما" value={form.name} onChange={set('name')} required placeholder="مثلاً مریم احمدی" />}
            <Input label="ایمیل" type="email" dir="ltr" value={form.email} onChange={set('email')} required placeholder="you@example.com" />
            <Input label="رمز عبور" type="password" dir="ltr" value={form.password} onChange={set('password')} required minLength={6}
              hint={mode === 'register' ? 'حداقل ۶ کاراکتر' : ''} />
            {err && <div className="rounded-xl bg-rose-50 px-3 py-2 text-sm text-rose-700">{err}</div>}
            <Button type="submit" loading={loading} className="w-full py-3">
              {mode === 'register' ? 'ساخت حساب و شروع' : 'ورود'}
            </Button>
          </form>
        </Card>
      </div>
    </div>
  )
}
