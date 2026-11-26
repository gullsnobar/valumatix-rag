import { useEffect, useId, useRef } from 'react'
import type { ReactNode } from 'react'
import { AnimatePresence, motion, useIsPresent, useReducedMotion } from 'motion/react'

function DrawerPanel({
  children, title, onClose, side, id, variant, footer,
}: {
  children: ReactNode
  title: string
  onClose: () => void
  side: 'left' | 'right'
  id?: string
  variant?: 'navigation' | 'guide'
  footer?: ReactNode
}) {
  const titleId = useId()
  const panel = useRef<HTMLElement>(null)
  const close = useRef<HTMLButtonElement>(null)
  const reduced = useReducedMotion()
  const present = useIsPresent()
  const offset = reduced ? 0 : side === 'right' ? '100%' : '-100%'

  useEffect(() => {
    const previous = document.activeElement
    const target = panel.current
    close.current?.focus()
    return () => {
      if (previous instanceof HTMLElement && previous.isConnected
        && (target?.contains(document.activeElement) || document.activeElement === document.body)) previous.focus()
    }
  }, [])

  useEffect(() => {
    if (!present) return
    function onKey(event: KeyboardEvent) {
      if (event.defaultPrevented || document.querySelector('dialog[open]')) return
      if (event.key === 'Escape') {
        event.preventDefault()
        onClose()
      }
      if (event.key !== 'Tab') return
      const focusable = [...(panel.current?.querySelectorAll<HTMLElement>(
        'button:not(:disabled), a[href], input:not(:disabled), textarea:not(:disabled), summary, [tabindex="0"]',
      ) ?? [])].filter((element) => element.getClientRects().length > 0
        && !element.matches('input[type="radio"]:not(:checked)'))
      const first = focusable[0]
      const last = focusable.at(-1)
      const active = document.activeElement
      if (event.shiftKey && (active === first || !panel.current?.contains(active))) {
        event.preventDefault()
        last?.focus()
      } else if (!event.shiftKey && (active === last || !panel.current?.contains(active))) {
        event.preventDefault()
        first?.focus()
      }
    }
    window.addEventListener('keydown', onKey)
    return () => window.removeEventListener('keydown', onKey)
  }, [onClose, present])

  return (
    <motion.div
      className="drawer-layer" initial={{ opacity: 0 }} animate={{ opacity: 1 }} exit={{ opacity: 0 }}
      transition={{ duration: reduced ? 0 : 0.18, ease: 'easeOut' }}
    >
      <div className="drawer-backdrop" aria-hidden="true" onClick={onClose} />
      <motion.aside
        id={id} className={'drawer drawer-' + side + (variant ? ' drawer-' + variant : '')}
        ref={panel} role="dialog" aria-modal="true"
        aria-labelledby={titleId} initial={{ x: offset }} animate={{ x: 0 }} exit={{ x: offset }}
        transition={{ duration: reduced ? 0 : 0.2, ease: 'easeOut' }}
      >
        <div className="drawer-header">
          <h2 id={titleId}>{title}</h2>
          <button className="button secondary compact" type="button" ref={close} onClick={onClose}>Close</button>
        </div>
        <div className="drawer-content">{children}</div>
        {footer && <div className="drawer-footer">{footer}</div>}
      </motion.aside>
    </motion.div>
  )
}

export function SlideOver({
  open, children, title, onClose, side = 'right', id, variant, footer,
}: {
  open: boolean
  children: ReactNode
  title: string
  onClose: () => void
  side?: 'left' | 'right'
  id?: string
  variant?: 'navigation' | 'guide'
  footer?: ReactNode
}) {
  return <AnimatePresence mode="wait">{open && <DrawerPanel
    key={title} title={title} onClose={onClose} side={side} id={id} variant={variant} footer={footer}
  >{children}</DrawerPanel>}</AnimatePresence>
}
