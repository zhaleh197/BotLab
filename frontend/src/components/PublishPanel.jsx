import { useEffect, useState } from 'react'
import { CheckCircle2, ExternalLink, Rocket, AlertTriangle, CreditCard, Wifi, WifiOff } from 'lucide-react'
import { api } from '../api'
import { Badge, Button, Input } from './ui'

const PLATFORMS = {
  bale: {
    name: 'بله', link: (u) => `https://ble.ir/${u}`,
    steps: ['در پیام‌رسان بله، بات @botfather را باز کنید.', 'دستور /newbot را بفرستید و نام و شناسهٔ بات را انتخاب کنید.', 'توکنی که بات‌فادر می‌دهد را این‌جا وارد کنید.'],
    payHelp: 'توکن پرداخت کیف پول را از @botfather بله (بخش پرداخت بات) بگیرید؛ مبلغ به ریال از کارت مشتری کسر و به کیف پول شما واریز می‌شود.',
    testToken: 'WALLET-TEST-1111111111111111',
  },
  telegram: {
    name: 'تلگرام', link: (u) => `https://t.me/${u}`,
    steps: ['در تلگرام، @BotFather را باز کنید.', 'دستور /newbot را بفرستید و نام و شناسهٔ بات را انتخاب کنید.', 'توکن دریافتی را این‌جا وارد کنید.'],
    payHelp: 'در @BotFather: ‏/mybots ← بات ← Payments ← یک درگاه (مثلاً Stripe) در حالت Test. در حالت آزمایشی با کارت 4242 4242 4242 4242 پرداخت کنید. درگاه‌های تلگرام ریال ندارند؛ مبلغ به دلار تبدیل می‌شود.',
    testToken: '',
  },
}

