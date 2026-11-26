import { useEffect, useRef, useState } from 'react'
import { useQuery } from '@tanstack/react-query'
import { BarChart3, CircleHelp, ExternalLink, FileText, Menu, MessageSquareText, PanelLeftClose, PanelLeftOpen } from 'lucide-react'
import { motion, useReducedMotion } from 'motion/react'
import { Link, matchPath, NavLink, Outlet, useLocation, useNavigate } from 'react-router'
import { API_DOCS_URL, api } from '../api/client.ts'
import type { HealthOut, UserOut } from '../api/types.ts'
import { useAuth } from '../hooks/auth.ts'
import { useRouteNotice } from '../hooks/notices.ts'
import type { ShellContext } from '../hooks/shell.ts'
import { useTheme } from '../hooks/theme.ts'
import { useConversation } from '../hooks/useConversation.ts'
import { useDocuments } from '../hooks/useDocuments.ts'
import { useMediaQuery } from '../hooks/useMediaQuery.ts'
import { useSampleDocuments } from '../hooks/useSampleDocuments.ts'
import { useUploadQueue } from '../hooks/useUploadQueue.ts'
import { Brand } from './Brand.tsx'
import { HowItWorks } from './HowItWorks.tsx'
import { Notice } from './Notice.tsx'
import { ProfileMenu, SignOutDialog } from './ProfileMenu.tsx'
import { SlideOver } from './SlideOver.tsx'
import { ThemeControl } from './ThemeControl.tsx'

const navigation = [
  { path: '/', label: 'Ask', description: 'Ask questions and check the source passages.', Icon: MessageSquareText },
  { path: '/documents', label: 'Documents', description: 'Manage the files PolicyDesk RAG searches.', Icon: FileText },
  { path: '/insights', label: 'Insights', description: 'Review usage, response times, and providers.', Icon: BarChart3 },
]
const railKey = 'tarnwick-rail-collapsed'
const guideKey = 'policydesk_guide_seen'

function HealthIndicator({ health, failed }: { health?: HealthOut; failed: boolean }) {
  const status = failed || health?.status === 'unavailable' ? 'degraded' : health?.status === 'ok' ? 'ok' : 'pending'
  const label = status === 'ok' ? 'All systems operational' : status === 'degraded' ? 'Service degraded' : 'Checking service status'
  const details = health && status === 'degraded'
    ? `${label} · database ${health.database} · embeddings ${health.embedding_service}` : label
  return <div className={'health-status health-' + status} role="status" aria-label={label} title={details}>
    <span className="health-dot" aria-hidden="true" /><span className="rail-label">{label}</span>
  </div>
}

