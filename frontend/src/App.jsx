import { createContext, useContext, useEffect, useState } from 'react'
import { Navigate, Route, Routes } from 'react-router-dom'
import { api, auth } from './api'
import AuthPage from './pages/AuthPage'
import Dashboard from './pages/Dashboard'
import Workspace from './pages/Workspace'
import { Spinner } from './components/ui'

const UserCtx = createContext(null)
export const useUser = () => useContext(UserCtx)

export default function App() {
  const [user, setUser] = useState(undefined)

  useEffect(() => {
    if (!auth.token) { setUser(null); return }
    api('/api/me').then(setUser).catch(() => setUser(null))
    const onLogout = () => setUser(null)
    window.addEventListener('botlab-logout', onLogout)
    return () => window.removeEventListener('botlab-logout', onLogout)
  }, [])

  const login = ({ token, user }) => { auth.set(token); setUser(user) }
  const logout = () => { auth.set(null); setUser(null) }

  if (user === undefined) {
    return <div className="h-full grid place-items-center"><Spinner className="size-8 text-brand-500" /></div>
  }
  return (
    <UserCtx.Provider value={{ user, login, logout }}>
      <Routes>
        {user ? (
          <>
            <Route path="/" element={<Dashboard />} />
            <Route path="/bots/:id" element={<Workspace />} />
            <Route path="*" element={<Navigate to="/" />} />
          </>
        ) : (
          <Route path="*" element={<AuthPage />} />
        )}
      </Routes>
    </UserCtx.Provider>
  )
}