export default function PublishPanel({ bot, version, onChange }) {
  const [platform, setPlatform] = useState(bot.platform || 'bale')
  const [token, setToken] = useState('')
  const [payToken, setPayToken] = useState('')
  const [reach, setReach] = useState(null)
  useEffect(() => { api('/api/health/platforms').then(setReach).catch(() => {}) }, [])
  const [loading, setLoading] = useState(false)
  const [msg, setMsg] = useState(null)
  const live = bot.versions.find((v) => v.is_live)
  const p = PLATFORMS[platform]
  const canReuse = bot.has_token && bot.platform === platform
  const failed = (version.test_report?.failed || 0) > 0
  const cfg = version.spec.workshop || version.spec.order
  const needsPay = !!cfg?.require_payment
  const reuseePay = bot.has_payment_token && bot.platform === platform

  const publish = async () => {
    setLoading(true); setMsg(null)
    try {
      const r = await api(`/api/bots/${bot.id}/publish`, { method: 'POST', body: { version_id: version.id, platform, token, payment_token: payToken } })
      setMsg({ ok: true, text: `نسخهٔ ${r.version} روی ${p.name} منتشر شد (${r.mode === 'webhook' ? 'وب‌هوک' : 'polling'}).` })
      setToken(''); setPayToken('')
      onChange()
    } catch (e) { setMsg({ ok: false, text: e.message }) } finally { setLoading(false) }
  }

  const unpublish = async () => {
    if (!confirm('بات از دسترس کاربران خارج شود؟')) return
    await api(`/api/bots/${bot.id}/unpublish`, { method: 'POST' })
    onChange()
  }

  return (
    <div className="mx-auto max-w-2xl space-y-5 p-5">
      {live ? (
        <div className="flex flex-wrap items-center gap-3 rounded-2xl bg-emerald-50 p-4 ring-1 ring-emerald-200">
          <CheckCircle2 className="size-6 text-emerald-600" />
          <div className="flex-1">
            <div className="font-bold text-emerald-800">بات فعال است — نسخهٔ {live.number} روی {PLATFORMS[bot.platform].name}</div>
            {bot.bot_username && (
              <a href={PLATFORMS[bot.platform].link(bot.bot_username)} target="_blank" rel="noreferrer"
                className="mt-1 inline-flex items-center gap-1 text-sm text-emerald-700 underline" dir="ltr">
                @{bot.bot_username}<ExternalLink className="size-3.5" />
              </a>
            )}
          </div>
          <Button variant="danger" onClick={unpublish} className="!py-1.5 text-xs">توقف بات</Button>
        </div>
      ) : (
        <div className="rounded-2xl bg-slate-50 p-4 text-sm text-slate-600 ring-1 ring-slate-200">این بات هنوز منتشر نشده است.</div>
      )}

      <div className="rounded-2xl border border-slate-200 p-5">
        <div className="mb-4 flex items-center gap-2 font-bold"><Rocket className="size-5 text-brand-600" />انتشار نسخهٔ {version.number}
          {version.is_live && <Badge tone="green">همین نسخه منتشر شده</Badge>}</div>

        <div className="mb-4 grid grid-cols-2 gap-2">
          {Object.entries(PLATFORMS).map(([k, v]) => (
            <button key={k} onClick={() => setPlatform(k)}
              className={`rounded-xl border py-3 text-sm font-medium transition cursor-pointer ${platform === k ? 'border-brand-500 bg-brand-50 text-brand-700' : 'border-slate-200 hover:bg-slate-50'}`}>
              {v.name}
            </button>
          ))}
        </div>

        <ol className="mb-4 list-decimal space-y-1 pr-5 text-sm leading-7 text-slate-600">{p.steps.map((s) => <li key={s}>{s}</li>)}</ol>

        <Input label="توکن بات" dir="ltr" value={token} onChange={(e) => setToken(e.target.value)}
          placeholder={canReuse ? `توکن ذخیره‌شده: ${bot.token_hint}` : '123456789:ABCdef…'}
          hint={canReuse ? 'اگر خالی بگذارید از توکن ذخیره‌شده استفاده می‌شود.' : 'توکن فقط برای اتصال بات استفاده می‌شود.'} />

        {reach?.[platform] && (
          <div className={`mt-3 flex items-center gap-2 text-xs ${reach[platform].reachable ? 'text-emerald-700' : 'text-rose-700'}`}>
            {reach[platform].reachable ? <Wifi className="size-3.5" /> : <WifiOff className="size-3.5" />}
            {reach[platform].reachable ? `سرور به ${p.name} دسترسی دارد.` : `سرور به ${p.name} دسترسی ندارد؛ انتشار روی این پلتفرم از این سرور ممکن نیست.`}
          </div>
        )}

        <div className={`mt-5 rounded-2xl border p-4 ${needsPay ? 'border-emerald-200 bg-emerald-50/40' : 'border-slate-200'}`}>
          <div className="mb-2 flex items-center gap-2 text-sm font-bold"><CreditCard className="size-4 text-emerald-600" />پرداخت آنلاین
            {needsPay ? <Badge tone="green">این نسخه پرداخت می‌خواهد</Badge> : <Badge>در این نسخه غیرفعال</Badge>}</div>
          <p className="mb-3 text-xs leading-6 text-slate-600">{p.payHelp}</p>
          <Input dir="ltr" value={payToken} onChange={(e) => setPayToken(e.target.value)}
            placeholder={reuseePay ? `توکن ذخیره‌شده: ${bot.payment_hint}` : 'توکن پرداخت (provider token)'}
            hint={reuseePay ? (bot.payment_test ? 'توکن فعلی آزمایشی است؛ پولی جابه‌جا نمی‌شود.' : 'توکن فعلی واقعی است؛ پرداخت‌ها واقعی‌اند.') : ''} />
          {p.testToken && (
            <button type="button" onClick={() => setPayToken(p.testToken)}
              className="mt-2 text-xs text-brand-700 underline cursor-pointer">استفاده از توکن آزمایشی بله (بدون پول واقعی)</button>
          )}
          {needsPay && !payToken.trim() && !reuseePay && (
            <div className="mt-2 text-xs text-amber-700">بدون توکن پرداخت، مشتری صورت‌حساب دریافت نمی‌کند و ثبت‌نام‌های پولی قطعی نمی‌شوند.</div>
          )}
        </div>

        {failed && (
          <div className="mt-4 flex gap-2 rounded-xl bg-amber-50 p-3 text-sm text-amber-800">
            <AlertTriangle className="size-4 shrink-0" />برخی آزمون‌های این نسخه ناموفق بوده‌اند. پیشنهاد می‌شود ابتدا تب «آزمون‌ها» را بررسی کنید.
          </div>
        )}
        {msg && <div className={`mt-4 rounded-xl px-3 py-2 text-sm ${msg.ok ? 'bg-emerald-50 text-emerald-700' : 'bg-rose-50 text-rose-700'}`}>{msg.text}</div>}

        <Button onClick={publish} loading={loading} disabled={!token.trim() && !canReuse} className="mt-4 w-full py-3">
          {live ? `انتشار نسخهٔ ${version.number} به‌جای نسخهٔ ${live.number}` : `انتشار روی ${p.name}`}
        </Button>
        <p className="mt-3 text-xs leading-6 text-slate-500">داده‌های واقعی (ثبت‌نام‌ها و سفارش‌ها) با انتشار نسخهٔ جدید حفظ می‌شوند.</p>
      </div>
    </div>
  )
}
