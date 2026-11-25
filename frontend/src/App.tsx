import { BrowserRouter, Navigate, Route, Routes, useLocation } from 'react-router'
import { AppShell } from './components/AppShell.tsx'
import { AskPage } from './components/AskPage.tsx'
import { AuthPage } from './components/AuthPage.tsx'
import { AuthLayout } from './components/AuthLayout.tsx'
import { DocumentsPage } from './components/DocumentsPage.tsx'
import { InsightsPage } from './components/InsightsPage.tsx'
import { InlineError, SkeletonRows } from './components/Notice.tsx'
import { useAuth } from './hooks/auth.ts'

function ProtectedRoute() {
  const auth = useAuth()
  const location = useLocation()
  if (auth.status === 'anonymous') return <Navigate to="/login" state={{ from: location.pathname }} replace />
  if (auth.status === 'ready' && auth.user) return <AppShell key={auth.user.id} user={auth.user} />
  return (
    <AuthLayout>
        <h1>PolicyDesk RAG</h1>
        {auth.status === 'error'
          ? <><InlineError message="Could not verify your session." retry={auth.retry} />
            <button className="button ghost" type="button" onClick={auth.logout}>Sign out</button></>
          : <SkeletonRows rows={2} />}
    </AuthLayout>
  )
}

export default function App() {
  return (
    <BrowserRouter>
      <Routes>
        <Route path="/login" element={<AuthPage key="login" mode="login" />} />
        <Route path="/signup" element={<AuthPage key="signup" mode="signup" />} />
        <Route element={<ProtectedRoute />}>
          <Route index element={<AskPage />} />
          <Route path="documents" element={<DocumentsPage />} />
          <Route path="insights" element={<InsightsPage />} />
        </Route>
        <Route path="*" element={<Navigate to="/" replace />} />
      </Routes>
    </BrowserRouter>
  )
}
