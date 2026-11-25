import { StrictMode } from 'react'
import { createRoot } from 'react-dom/client'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { MotionConfig } from 'motion/react'
import '@fontsource/ibm-plex-sans/latin-400.css'
import '@fontsource/ibm-plex-sans/latin-500.css'
import '@fontsource/ibm-plex-sans/latin-600.css'
import '@fontsource/ibm-plex-mono/latin-400.css'
import App from './App.tsx'
import { AuthProvider } from './components/AuthProvider.tsx'
import { ApiError } from './api/client.ts'
import { applyTheme, readTheme } from './hooks/theme.ts'
import './styles.css'

applyTheme(readTheme())

const client = new QueryClient({
  defaultOptions: {
    queries: {
      staleTime: 5_000,
      retry: (count, error) => count < 1 && (!(error instanceof ApiError) || error.status === 0 || error.status >= 500),
    },
  },
})

createRoot(document.getElementById('root')!).render(
  <StrictMode>
    <QueryClientProvider client={client}>
      <MotionConfig reducedMotion="user">
        <AuthProvider><App /></AuthProvider>
      </MotionConfig>
    </QueryClientProvider>
  </StrictMode>,
)
