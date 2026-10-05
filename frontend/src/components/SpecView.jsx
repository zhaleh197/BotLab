import { useState } from 'react'
import { fmt } from '../api'
import { Badge } from './ui'

const FIELD = { name: 'نام', phone: 'موبایل', address: 'آدرس', note: 'توضیحات' }

function Row({ k, v }) {
  return (
    <div className="flex justify-between gap-4 border-b border-slate-100 py-2.5 text-sm last:border-0">
      <span className="text-slate-500">{k}</span><span className="text-left font-medium">{v}</span>
    </div>
  )
}

function Section({ title, children }) {
  return (
    <div className="rounded-2xl border border-slate-200 p-4">
      <div className="mb-2 font-bold">{title}</div>
      {children}
    </div>
  )
}

export default function SpecView({ version }) {
  const [raw, setRaw] = useState(false)
  const s = version.spec
  const money = (n) => (n ? `${fmt(n)} ${s.currency}` : 'رایگان')
  const yes = (b) => (b ? <Badge tone="green">فعال</Badge> : <Badge>غیرفعال</Badge>)

  return (
    <div className="space-y-4 p-5">
      <div className="flex items-center justify-between">
        <div>
          <div className="text-lg font-bold">{s.business_name}</div>
          <div className="text-sm text-slate-500">مشخصات نسخهٔ {version.number} — همان چیزی که ایجنت از توضیحات شما فهمیده است</div>
        </div>
        <button onClick={() => setRaw(!raw)} className="rounded-lg border border-slate-200 px-3 py-1.5 text-xs text-slate-600 hover:bg-slate-50 cursor-pointer">
          {raw ? 'نمای خوانا' : 'نمای JSON'}
        </button>
      </div>

      {raw ? (
        <pre dir="ltr" className="overflow-x-auto rounded-2xl bg-slate-900 p-4 text-xs leading-6 text-slate-100">{JSON.stringify(s, null, 2)}</pre>
      ) : (
        <>
          <Section title="پیام خوش‌آمد">
            <div className="whitespace-pre-wrap text-sm leading-7 text-slate-700">{s.welcome_message}</div>
            {s.support_contact && <div className="mt-2 text-sm text-slate-500">پشتیبانی: {s.support_contact}</div>}
          </Section>

          {s.template === 'workshop' && (
            <>
              <Section title={`کارگاه‌ها (${s.workshop.sessions.length})`}>
                <div className="overflow-x-auto">
                  <table className="w-full text-sm">
                    <thead><tr className="text-right text-slate-500"><th className="py-2 font-normal">عنوان</th><th className="font-normal">زمان</th><th className="font-normal">ظرفیت</th><th className="font-normal">قیمت</th></tr></thead>
                    <tbody>
                      {s.workshop.sessions.map((x) => (
                        <tr key={x.id} className="border-t border-slate-100">
                          <td className="py-2.5 font-medium">{x.title}</td><td>{x.when}</td><td>{x.capacity} نفر</td><td>{money(x.price)}</td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              </Section>
              <Section title="قواعد ثبت‌نام">
                <Row k="لغو ثبت‌نام توسط کاربر" v={yes(s.workshop.allow_cancel)} />
                <Row k="حداکثر کارگاه برای هر نفر" v={s.workshop.max_per_user} />
                <Row k="فهرست انتظار" v={<span className="flex items-center gap-2">{yes(s.workshop.waitlist.enabled)}
                  {s.workshop.waitlist.enabled && <span className="text-xs text-slate-500">{s.workshop.waitlist.max_size ? `حداکثر ${s.workshop.waitlist.max_size} نفر` : 'بدون سقف'}</span>}</span>} />
                <Row k="اطلاعات دریافتی" v={s.workshop.collect_fields.map((f) => FIELD[f]).join('، ') || '—'} />
              </Section>
            </>
          )}

          {s.template === 'order' && (
            <>
              <Section title={`منو (${s.order.items.length} آیتم)`}>
                <div className="overflow-x-auto">
                  <table className="w-full text-sm">
                    <thead><tr className="text-right text-slate-500"><th className="py-2 font-normal">آیتم</th><th className="font-normal">دسته</th><th className="font-normal">قیمت</th><th className="font-normal">گزینه‌ها</th><th className="font-normal">وضعیت</th></tr></thead>
                    <tbody>
                      {s.order.items.map((x) => (
                        <tr key={x.id} className="border-t border-slate-100">
                          <td className="py-2.5 font-medium">{x.name}</td><td className="text-slate-500">{x.category || '—'}</td>
                          <td>{money(x.price)}</td><td>{x.options.join('، ') || '—'}</td>
                          <td>{x.available ? <Badge tone="green">موجود</Badge> : <Badge tone="red">ناموجود</Badge>}</td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              </Section>
              <Section title="قواعد سفارش">
                <Row k="حداقل مبلغ سفارش" v={s.order.rules.min_order_total ? money(s.order.rules.min_order_total) : 'ندارد'} />
                <Row k="حداکثر تعداد هر آیتم" v={s.order.rules.max_qty_per_item} />
                <Row k="حداکثر اقلام هر سفارش" v={s.order.rules.max_items_per_order} />
                <Row k="ارسال" v={s.order.rules.delivery ? `${money(s.order.rules.delivery_fee)}${s.order.rules.free_delivery_over ? ` — رایگان بالای ${money(s.order.rules.free_delivery_over)}` : ''}` : 'ندارد (تحویل حضوری)'} />
                <Row k="ساعت سفارش‌گیری" v={s.order.rules.open_hour != null ? `${s.order.rules.open_hour} تا ${s.order.rules.close_hour}` : 'شبانه‌روزی'} />
                <Row k="اطلاعات دریافتی" v={s.order.collect_fields.map((f) => FIELD[f]).join('، ')} />
              </Section>
            </>
          )}

          {version.assumptions?.length > 0 && (
            <Section title="فرض‌های ایجنت">
              <ul className="list-disc space-y-1 pr-5 text-sm leading-7 text-slate-700">{version.assumptions.map((a, i) => <li key={i}>{a}</li>)}</ul>
            </Section>
          )}
        </>
      )}
    </div>
  )
}
