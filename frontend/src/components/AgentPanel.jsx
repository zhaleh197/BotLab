import { useEffect, useRef, useState } from 'react'
import { AlertTriangle, Check, CircleX, FlaskConical, Rocket, Send, Smartphone, Sparkles } from 'lucide-react'
import { Button, RichText, Spinner } from './ui'

const SUGGESTIONS = [
  'فهرست انتظار هم اضافه کن؛ حداکثر ۵ نفر',
  'ظرفیت را ۲ نفر بیشتر کن',
  'لغو ثبت‌نام را غیرفعال کن',
  'یک آیتم جدید به منو اضافه کن: چای ماسالا ۹۵ هزار تومان',
  'حداقل سفارش را ۳۰۰ هزار تومان کن',
]

function StepIcon({ status }) {
  if (status === 'running') return <Spinner className="size-4 text-brand-600" />
  if (status === 'warn') return <AlertTriangle className="size-4 text-amber-500" />
  if (status === 'error') return <CircleX className="size-4 text-rose-500" />
  return <Check className="size-4 text-emerald-600" />
}

function Steps({ steps }) {
  return (
    <div className="fade-up rounded-xl border border-slate-200 bg-slate-50/70 p-3">
      <div className="mb-2 flex items-center gap-1.5 text-xs font-medium text-slate-500"><Sparkles className="size-3.5" />کار ایجنت</div>
      <ol className="space-y-2">
        {steps.map((s) => (
          <li key={s.id} className="flex gap-2 text-sm">
            <span className="mt-0.5"><StepIcon status={s.meta.status} /></span>
            <div className="min-w-0">
              <div className={s.meta.status === 'running' ? 'font-medium text-ink' : 'text-slate-700'}>{s.content}</div>
              {s.meta.detail && <div className="text-xs leading-5 text-slate-500">{s.meta.detail}</div>}
            </div>
          </li>
        ))}
      </ol>
    </div>
  )
}

function AssistantMessage({ m, onAction, onPick }) {
  const meta = m.meta || {}
  return (
    <div className="fade-up max-w-[95%] rounded-2xl rounded-tr-sm bg-white p-3.5 text-sm shadow-sm ring-1 ring-slate-200/70">
      <RichText text={m.content} />
      {meta.kind === 'questions' && (
        <ol className="mt-3 space-y-2">
          {meta.questions.map((q, i) => (
            <li key={i}>
              <button onClick={() => onPick(q)}
                className="w-full rounded-xl bg-brand-50 px-3 py-2 text-right leading-6 text-brand-700 hover:bg-brand-100 cursor-pointer">
                {i + 1}. {q}
              </button>
            </li>
          ))}
        </ol>
      )}
      {meta.unsupported?.length > 0 && (
        <div className="mt-3 rounded-xl bg-amber-50 px-3 py-2 text-xs leading-6 text-amber-800">
          خارج از توان نسخهٔ فعلی: {meta.unsupported.join('، ')}
        </div>
      )}
      {meta.kind === 'result' && (
        <>
          {meta.diff?.length > 0 && (
            <details className="mt-3 rounded-xl bg-slate-50 px-3 py-2 text-xs">
              <summary className="cursor-pointer text-slate-600">تغییرات فنی مشخصات ({meta.diff.length})</summary>
              <ul className="mt-2 space-y-1 font-mono text-[11px] leading-5 text-slate-600" dir="ltr">
                {meta.diff.map((d, i) => <li key={i}>{d}</li>)}
              </ul>
            </details>
          )}
          <div className="mt-3 flex flex-wrap gap-2">
            <Button variant="secondary" className="!px-3 !py-1.5 text-xs" onClick={() => onAction('sim')}><Smartphone className="size-3.5" />امتحان در شبیه‌ساز</Button>
            <Button variant="secondary" className="!px-3 !py-1.5 text-xs" onClick={() => onAction('tests')}>
              <FlaskConical className="size-3.5" />آزمون‌ها {meta.passed}/{meta.total}
            </Button>
            <Button className="!px-3 !py-1.5 text-xs" onClick={() => onAction('publish')}><Rocket className="size-3.5" />انتشار</Button>
          </div>
        </>
      )}
    </div>
  )
}

