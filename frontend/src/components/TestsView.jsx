import { useState } from 'react'
import { CheckCircle2, ChevronDown, XCircle } from 'lucide-react'
import { Badge } from './ui'

function Transcript({ result }) {
  return (
    <div className="mt-3 space-y-2 rounded-xl bg-slate-50 p-3">
      {result.transcript.map((s, i) => (
        <div key={i} className={`text-xs leading-6 ${result.failed_step === i ? 'rounded-lg bg-rose-50 p-2 ring-1 ring-rose-200' : ''}`}>
          <div><span className="font-medium text-brand-700">{s.user} ←</span> {s.send}</div>
          {s.replies.map((r, j) => (
            <div key={j} className="mr-4 whitespace-pre-wrap text-slate-600">
              <span className="font-medium text-slate-500">بات → {r.to}:</span> {r.text}
            </div>
          ))}
        </div>
      ))}
    </div>
  )
}

function TestItem({ test, result }) {
  const [open, setOpen] = useState(!result?.passed)
  const passed = result?.passed
  return (
    <div className={`rounded-2xl border p-4 ${passed ? 'border-slate-200' : 'border-rose-200 bg-rose-50/30'}`}>
      <button onClick={() => setOpen(!open)} className="flex w-full items-center gap-3 text-right cursor-pointer">
        {passed ? <CheckCircle2 className="size-5 shrink-0 text-emerald-600" /> : <XCircle className="size-5 shrink-0 text-rose-600" />}
        <div className="min-w-0 flex-1">
          <div className="flex flex-wrap items-center gap-2 font-medium">
            {test.name}
            {test.origin === 'auto' ? <Badge>خودکار</Badge> : <Badge tone="violet">نوشتهٔ ایجنت</Badge>}
            <span className="text-xs font-normal text-slate-400">{test.steps.length} گام</span>
          </div>
          {test.description && <div className="text-xs leading-6 text-slate-500">{test.description}</div>}
        </div>
        <ChevronDown className={`size-4 text-slate-400 transition ${open ? 'rotate-180' : ''}`} />
      </button>
      {open && result && (
        <>
          {!passed && <div className="mt-3 rounded-xl bg-rose-100/60 px-3 py-2 text-sm text-rose-800">گام {result.failed_step + 1}: {result.reason}</div>}
          <Transcript result={result} />
        </>
      )}
    </div>
  )
}

export default function TestsView({ version }) {
  const rep = version.test_report || { results: [], passed: 0, total: 0 }
  const byName = Object.fromEntries((rep.results || []).map((r) => [r.name, r]))
  const pct = rep.total ? Math.round((rep.passed / rep.total) * 100) : 0
  return (
    <div className="space-y-4 p-5">
      <div className="flex flex-wrap items-center gap-4 rounded-2xl bg-gradient-to-l from-slate-50 to-white p-4 ring-1 ring-slate-200">
        <div className={`grid size-16 place-items-center rounded-full text-lg font-bold ${pct === 100 ? 'bg-emerald-100 text-emerald-700' : 'bg-amber-100 text-amber-700'}`}>{pct}٪</div>
        <div className="flex-1">
          <div className="font-bold">{rep.passed} از {rep.total} آزمون موفق</div>
          <div className="text-sm leading-6 text-slate-500">
            آزمون‌های «خودکار» از روی مشخصات ساخته می‌شوند و رفتارهای پایه را می‌سنجند؛ آزمون‌های «نوشتهٔ ایجنت» قواعد خاص شما را
            می‌سنجند و در نسخه‌های بعد به‌عنوان آزمون رگرسیون دوباره اجرا می‌شوند.
          </div>
        </div>
      </div>
      {version.tests.map((t) => <TestItem key={t.name} test={t} result={byName[t.name]} />)}
    </div>
  )
}
