import { useEffect, useId, useRef } from 'react'
import { LogOut } from 'lucide-react'
import { AnimatePresence } from 'motion/react'
import type { Theme } from '../hooks/theme.ts'
import { Popover } from './Popover.tsx'

function displayProfile(email: string) {
  const local = email.split('@')[0]
  const words = local.split(/[._-]+/).filter(Boolean)
  const initials = local.split(/[._\d-]+/).filter(Boolean)
  const letters = initials.length >= 2
    ? initials[0][0] + initials[1][0] : (initials[0] ?? local).slice(0, 2)
  return {
    initials: letters.toUpperCase(),
    name: words.map((word) => word[0].toUpperCase() + word.slice(1)).join(' ') || local,
  }
}

const themes: { value: Theme; label: string }[] = [
  { value: 'light', label: 'Light' },
  { value: 'dark', label: 'Dark' },
  { value: 'system', label: 'System' },
]

export function ProfileMenu({
  email, theme, selectTheme, open, setOpen, requestSignOut,
}: {
  email: string
  theme: Theme
  selectTheme: (theme: Theme) => void
  open: boolean
  setOpen: (open: boolean) => void
  requestSignOut: (trigger: HTMLButtonElement | null) => void
}) {
  const id = useId()
  const trigger = useRef<HTMLButtonElement>(null)
  const profile = displayProfile(email)
  return <div className="popover-anchor profile-anchor">
    <button type="button" className="profile-trigger" ref={trigger} aria-expanded={open}
      aria-label={'Profile menu for ' + email} title={profile.name}
      aria-controls={open ? id : undefined} onClick={() => setOpen(!open)}>
      <span className="avatar" aria-hidden="true">{profile.initials}</span>
    </button>
    <AnimatePresence>{open && <Popover id={id} label="Profile settings" placement="below"
      onClose={() => setOpen(false)} restoreFocusTo={trigger}>
      <div className="profile-card">
        <span className="avatar" aria-hidden="true">{profile.initials}</span>
        <div className="profile-identity">
          <span>{profile.name}</span><span className="profile-email muted" title={email}>{email}</span>
        </div>
      </div>
      <fieldset className="theme-setting">
        <legend>Theme</legend>
        <div className="theme-segments">
          {themes.map(({ value, label }) => <label key={value}>
            <input className="sr-only" type="radio" name={id + '-theme'} value={value}
              checked={theme === value} data-initial-focus={theme === value ? '' : undefined}
              onChange={() => selectTheme(value)} />
            <span>{label}</span>
          </label>)}
        </div>
      </fieldset>
      <button className="button ghost sign-out" type="button" onClick={() => {
        setOpen(false)
        requestSignOut(trigger.current)
      }}><LogOut /> Sign out</button>
    </Popover>}</AnimatePresence>
  </div>
}

export function SignOutDialog({ close, confirm, trigger }: {
  close: () => void
  confirm: () => void
  trigger: HTMLButtonElement | null
}) {
  const title = useId()
  const dialog = useRef<HTMLDialogElement>(null)
  const cancel = useRef<HTMLButtonElement>(null)
  const signOut = useRef<HTMLButtonElement>(null)
  useEffect(() => {
    const element = dialog.current
    element?.showModal()
    cancel.current?.focus()
    return () => {
      element?.close()
      if (trigger?.isConnected) trigger.focus()
    }
  }, [trigger])
  return <dialog className="sign-out-dialog" ref={dialog} aria-labelledby={title} onKeyDown={(event) => {
    if (event.key !== 'Tab') return
    const edge = event.shiftKey ? cancel.current : signOut.current
    if (document.activeElement === edge) {
      event.preventDefault()
      const next = event.shiftKey ? signOut.current : cancel.current
      next?.focus()
    }
  }} onCancel={(event) => {
    event.preventDefault()
    close()
  }}>
    <h2 id={title}>Sign out of PolicyDesk RAG?</h2>
    <div className="dialog-actions">
      <button type="button" className="button secondary" ref={cancel} onClick={close}>Cancel</button>
      <button type="button" className="button primary" ref={signOut} onClick={confirm}>Sign out</button>
    </div>
  </dialog>
}
