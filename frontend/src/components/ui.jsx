import { Bot, LogOut } from 'lucide-react'
import { Link } from 'react-router-dom'

export function Spinner({ className = 'size-4' }) {
  return (
    <svg className={`animate-spin ${className}`} viewBox="0 0 24 24" fill="none">
      <circle cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="3" opacity=".2" />
      <path d="M22 12a10 10 0 0 0-10-10" stroke="currentColor" strokeWidth="3" strokeLinecap="round" />
    </svg>
  )
}

const variants = {
  primary: 'bg-brand-600 text-white hover:bg-brand-700 shadow-sm shadow-brand-600/20',
  secondary: 'bg-white text-ink border border-slate-200 hover:bg-slate-50',
  ghost: 'text-slate-600 hover:bg-slate-100',
  danger: 'bg-white text-rose-600 border border-rose-200 hover:bg-rose-50',
  success: 'bg-emerald-600 text-white hover:bg-emerald-700',
}

export function Button({ variant = 'primary', loading, className = '', children, ...props }) {
  return (
    <button
      {...props}
      disabled={loading || props.disabled}
      className={`inline-flex items-center justify-center gap-2 rounded-xl px-4 py-2.5 text-sm font-medium transition
        disabled:opacity-50 disabled:cursor-not-allowed cursor-pointer ${variants[variant]} ${className}`}
    >
      {loading && <Spinner />}
      {children}
    </button>
  )
}

const tones = {
  slate: 'bg-slate-100 text-slate-600',
  green: 'bg-emerald-50 text-emerald-700 ring-1 ring-emerald-200',
  amber: 'bg-amber-50 text-amber-700 ring-1 ring-amber-200',
  blue: 'bg-brand-50 text-brand-700 ring-1 ring-brand-200',
  red: 'bg-rose-50 text-rose-700 ring-1 ring-rose-200',
  violet: 'bg-violet-50 text-violet-700 ring-1 ring-violet-200',
}

export function Badge({ tone = 'slate', children, className = '' }) {
  return <span className={`inline-flex items-center gap-1 rounded-full px-2.5 py-0.5 text-xs font-medium ${tones[tone]} ${className}`}>{children}</span>
}

export function Card({ className = '', children }) {
  return <div className={`rounded-2xl bg-white border border-slate-200/80 shadow-sm ${className}`}>{children}</div>
}

export function Input({ label, hint, className = '', ...props }) {
  return (
    <label className="block">
      {label && <span className="mb-1.5 block text-sm font-medium text-slate-700">{label}</span>}
      <input
        {...props}
        className={`w-full rounded-xl border border-slate-200 bg-white px-3.5 py-2.5 text-sm outline-none transition
          focus:border-brand-500 focus:ring-4 focus:ring-brand-100 ${className}`}
      />
      {hint && <span className="mt-1 block text-xs text-slate-500">{hint}</span>}
    </label>
  )
}

export function Logo({ small }) {
  return (
    <Link to="/" className="flex items-center gap-2 font-bold text-ink">
      <span className={`grid place-items-center rounded-xl bg-gradient-to-br from-brand-500 to-violet-500 text-white ${small ? 'size-8' : 'size-10'}`}>
        <Bot className={small ? 'size-5' : 'size-6'} />
      </span>
      <span className={small ? 'text-lg' : 'text-xl'}>باتساز</span>
    </Link>
  )
}

export function TopBar({ user, onLogout, children }) {
  return (
    <header className="sticky top-0 z-20 border-b border-slate-200/80 bg-white/90 backdrop-blur">
      <div className="mx-auto flex h-14 max-w-[1500px] items-center gap-3 px-4">
        <Logo small />
        <div className="flex flex-1 items-center gap-3 min-w-0">{children}</div>
        {user && (
          <div className="flex items-center gap-2">
            <span className="hidden sm:block text-sm text-slate-500">{user.name}</span>
            <button onClick={onLogout} title="خروج" className="rounded-lg p-2 text-slate-500 hover:bg-slate-100 cursor-pointer">
              <LogOut className="size-4" />
            </button>
          </div>
        )}
      </div>
    </header>
  )
}

/** Tiny formatter: **bold** and line breaks. */
export function RichText({ text }) {
  return (
    <div className="whitespace-pre-wrap leading-7">
      {String(text || '').split(/(\*\*[^*]+\*\*)/g).map((p, i) =>
        p.startsWith('**') && p.endsWith('**') ? <strong key={i}>{p.slice(2, -2)}</strong> : <span key={i}>{p}</span>)}
    </div>
  )
}

export function Empty({ icon: Icon, title, children }) {
  return (
    <div className="flex flex-col items-center justify-center gap-3 py-16 text-center text-slate-500">
      {Icon && <span className="grid size-14 place-items-center rounded-2xl bg-slate-100"><Icon className="size-7 text-slate-400" /></span>}
      <div className="font-medium text-slate-700">{title}</div>
      <div className="max-w-sm text-sm leading-6">{children}</div>
    </div>
  )
}
