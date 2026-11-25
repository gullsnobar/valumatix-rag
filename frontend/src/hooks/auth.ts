import { createContext, useContext } from 'react'
import type { Credentials, UserOut } from '../api/types.ts'

interface AuthContextValue {
  status: 'anonymous' | 'pending' | 'ready' | 'error'
  user: UserOut | undefined
  authenticate: (mode: 'login' | 'signup', credentials: Credentials, signal?: AbortSignal) => Promise<UserOut>
  logout: () => void
  retry: () => void
}

export const AuthContext = createContext<AuthContextValue | null>(null)

export function useAuth(): AuthContextValue {
  const value = useContext(AuthContext)
  if (!value) throw new Error('AuthProvider is required.')
  return value
}
