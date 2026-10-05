import { Badge } from './ui'

export default function VersionsView({ bot, selected, onSelect }) {
  return (
    <div className="p-5">
      <ol className="relative space-y-4 border-r-2 border-slate-100 pr-6">
        {bot.versions.map((v) => (
          <li key={v.id} className="relative">
            <span className={`absolute -right-[33px] top-4 size-4 rounded-full ring-4 ring-white ${v.is_live ? 'bg-emerald-500' : 'bg-slate-300'}`} />
            <button onClick={() => onSelect(v.id)}
              className={`w-full rounded-2xl border p-4 text-right transition cursor-pointer ${selected === v.id ? 'border-brand-400 bg-brand-50/40' : 'border-slate-200 hover:bg-slate-50'}`}>
              <div className="flex flex-wrap items-center gap-2">
                <span className="font-bold">نسخهٔ {v.number}</span>
                {v.is_live && <Badge tone="green">منتشرشده</Badge>}
                <Badge tone={v.passed === v.total ? 'green' : 'amber'}>آزمون {v.passed}/{v.total}</Badge>
                <span className="ms-auto text-xs text-slate-400">{new Date(v.created_at).toLocaleString('fa-IR')}</span>
              </div>
              <div className="mt-2 whitespace-pre-wrap text-sm leading-7 text-slate-600">{v.change_note}</div>
            </button>
          </li>
        ))}
      </ol>
    </div>
  )
}
