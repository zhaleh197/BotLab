const TOKEN_KEY = 'botlab_token'

export const auth = {
  get token() {
    try { return localStorage.getItem(TOKEN_KEY) } catch { return null }
  },
  set(token) {
    try { token ? localStorage.setItem(TOKEN_KEY, token) : localStorage.removeItem(TOKEN_KEY) } catch { /* ignore */ }
  },
}

export async function api(path, { method = 'GET', body } = {}) {
  const headers = { 'Content-Type': 'application/json' }
  if (auth.token) headers.Authorization = `Bearer ${auth.token}`
  const res = await fetch(path, { method, headers, body: body ? JSON.stringify(body) : undefined })
  let data = null
  try { data = await res.json() } catch { /* empty body */ }
  if (res.status === 401) {
    auth.set(null)
    window.dispatchEvent(new Event('botlab-logout'))
  }
  if (!res.ok) {
    const d = data?.detail
    const msg = typeof d === 'string' ? d : Array.isArray(d) ? 'ورودی نامعتبر است' : 'خطا در ارتباط با سرور'
    throw new Error(msg)
  }
  return data
}

export const fmt = (n) => (n || 0).toLocaleString('en-US')
