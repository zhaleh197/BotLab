import { useCallback, useEffect, useRef, useState } from 'react'
import { Link, useNavigate, useParams } from 'react-router-dom'
import { ArrowRight, Database, FileCode2, FlaskConical, History, Rocket, Smartphone, Trash2 } from 'lucide-react'
import { api } from '../api'
import { useUser } from '../App'
import { Empty, Spinner, TopBar } from '../components/ui'
import AgentPanel from '../components/AgentPanel'
import Simulator from '../components/Simulator'
import SpecView from '../components/SpecView'
import TestsView from '../components/TestsView'
import PublishPanel from '../components/PublishPanel'
import DataView from '../components/DataView'
import VersionsView from '../components/VersionsView'
import { statusBadge, templateBadge } from './Dashboard'

const TABS = [
  { id: 'sim', label: 'شبیه‌ساز', icon: Smartphone },
  { id: 'spec', label: 'مشخصات', icon: FileCode2 },
  { id: 'tests', label: 'آزمون‌ها', icon: FlaskConical },
  { id: 'publish', label: 'انتشار', icon: Rocket },
  { id: 'data', label: 'داده‌ها', icon: Database },
  { id: 'versions', label: 'نسخه‌ها', icon: History },
]

export default function Workspace() {
  const { id } = useParams()
  const nav = useNavigate()
  const { user, logout } = useUser()
  const [bot, setBot] = useState(null)
  const [messages, setMessages] = useState([])
  const [status, setStatus] = useState('idle')
  const [versionId, setVersionId] = useState(null)
  const [version, setVersion] = useState(null)
  const [tab, setTab] = useState('sim')
  const [error, setError] = useState('')
  const prevStatus = useRef(null)

  const loadBot = useCallback(async (selectLatest) => {
    const b = await api(`/api/bots/${id}`)
    setBot(b)
    if (b.versions.length && (selectLatest || !versionId)) setVersionId(b.versions[0].id)
    return b
  }, [id, versionId])

  const loadMessages = useCallback(async () => {
    const r = await api(`/api/bots/${id}/messages`)
    setMessages(r.messages)
    setStatus(r.agent_status)
    return r.agent_status
  }, [id])

  useEffect(() => {
    loadBot(true).catch((e) => setError(e.message))
    loadMessages().catch(() => {})
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [id])

  // Poll while the agent works; when it finishes, refresh the bot and jump to the newest version.
  useEffect(() => {
    if (prevStatus.current === 'running' && status === 'idle') loadBot(true).catch(() => {})
    prevStatus.current = status
    if (status !== 'running') return
    const t = setInterval(() => loadMessages().catch(() => {}), 1200)
    return () => clearInterval(t)
  }, [status, loadMessages, loadBot])

  useEffect(() => {
    if (!versionId) { setVersion(null); return }
    api(`/api/bots/${id}/versions/${versionId}`).then(setVersion).catch(() => {})
  }, [id, versionId])

  const send = async (text) => {
    await api(`/api/bots/${id}/messages`, { method: 'POST', body: { text } })
    setStatus('running')
    await loadMessages()
  }

  const remove = async () => {
    if (!confirm('این بات و همهٔ داده‌هایش حذف شود؟')) return
    await api(`/api/bots/${id}`, { method: 'DELETE' })
    nav('/')
  }

  if (error) return <div className="p-10 text-center text-rose-600">{error} — <Link to="/" className="underline">بازگشت</Link></div>
  if (!bot) return <div className="h-full grid place-items-center"><Spinner className="size-8 text-brand-500" /></div>

  const refresh = () => loadBot(false)
  const hasVersion = bot.versions.length > 0

  return (
    <div className="flex h-full flex-col">
      <TopBar user={user} onLogout={logout}>
        <Link to="/" className="rounded-lg p-1.5 text-slate-500 hover:bg-slate-100"><ArrowRight className="size-4" /></Link>
        <div className="min-w-0 truncate font-bold">{bot.name}</div>
        <div className="hidden md:flex gap-1.5">{templateBadge(bot.template)}{statusBadge(bot)}</div>
        <button onClick={remove} title="حذف بات" className="ms-auto rounded-lg p-2 text-slate-400 hover:bg-rose-50 hover:text-rose-600 cursor-pointer">
          <Trash2 className="size-4" />
        </button>
      </TopBar>

      <div className="mx-auto grid w-full max-w-[1500px] flex-1 min-h-0 gap-4 p-4 lg:grid-cols-[minmax(360px,440px)_1fr]">
        <AgentPanel messages={messages} running={status === 'running'} onSend={send} hasBot={hasVersion}
          onAction={(a) => setTab(a)} />

        <section className="flex min-h-[600px] flex-col overflow-hidden rounded-2xl border border-slate-200/80 bg-white shadow-sm">
          <div className="flex items-center gap-1 overflow-x-auto border-b border-slate-100 px-3 pt-2 scroll-thin">
            {TABS.map(({ id: t, label, icon: Icon }) => (
              <button key={t} onClick={() => setTab(t)}
                className={`flex shrink-0 items-center gap-1.5 border-b-2 px-3 py-2.5 text-sm transition cursor-pointer ${tab === t ? 'border-brand-600 text-brand-700 font-medium' : 'border-transparent text-slate-500 hover:text-ink'}`}>
                <Icon className="size-4" />{label}
              </button>
            ))}
            {hasVersion && (
              <div className="ms-auto flex shrink-0 items-center gap-2 pb-1 text-sm">
                <span className="text-slate-500">نسخه:</span>
                <select value={versionId || ''} onChange={(e) => setVersionId(Number(e.target.value))}
                  className="rounded-lg border border-slate-200 bg-white px-2 py-1 text-sm outline-none">
                  {bot.versions.map((v) => (
                    <option key={v.id} value={v.id}>{v.number}{v.is_live ? ' (منتشرشده)' : ''}</option>
                  ))}
                </select>
              </div>
            )}
          </div>
          <div className="flex-1 min-h-0 overflow-y-auto scroll-thin">
            {!hasVersion ? (
              <Empty icon={FileCode2} title="هنوز نسخه‌ای ساخته نشده">
                {status === 'running' ? 'ایجنت در حال کار است…' : 'در پنل گفتگو نیازتان را توضیح دهید و به سؤال‌های ایجنت پاسخ دهید تا نسخهٔ اول ساخته شود.'}
              </Empty>
            ) : !version ? (
              <div className="grid place-items-center py-16"><Spinner className="size-6 text-brand-500" /></div>
            ) : (
              <>
                {tab === 'sim' && <Simulator botId={bot.id} version={version} />}
                {tab === 'spec' && <SpecView version={version} />}
                {tab === 'tests' && <TestsView version={version} />}
                {tab === 'publish' && <PublishPanel bot={bot} version={version} onChange={refresh} />}
                {tab === 'data' && <DataView bot={bot} />}
                {tab === 'versions' && <VersionsView bot={bot} selected={versionId} onSelect={(v) => { setVersionId(v); setTab('spec') }} />}
              </>
            )}
          </div>
        </section>
      </div>
    </div>
  )
}
