import type { ReactNode } from 'react'
import { motion, useReducedMotion } from 'motion/react'
import handbookPhoto from '../assets/policy-handbook.jpg'
import { Brand } from './Brand.tsx'

const headline = 'Ask about company policies.'
const supportingLine = 'Every answer shows its source.'

export function AuthLayout({ children }: { children: ReactNode }) {
  const reduced = useReducedMotion()
  return (
    <main className="auth-screen">
      <aside className="auth-aside" aria-label="About PolicyDesk RAG">
        <Brand />
        <div className="auth-story">
          <img className="auth-photo" src={handbookPhoto} width={1536} height={1024}
            alt="A magnifying glass over a highlighted passage in an open handbook." loading="lazy" />
          <div className="auth-story-copy">
            <h2>{headline}</h2>
            <p>{supportingLine}</p>
          </div>
        </div>
        <p className="auth-footer">© 2026 Tarnwick Consulting · Fictional demo company</p>
      </aside>
      <div className="auth-form-area">
        <motion.div className="auth-panel" initial={reduced ? false : { opacity: 0 }}
          animate={{ opacity: 1 }} transition={{ duration: reduced ? 0 : 0.18, ease: 'easeOut' }}>
          <div className="auth-mobile-brand">
            <Brand />
            <p className="muted">{headline} {supportingLine}</p>
          </div>
          {children}
        </motion.div>
      </div>
    </main>
  )
}
