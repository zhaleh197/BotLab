import { useEffect, useState } from 'react'
import { Database, RefreshCw } from 'lucide-react'
import { api, fmt } from '../api'
import { Badge, Empty, Spinner } from './ui'

function People({ rows, emptyText }) {
  if (!rows.length) return <div className="py-2 text-sm text-slate-400">{emptyText}</div>
  return (
    <table className="w-full text-sm">
      <thead><tr className="text-right text-slate-500"><th className="py-1.5 font-normal">#</th><th className="font-normal">کد</th><th className="font-normal">نام</th><th className="font-normal">موبایل</th></tr></thead>
      <tbody>{rows.map((r, i) => (
        <tr key={i} className="border-t border-slate-100"><td className="py-2">{i + 1}</td><td dir="ltr" className="text-right">{r.code}</td><td>{r.name || '—'}</td><td dir="ltr" className="text-right">{r.phone || '—'}</td></tr>
      ))}</tbody>
    </table>
  )
}

export default function DataView({ bot }) {
  const [scope, setScope] = useState(bot.live_version ? 'live' : 'sandbox')
  const [data, setData] = useState(null)
  const load = () => { setData(null); api(`/api/bots/${bot.id}/data?scope=${scope}`).then(setData).catch(() => setData({ template: null })) }
  useEffect(load, [bot.id, scope]) // eslint-disable-line react-hooks/exhaustive-deps

  return (
    <div className="space-y-4 p-5">
      <div className="flex items-center gap-2">
        {[['live', 'داده‌های واقعی'], ['sandbox', 'داده‌های شبیه‌ساز']].map(([k, t]) => (
          <button key={k} onClick={() => setScope(k)}
            className={`rounded-full px-3 py-1.5 text-sm cursor-pointer ${scope === k ? 'bg-ink text-white' : 'bg-slate-100 text-slate-600'}`}>{t}</button>
        ))}
        <button onClick={load} className="ms-auto rounded-lg p-2 text-slate-500 hover:bg-slate-100 cursor-pointer" title="به‌روزرسانی"><RefreshCw className="size-4" /></button>
      </div>
      {!data ? <div className="grid place-items-center py-10"><Spinner className="size-6 text-brand-500" /></div> :
        !data.template ? <Empty icon={Database} title="داده‌ای نیست" /> :
          data.template === 'workshop' ? (
            <div className="grid gap-4 md:grid-cols-2">
              {data.sessions.map((s) => (
                <div key={s.id} className="rounded-2xl border border-slate-200 p-4">
                  <div className="flex items-center justify-between gap-2">
                    <div className="font-bold">{s.title}</div>
                    <Badge tone={s.registrations.length >= s.capacity ? 'red' : 'green'}>{s.registrations.length} / {s.capacity}</Badge>
                  </div>
                  <div className="mb-3 text-xs text-slate-500">{s.when}</div>
                  <div className="mb-1 text-sm font-medium">ثبت‌نام‌ها</div>
                  <People rows={s.registrations} emptyText="هنوز ثبت‌نامی نشده" />
                  {s.waitlist.length > 0 && (<><div className="mb-1 mt-4 text-sm font-medium">فهرست انتظار</div><People rows={s.waitlist} emptyText="" /></>)}
                </div>
              ))}
            </div>
          ) : data.orders.length === 0 ? <Empty icon={Database} title="هنوز سفارشی ثبت نشده" /> : (
            <div className="space-y-3">
              {data.orders.map((o) => (
                <div key={o.code} className="rounded-2xl border border-slate-200 p-4 text-sm">
                  <div className="flex items-center justify-between">
                    <span className="font-bold" dir="ltr">{o.code}</span><span className="font-bold">{fmt(o.total)} تومان</span>
                  </div>
                  <div className="mt-2 text-slate-600">{o.lines.map((l) => `${l.item} × ${l.qty}`).join('، ')}</div>
                  <div className="mt-2 flex flex-wrap gap-x-4 text-xs text-slate-500">
                    {Object.entries(o.fields || {}).map(([k, v]) => <span key={k}>{({ name: 'نام', phone: 'موبایل', address: 'آدرس', note: 'توضیحات' })[k]}: {v}</span>)}
                  </div>
                </div>
              ))}
            </div>
          )}
    </div>
  )
}
