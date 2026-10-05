import { useEffect, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { Bot, CalendarCheck, ChevronLeft, ShoppingBag, Sparkles } from 'lucide-react'
import { api } from '../api'
import { useUser } from '../App'
import { Badge, Button, Card, Empty, Spinner, TopBar } from '../components/ui'

export const EXAMPLES = [
  {
    icon: CalendarCheck, title: 'رزرو کارگاه',
    text: 'من آموزشگاه سفالگری «گِل‌سان» را دارم. یک بات می‌خواهم که مردم بتوانند در کارگاه‌های این هفته ثبت‌نام کنند: کارگاه چرخ سفال پنجشنبه ساعت ۱۰ با ظرفیت ۸ نفر و قیمت ۶۵۰ هزار تومان، و کارگاه نقاشی روی سفال جمعه ساعت ۱۶ با ظرفیت ۱۲ نفر و قیمت ۴۵۰ هزار تومان. اسم و شماره موبایل بگیرد و هر نفر فقط در یک کارگاه ثبت‌نام کند.',
  },
  {
    icon: ShoppingBag, title: 'سفارش از منو',
    text: 'کافه‌ام به اسم «کافه دنج» است. بات سفارش می‌خواهم با این منو: اسپرسو ۸۵ هزار، لاته ۱۱۰ هزار، کیک شکلاتی ۱۴۰ هزار، ساندویچ مرغ ۲۲۰ هزار. لاته کوچک و بزرگ دارد. حداقل سفارش ۲۰۰ هزار تومان باشد و ارسال ۴۰ هزار تومان.',
  },
]

export function templateBadge(t) {
  if (t === 'workshop') return <Badge tone="violet"><CalendarCheck className="size-3" />رزرو کارگاه</Badge>
  if (t === 'order') return <Badge tone="amber"><ShoppingBag className="size-3" />ثبت سفارش</Badge>
  return <Badge>در حال طراحی</Badge>
}

export function statusBadge(b) {
  if (b.live_version) return <Badge tone="green"><span className="size-1.5 rounded-full bg-emerald-500" />منتشرشده · نسخهٔ {b.live_version}</Badge>
  if (b.latest_version) return <Badge tone="blue">پیش‌نویس · نسخهٔ {b.latest_version}</Badge>
  return <Badge>بدون نسخه</Badge>
}

export default function Dashboard() {
  const { user, logout } = useUser()
  const nav = useNavigate()
  const [bots, setBots] = useState(null)
  const [text, setText] = useState('')
  const [creating, setCreating] = useState(false)
  const [err, setErr] = useState('')

  useEffect(() => { api('/api/bots').then(setBots).catch((e) => setErr(e.message)) }, [])

  const create = async () => {
    if (!text.trim()) return
    setCreating(true); setErr('')
    try {
      const { id } = await api('/api/bots', { method: 'POST', body: { message: text } })
      nav(`/bots/${id}`)
    } catch (e) { setErr(e.message); setCreating(false) }
  }

  return (
    <div className="min-h-full">
      <TopBar user={user} onLogout={logout} />
      <main className="mx-auto max-w-5xl px-4 py-8">
        <h1 className="text-2xl font-bold">سلام {user.name} 👋</h1>
        <p className="mt-1 text-slate-600">بات جدیدی می‌خواهید؟ کافی است توضیح دهید چه کاری باید انجام دهد.</p>

        <Card className="mt-6 p-5">
          <div className="mb-3 flex items-center gap-2 font-medium"><Sparkles className="size-5 text-brand-600" />ساخت بات جدید با ایجنت</div>
          <textarea
            value={text} onChange={(e) => setText(e.target.value)} rows={4}
            placeholder="مثلاً: یک بات برای ثبت‌نام در کارگاه‌های آموزشی‌ام می‌خواهم که ظرفیت را کنترل کند…"
            className="w-full resize-none rounded-xl border border-slate-200 p-3.5 text-sm leading-7 outline-none focus:border-brand-500 focus:ring-4 focus:ring-brand-100"
            onKeyDown={(e) => { if (e.key === 'Enter' && (e.ctrlKey || e.metaKey)) create() }}
          />
          <div className="mt-3 flex flex-wrap items-center gap-2">
            <span className="text-xs text-slate-500">نمونه‌ها:</span>
            {EXAMPLES.map(({ icon: Icon, title, text: t }) => (
              <button key={title} onClick={() => setText(t)}
                className="inline-flex items-center gap-1.5 rounded-full border border-slate-200 px-3 py-1 text-xs text-slate-600 hover:border-brand-300 hover:bg-brand-50 cursor-pointer">
                <Icon className="size-3.5" />{title}
              </button>
            ))}
            <Button onClick={create} loading={creating} disabled={!text.trim()} className="ms-auto">
              شروع ساخت <ChevronLeft className="size-4" />
            </Button>
          </div>
          {err && <div className="mt-3 rounded-xl bg-rose-50 px-3 py-2 text-sm text-rose-700">{err}</div>}
        </Card>

        <h2 className="mt-10 mb-4 text-lg font-bold">بات‌های من</h2>
        {bots === null ? (
          <div className="grid place-items-center py-10"><Spinner className="size-6 text-brand-500" /></div>
        ) : bots.length === 0 ? (
          <Card><Empty icon={Bot} title="هنوز باتی نساخته‌اید">اولین بات خود را با نوشتن توضیح در کادر بالا بسازید.</Empty></Card>
        ) : (
          <div className="grid gap-4 sm:grid-cols-2">
            {bots.map((b) => (
              <button key={b.id} onClick={() => nav(`/bots/${b.id}`)} className="text-right cursor-pointer">
                <Card className="p-5 transition hover:border-brand-300 hover:shadow-md">
                  <div className="flex items-start gap-3">
                    <span className="grid size-11 shrink-0 place-items-center rounded-xl bg-brand-50 text-brand-600"><Bot className="size-6" /></span>
                    <div className="min-w-0 flex-1">
                      <div className="truncate font-bold">{b.name}</div>
                      <div className="mt-2 flex flex-wrap gap-1.5">{templateBadge(b.template)}{statusBadge(b)}</div>
                      {b.bot_username && <div className="mt-2 text-xs text-slate-500" dir="ltr">@{b.bot_username}</div>}
                    </div>
                    {b.agent_status === 'running' && <Spinner className="size-4 text-brand-500" />}
                  </div>
                </Card>
              </button>
            ))}
          </div>
        )}
      </main>
    </div>
  )
}
