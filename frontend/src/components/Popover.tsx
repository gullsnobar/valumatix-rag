import { useEffect, useLayoutEffect, useRef } from 'react'
import type { ReactNode, RefObject } from 'react'
import { motion, useIsPresent, useReducedMotion } from 'motion/react'

export function Popover({
  children, id, label, onClose, busy = false, placement, restoreFocusTo,
}: {
  children: ReactNode
  id: string
  label: string
  onClose: () => void
  busy?: boolean
  placement?: 'above' | 'below'
  restoreFocusTo?: RefObject<HTMLElement | null>
}) {
  const popup = useRef<HTMLDivElement>(null)
  const reduced = useReducedMotion()
  const present = useIsPresent()

  useLayoutEffect(() => {
    const element = popup.current
    const anchor = element?.parentElement
    if (!element || !anchor) return
    if (placement) {
      element.dataset.placement = placement
      return
    }
    const scrollArea = anchor.closest('.page-scroll')

    function place() {
      if (!element || !anchor) return
      const area = scrollArea?.getBoundingClientRect()
      const bounds = anchor.getBoundingClientRect()
      const height = element.offsetHeight + 4
      const below = Math.min(window.innerHeight, area?.bottom ?? Infinity) - bounds.bottom
      const above = bounds.top - Math.max(0, area?.top ?? 0)
      element.dataset.placement = below < height && above > below ? 'above' : 'below'
    }

    place()
    scrollArea?.addEventListener('scroll', place, { passive: true })
    window.addEventListener('resize', place)
    return () => {
      scrollArea?.removeEventListener('scroll', place)
      window.removeEventListener('resize', place)
    }
  }, [busy, placement])

  useEffect(() => {
    const target = popup.current
    const trigger = restoreFocusTo?.current ?? document.activeElement
    target?.querySelector<HTMLElement>('[data-initial-focus], button:not(:disabled)')?.focus()
    return () => {
      if (trigger instanceof HTMLElement && trigger.isConnected
        && (target?.contains(document.activeElement) || document.activeElement === document.body)) trigger.focus()
    }
  }, [restoreFocusTo])

  useEffect(() => {
    if (!present) return
    const onKey = (event: KeyboardEvent) => {
      if (event.key === 'Escape' && !busy && !document.querySelector('dialog[open]')) {
        event.preventDefault()
        event.stopPropagation()
        onClose()
      } else if (event.key === 'Tab' && !busy) {
        const target = popup.current
        requestAnimationFrame(() => {
          if (target?.isConnected && !target.parentElement?.contains(document.activeElement)) onClose()
        })
      }
    }
    const onPointer = (event: PointerEvent) => {
      if (event.target instanceof Node && !popup.current?.parentElement?.contains(event.target) && !busy) {
        onClose()
      }
    }
    document.addEventListener('keydown', onKey)
    document.addEventListener('pointerdown', onPointer)
    return () => {
      document.removeEventListener('keydown', onKey)
      document.removeEventListener('pointerdown', onPointer)
    }
  }, [busy, onClose, present])

  const hidden = { opacity: 0, scale: reduced ? 1 : 0.98 }
  return <motion.div className="popover" id={id} role="dialog" aria-label={label} ref={popup}
    inert={!present} initial={reduced ? false : hidden} animate={{ opacity: 1, scale: 1 }} exit={hidden}
    transition={{ duration: reduced ? 0 : 0.16, ease: 'easeOut' }}>{children}</motion.div>
}
