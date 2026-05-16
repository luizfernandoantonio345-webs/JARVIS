const DEFAULT_WS_PATH = '/ws/jarvis'

export function getWebSocketUrl(path: string = DEFAULT_WS_PATH): string {
  const configured = import.meta.env.VITE_WS_URL as string | undefined
  if (configured && configured.trim()) {
    return configured.trim()
  }

  const protocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:'
  return `${protocol}//${window.location.host}${path}`
}
