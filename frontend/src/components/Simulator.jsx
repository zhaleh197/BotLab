import { useEffect, useRef, useState } from 'react'
import { Bot, RotateCcw, Send, Info } from 'lucide-react'
import { api } from '../api'
import { Button } from './ui'

const USERS = [
  { id: 'u1', name: 'علی', color: 'bg-sky-500' },
  { id: 'u2', name: 'سارا', color: 'bg-pink-500' },
  { id: 'u3', name: 'رضا', color: 'bg-amber-500' },
]
const empty = () => ({ u1: [], u2: [], u3: [] })

export default function Simulator({ botId, version }) {
  const [user, setUser] = useState('u1')
  const [chats, setChats] = useState(empty)
  const [unread, setUnread] = useState({})
  const [text, setText] = useState('')
  const [busy, setBusy] = useState(false)
  const endRef = useRef(null)
  const msgs = chats[user]
  const lastButtons = [...msgs].reverse().find((m) => m.from === 'bot')?.buttons || []

  useEffect(() => { endRef.current?.scrollIntoView({ block: 'end' }) }, [msgs.length, user])

  const send = async (t) => {
    const value = (t ?? text).trim()
    if (!value || busy) return
    setText(''); setBusy(true)
    setChats((c) => ({ ...c, [user]: [...c[user], { from: 'me', text: value }] }))
    try {
      const r = await api(`/api/bots/${botId}/sim`, { method: 'POST', body: { text: value, user, version_id: version.id } })
      setChats((c) => {
        const next = { ...c }
        for (const rep of r.replies) next[rep.to] = [...(next[rep.to] || []), { from: 'bot', text: rep.text, buttons: rep.buttons }]
        return next
      })
      const others = r.replies.filter((x) => x.to !== user)
      if (others.length) setUnread((u) => { const n = { ...u }; others.forEach((o) => { n[o.to] = (n[o.to] || 0) + 1 }); return n })
    } catch (e) {
      setChats((c) => ({ ...c, [user]: [...c[user], { from: 'bot', text: '⚠️ ' + e.message }] }))
    } finally { setBusy(false) }
  }

  const reset = async () => {
    await api(`/api/bots/${botId}/sim/reset`, { method: 'POST' })
    setChats(empty()); setUnread({})
  }

  const switchUser = (id) => { setUser(id); setUnread((u) => ({ ...u, [id]: 0 })) }

  return (
    <div className="grid gap-6 p-5 xl:grid-cols-[1fr_260px]">
      <div className="mx-auto flex h-[640px] w-full max-w-[420px] flex-col overflow-hidden rounded-[2rem] border-[6px] border-slate-800 bg-slate-800 shadow-xl">
        <div className="flex items-center gap-2 bg-[#2b5278] px-3 py-2.5 text-white">
          <span className="grid size-9 place-items-center rounded-full bg-white/20"><Bot className="size-5" /></span>
          <div className="min-w-0 flex-1">
            <div className="truncate text-sm font-bold">{version.spec.business_name}</div>
            <div className="text-[11px] text-white/70">بات · نسخهٔ {version.number} · محیط آزمایشی</div>
          </div>
        </div>
        <div className="chat-bg flex-1 space-y-2 overflow-y-auto p-3 scroll-thin">
          {msgs.length === 0 && (
            <div className="mt-24 text-center">
              <Button onClick={() => send('/start')} className="!rounded-full">شروع گفتگو با بات</Button>
              <div className="mt-2 text-xs text-slate-600">به‌جای {USERS.find((u) => u.id === user).name} پیام می‌دهید</div>
            </div>
          )}
          {msgs.map((m, i) => (
            <div key={i} className={`fade-up flex ${m.from === 'me' ? 'justify-start' : 'justify-end'}`}>
              <div className={`max-w-[85%] whitespace-pre-wrap rounded-2xl px-3 py-2 text-[13px] leading-6 shadow-sm ${m.from === 'me' ? 'rounded-tr-sm bg-[#effdde]' : 'rounded-tl-sm bg-white'}`}>
                {m.text}
              </div>
            </div>
          ))}
          <div ref={endRef} />
        </div>
        {lastButtons.length > 0 && (
          <div className="space-y-1 bg-slate-100 p-1.5">
            {lastButtons.map((row, i) => (
              <div key={i} className="flex gap-1">
                {row.map((b) => (
                  <button key={b} onClick={() => send(b)} disabled={busy}
                    className="flex-1 truncate rounded-lg bg-white px-2 py-2 text-xs shadow-sm hover:bg-slate-50 disabled:opacity-60 cursor-pointer">{b}</button>
                ))}
              </div>
            ))}
          </div>
        )}
        <form onSubmit={(e) => { e.preventDefault(); send() }} className="flex items-center gap-2 bg-white px-2 py-2">
          <input value={text} onChange={(e) => setText(e.target.value)} placeholder="پیام…"
            className="flex-1 rounded-full bg-slate-100 px-4 py-2 text-sm outline-none" />
          <button disabled={busy || !text.trim()} className="grid size-9 place-items-center rounded-full bg-[#2b5278] text-white disabled:opacity-40 cursor-pointer">
            <Send className="size-4 -scale-x-100" />
          </button>
        </form>
      </div>

      <div className="space-y-4">
        <div>
          <div className="mb-2 text-sm font-medium">کاربر آزمایشی</div>
          <div className="space-y-1.5">
            {USERS.map((u) => (
              <button key={u.id} onClick={() => switchUser(u.id)}
                className={`flex w-full items-center gap-2 rounded-xl border px-3 py-2 text-sm transition cursor-pointer ${user === u.id ? 'border-brand-500 bg-brand-50' : 'border-slate-200 hover:bg-slate-50'}`}>
                <span className={`grid size-7 place-items-center rounded-full text-xs text-white ${u.color}`}>{u.name[0]}</span>
                {u.name}
                {unread[u.id] > 0 && <span className="ms-auto rounded-full bg-rose-500 px-2 text-xs text-white">{unread[u.id]}</span>}
              </button>
            ))}
          </div>
        </div>
        <Button variant="secondary" onClick={reset} className="w-full"><RotateCcw className="size-4" />پاک کردن داده‌های آزمایشی</Button>
        <div className="flex gap-2 rounded-xl bg-slate-50 p-3 text-xs leading-6 text-slate-600">
          <Info className="size-4 shrink-0 text-slate-400" />
          <span>این شبیه‌ساز دقیقاً همان موتوری را اجرا می‌کند که بات واقعی روی بله و تلگرام اجرا می‌کند. با چند کاربر می‌توانید پر شدن ظرفیت و فهرست انتظار را امتحان کنید. داده‌های این بخش از داده‌های واقعی جداست.</span>
        </div>
      </div>
    </div>
  )
}
