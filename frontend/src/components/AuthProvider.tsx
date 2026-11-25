import { useEffect, useSyncExternalStore } from 'react'
import type { ReactNode } from 'react'
import { useQuery, useQueryClient } from '@tanstack/react-query'
import { api } from '../api/client.ts'
import { getAccessToken, setAccessToken, subscribeToSession } from '../api/session.ts'
import type { Credentials } from '../api/types.ts'
import { AuthContext } from '../hooks/auth.ts'

export function AuthProvider({ children }: { children: ReactNode }) {
  const client = useQueryClient()
  const token = useSyncExternalStore(subscribeToSession, getAccessToken)
  const account = useQuery({
    queryKey: ['account', token],
    queryFn: ({ signal }) => api.me(signal),
    enabled: Boolean(token),
    staleTime: 60_000,
    retry: false,
  })

  useEffect(() => {
    if (!token) client.removeQueries({ predicate: ({ queryKey }) => queryKey[0] !== 'health' })
  }, [client, token])

  async function authenticate(mode: 'login' | 'signup', credentials: Credentials, signal?: AbortSignal) {
    const auth = await api.authenticate(mode, credentials, signal)
    signal?.throwIfAborted()
    client.removeQueries({ predicate: ({ queryKey }) => queryKey[0] !== 'health' })
    client.setQueryData(['account', auth.access_token], auth.user)
    setAccessToken(auth.access_token)
    return auth.user
  }

  return (
    <AuthContext.Provider value={{
      status: !token ? 'anonymous' : account.isPending ? 'pending' : account.isError ? 'error' : 'ready',
      user: token ? account.data : undefined,
      authenticate,
      logout: () => setAccessToken(null),
      retry: () => { void account.refetch() },
    }}>
      {children}
    </AuthContext.Provider>
  )
}
