import { useId } from 'react'
import { Monitor, Moon, Sun } from 'lucide-react'
import type { Theme } from '../hooks/theme.ts'

const options = [
  { value: 'light', label: 'Light', Icon: Sun },
  { value: 'dark', label: 'Dark', Icon: Moon },
  { value: 'system', label: 'System', Icon: Monitor },
] as const

export function ThemeControl({ theme, selectTheme }: {
  theme: Theme
  selectTheme: (theme: Theme) => void
}) {
  const group = useId()
  return <fieldset className="theme-setting" aria-label="Theme">
    <legend className="rail-label">Theme</legend>
    <div className="theme-segments">
      {options.map(({ value, label, Icon }) => <label key={value} title={label}>
        <input className="sr-only" type="radio" name={group} value={value} checked={theme === value}
          aria-label={label} onChange={() => selectTheme(value)} />
        <span className="theme-choice"><Icon aria-hidden="true" /><span className="rail-label">{label}</span></span>
      </label>)}
    </div>
  </fieldset>
}
