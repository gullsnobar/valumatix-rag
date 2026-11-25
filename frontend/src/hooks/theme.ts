import { useEffect, useState } from 'react'

export type Theme = 'light' | 'dark' | 'system'
const themeKey = 'tarnwick-theme'
export function readTheme(): Theme {
  const saved = localStorage.getItem(themeKey)
  return saved === 'light' || saved === 'dark' ? saved : 'system'
}

export function applyTheme(theme: Theme) {
  if (theme === 'system') delete document.documentElement.dataset.theme
  else document.documentElement.dataset.theme = theme
}

export function useTheme() {
  const [theme, setTheme] = useState(readTheme)
  useEffect(() => {
    function syncTheme(event: StorageEvent) {
      if (event.key === themeKey || event.key === null) {
        const next = readTheme()
        applyTheme(next)
        setTheme(next)
      }
    }
    window.addEventListener('storage', syncTheme)
    return () => window.removeEventListener('storage', syncTheme)
  }, [])

  function select(next: Theme) {
    localStorage.setItem(themeKey, next)
    applyTheme(next)
    setTheme(next)
  }
  return { theme, select }
}
