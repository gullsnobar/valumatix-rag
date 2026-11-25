const STORAGE_KEY = 'tarnwick-access-token'
const SESSION_EVENT = 'tarnwick-session-change'

export function getAccessToken(): string | null {
  return localStorage.getItem(STORAGE_KEY)
}

export function setAccessToken(token: string | null): void {
  if (token === null) localStorage.removeItem(STORAGE_KEY)
  else localStorage.setItem(STORAGE_KEY, token)
  window.dispatchEvent(new Event(SESSION_EVENT))
}

export function subscribeToSession(callback: () => void): () => void {
  const onStorage = (event: StorageEvent) => {
    if (event.key === STORAGE_KEY || event.key === null) callback()
  }
  window.addEventListener(SESSION_EVENT, callback)
  window.addEventListener('storage', onStorage)
  return () => {
    window.removeEventListener(SESSION_EVENT, callback)
    window.removeEventListener('storage', onStorage)
  }
}

export function expireSession(token: string | null): void {
  // A late response from an old session must not sign out a newly signed-in user.
  if (token !== null && getAccessToken() === token) setAccessToken(null)
}