export function AppShell({ user }: { user: UserOut }) {
  const [notice, setNotice] = useRouteNotice()
  const [railCollapsed, setRailCollapsed] = useState(() => localStorage.getItem(railKey) === 'true')
  const [drawer, setDrawer] = useState<'navigation' | 'guide' | null>(() =>
    localStorage.getItem(guideKey) === 'true' ? null : 'guide')
  const [profileOpen, setProfileOpen] = useState(false)
  const [draft, setDraft] = useState('')
  const [signOut, setSignOut] = useState<{ trigger: HTMLButtonElement | null } | null>(null)
  const uploadsInput = useRef<HTMLInputElement>(null)
  const mobile = useMediaQuery('(width < 1024px)')
  const reduced = useReducedMotion()
  const location = useLocation()
  const navigate = useNavigate()
  const { logout } = useAuth()
  const page = navigation.find(({ path }) => matchPath(path, location.pathname)) ?? navigation[0]
  const { theme, select } = useTheme()
  const uploads = useUploadQueue(user.id)
  const samples = useSampleDocuments(user.id, setNotice)
  const conversation = useConversation(user.id, setNotice)
  const documents = useDocuments(user.id)
  const health = useQuery({
    queryKey: ['health'], queryFn: ({ signal }) => api.health(signal), refetchInterval: 30_000, retry: false,
  })

  useEffect(() => {
    if (drawer === 'guide') localStorage.setItem(guideKey, 'true')
  }, [drawer])

  function closeDrawer() {
    setDrawer(null)
    setProfileOpen(false)
  }

  function openGuide() {
    setProfileOpen(false)
    setDrawer('guide')
  }

  function chooseQuestion(question: string) {
    setDraft(question)
    closeDrawer()
    void navigate('/')
    requestAnimationFrame(() => document.getElementById('policy-question')?.focus())
  }

  function toggleRail() {
    const next = !railCollapsed
    localStorage.setItem(railKey, String(next))
    setRailCollapsed(next)
  }

  const pickFiles = () => uploadsInput.current?.click()
  const data: ShellContext = {
    ownerId: user.id, uploads, conversation, notify: setNotice, pickFiles,
    draft, setDraft, addingSamples: samples.isPending,
    loadSamples: () => { if (!samples.isPending) samples.mutate() },
  }

  function railContents(collapsed: boolean, canCollapse: boolean) {
    return <div className={'rail-content' + (collapsed ? ' rail-collapsed' : '')}>
      <Link to="/" className="rail-brand" aria-label="PolicyDesk RAG" title={collapsed ? 'PolicyDesk RAG' : undefined}
        onClick={closeDrawer}><Brand /></Link>
      {canCollapse && <button type="button" className="icon-button rail-toggle"
        aria-label={collapsed ? 'Expand navigation' : 'Collapse navigation'} aria-expanded={!collapsed}
        onClick={toggleRail} title={collapsed ? 'Expand navigation' : 'Collapse navigation'}>
        {collapsed ? <PanelLeftOpen /> : <PanelLeftClose />}
      </button>}
      <div className="rail-main">
        <nav className="rail-links" aria-label="Main navigation">
          {navigation.map(({ path, label, Icon }) => <NavLink key={path} to={path} end onClick={closeDrawer}
            title={collapsed ? label : undefined} aria-label={label + (path === '/documents' && documents.data
              ? ', ' + documents.data.total + ' uploaded' : '')}
            className={({ isActive }) => 'rail-link' + (isActive ? ' selected' : '')}>
            <Icon aria-hidden="true" />
            <span className="rail-label">{label}</span>
            {path === '/documents' && <span className="rail-count rail-label mono" aria-hidden="true">
              {documents.data?.total ?? '—'}
            </span>}
          </NavLink>)}
        </nav>
        <section className="rail-help" aria-label="Help">
          <h2 className="rail-label">Help</h2>
          <button className="rail-link" type="button" aria-label="How it works" aria-haspopup="dialog"
            title={collapsed ? 'How it works' : undefined}
            onClick={openGuide}><CircleHelp aria-hidden="true" /><span className="rail-label">How it works</span></button>
          <a className="rail-link" href={API_DOCS_URL} target="_blank" rel="noopener noreferrer"
            aria-label="API documentation (opens in a new tab)" title={collapsed ? 'API documentation' : undefined}>
            <ExternalLink aria-hidden="true" /><span className="rail-label">API documentation</span>
          </a>
        </section>
        <div className="rail-preferences"><ThemeControl theme={theme} selectTheme={select} /></div>
      </div>
      <div className="rail-health"><HealthIndicator health={health.data} failed={health.isError} /></div>
    </div>
  }

  return (
    <div className="app-frame">
      <a className="skip-link" href="#main-content">Skip to main content</a>
      <input ref={uploadsInput} type="file" multiple accept=".pdf,.docx,.pptx,.md,.txt" hidden
        aria-label="Choose documents to upload" onChange={(event) => {
          const files = Array.from(event.currentTarget.files ?? [])
          event.currentTarget.value = ''
          uploads.enqueue(files)
        }} />
      {!mobile && <motion.aside className="nav-rail" aria-label="Workspace navigation" initial={false}
        animate={{ width: railCollapsed ? 72 : 240 }} transition={{ duration: reduced ? 0 : 0.2, ease: 'easeOut' }}>
        {railContents(railCollapsed, true)}
      </motion.aside>}
      <div className="workspace">
        <header className="top-bar">
          <div className="page-container top-bar-inner">
            {mobile && <button className="icon-button" type="button" aria-label="Open navigation"
              aria-expanded={drawer === 'navigation'} aria-controls={drawer === 'navigation' ? 'mobile-navigation' : undefined}
              onClick={() => { setProfileOpen(false); setDrawer('navigation') }}><Menu /></button>}
            <div className="top-bar-heading"><h1>{page.label}</h1><p className="muted">{page.description}</p></div>
            <div className="top-bar-actions">
              <button className="icon-button" type="button" aria-label="Help" title="How it works"
                aria-haspopup="dialog" onClick={openGuide}><CircleHelp /></button>
              <ProfileMenu email={user.email} open={profileOpen}
                setOpen={setProfileOpen} requestSignOut={(trigger) => setSignOut({ trigger })} />
            </div>
          </div>
        </header>
        <main key={page.path} id="main-content" tabIndex={-1}
          className={'app-content ' + (page.path === '/' ? 'app-content-ask' : 'page-scroll')}>
          <Outlet context={data} />
        </main>
      </div>
      <SlideOver open={drawer === 'guide' || (mobile && drawer === 'navigation')}
        variant={drawer === 'guide' ? 'guide' : 'navigation'}
        title={drawer === 'guide' ? 'How it works' : 'Navigation'}
        side={drawer === 'guide' ? 'right' : 'left'}
        id={drawer === 'guide' ? 'policy-guide' : 'mobile-navigation'} onClose={closeDrawer}
        footer={drawer === 'guide' && <button className="button primary" type="button" onClick={closeDrawer}>Got it</button>}>
        {drawer === 'guide' ? <HowItWorks chooseQuestion={chooseQuestion} /> : railContents(false, false)}
      </SlideOver>
      {signOut && <SignOutDialog trigger={signOut.trigger} close={() => setSignOut(null)} confirm={() => {
        void navigate('/login', { replace: true, state: { message: 'You have been signed out of PolicyDesk RAG.' } })
        logout()
      }} />}
      {notice && <Notice notice={notice} dismiss={() => setNotice(null)} />}
    </div>
  )
}