export default function AgentPanel({ messages, running, onSend, onAction, hasBot }) {
  const [text, setText] = useState('')
  const [sending, setSending] = useState(false)
  const [err, setErr] = useState('')
  const endRef = useRef(null)
  const inputRef = useRef(null)

  useEffect(() => { endRef.current?.scrollIntoView({ behavior: 'smooth', block: 'end' }) }, [messages.length, running])

  // group consecutive step messages into one timeline block
  const blocks = []
  for (const m of messages) {
    if (m.role === 'step') {
      const last = blocks[blocks.length - 1]
      if (last?.type === 'steps') last.items.push(m)
      else blocks.push({ type: 'steps', items: [m], id: m.id })
    } else blocks.push({ type: 'msg', m, id: m.id })
  }

  const submit = async (e) => {
    e?.preventDefault()
    if (!text.trim() || running) return
    setSending(true); setErr('')
    try { await onSend(text.trim()); setText('') } catch (e) { setErr(e.message) } finally { setSending(false) }
  }

  const pick = (q) => {
    setText((t) => (t ? t + '\n' : '') + q.replace(/\s*\(اگر نگویید.*\)\s*$/, '') + ': ')
    inputRef.current?.focus()
  }

  return (
    <section className="flex min-h-[600px] flex-col overflow-hidden rounded-2xl border border-slate-200/80 bg-white shadow-sm lg:h-[calc(100vh-88px)]">
      <div className="flex items-center gap-2 border-b border-slate-100 px-4 py-3">
        <span className="grid size-8 place-items-center rounded-lg bg-gradient-to-br from-brand-500 to-violet-500 text-white"><Sparkles className="size-4" /></span>
        <div>
          <div className="text-sm font-bold">ایجنت باتساز</div>
          <div className="text-xs text-slate-500">{running ? 'در حال کار…' : 'آمادهٔ دریافت درخواست'}</div>
        </div>
      </div>
      <div className="flex-1 space-y-3 overflow-y-auto bg-slate-50/50 p-4 scroll-thin">
        {blocks.map((b) =>
          b.type === 'steps' ? <Steps key={b.id} steps={b.items} /> :
            b.m.role === 'user' ? (
              <div key={b.id} className="fade-up mr-auto max-w-[90%] whitespace-pre-wrap rounded-2xl rounded-tl-sm bg-brand-600 px-3.5 py-2.5 text-sm leading-7 text-white">
                {b.m.content}
              </div>
            ) : <AssistantMessage key={b.id} m={b.m} onAction={onAction} onPick={pick} />,
        )}
        {running && !messages.some((m) => m.role === 'step' && m.meta.status === 'running') && (
          <div className="flex items-center gap-2 text-sm text-slate-500"><Spinner className="size-4 text-brand-500" />ایجنت در حال فکر کردن…</div>
        )}
        <div ref={endRef} />
      </div>
      <form onSubmit={submit} className="border-t border-slate-100 p-3">
        {hasBot && !running && (
          <div className="mb-2 flex gap-1.5 overflow-x-auto pb-1 scroll-thin">
            {SUGGESTIONS.map((s) => (
              <button type="button" key={s} onClick={() => setText(s)}
                className="shrink-0 rounded-full border border-slate-200 px-2.5 py-1 text-xs text-slate-600 hover:bg-slate-50 cursor-pointer">{s}</button>
            ))}
          </div>
        )}
        {err && <div className="mb-2 text-xs text-rose-600">{err}</div>}
        <div className="flex items-end gap-2">
          <textarea ref={inputRef} value={text} onChange={(e) => setText(e.target.value)} rows={2}
            placeholder={hasBot ? 'تغییر موردنظرتان را بنویسید…' : 'پاسخ یا توضیح خود را بنویسید…'}
            onKeyDown={(e) => { if (e.key === 'Enter' && !e.shiftKey) { e.preventDefault(); submit() } }}
            className="flex-1 resize-none rounded-xl border border-slate-200 px-3 py-2 text-sm leading-6 outline-none focus:border-brand-500 focus:ring-4 focus:ring-brand-100" />
          <Button type="submit" loading={sending} disabled={running || !text.trim()} className="!p-3" title="ارسال">
            {!sending && <Send className="size-4 -scale-x-100" />}
          </Button>
        </div>
      </form>
    </section>
  )
}
