import { useState } from 'react'
import { CheckCircle2, ExternalLink, Rocket, AlertTriangle } from 'lucide-react'
import { api } from '../api'
import { Badge, Button, Input } from './ui'

const PLATFORMS = {
  bale: {
    name: 'بله', link: (u) => `https://ble.ir/${u}`,
    steps: ['در پیام‌رسان بله، بات @botfather را باز کنید.', 'دستور /newbot را بفرستید و نام و شناسهٔ بات را انتخاب کنید.', 'توکنی که بات‌فادر می‌دهد را این‌جا وارد کنید.'],
  },
  telegram: {
    name: 'تلگرام', link: (u) => `https://t.me/${u}`,
    steps: ['در تلگرام، @BotFather را باز کنید.', 'دستور /newbot را بفرستید و نام و شناسهٔ بات را انتخاب کنید.', 'توکن دریافتی را این‌جا وارد کنید.'],
  },
}

export default function PublishPanel({ bot, version, onChange }) {
  const [platform, setPlatform] = useState(bot.platform || 'bale')
  const [token, setToken] = useState('')
  const [loading, setLoading] = useState(false)
  const [msg, setMsg] = useState(null)
  const live = bot.versions.find((v) => v.is_live)
  const p = PLATFORMS[platform]
  const canReuse = bot.has_token && bot.platform === platform
  const failed = (version.test_report?.failed || 0) > 0

  const publish = async () => {
    setLoading(true); setMsg(null)
    try {
      const r = await api(`/api/bots/${bot.id}/publish`, { method: 'POST', body: { version_id: version.id, platform, token } })
      setMsg({ ok: true, text: `نسخهٔ ${r.version} روی ${p.name} منتشر شد (${r.mode === 'webhook' ? 'وب‌هوک' : 'polling'}).` })
      setToken('')
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
