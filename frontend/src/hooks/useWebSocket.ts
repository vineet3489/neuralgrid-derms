import { useEffect, useRef, useCallback } from 'react'
import { useGridStore } from '../stores/gridStore'
import { useAuthStore } from '../stores/authStore'
import type { GridAlert } from '../types'

const RECONNECT_DELAY = 3000
const MAX_RECONNECT_ATTEMPTS = 10

export function useWebSocket() {
  const wsRef = useRef<WebSocket | null>(null)
  const reconnectAttempts = useRef(0)
  const reconnectTimer = useRef<ReturnType<typeof setTimeout> | null>(null)
  const { setGridState, setWsConnected, addAlert } = useGridStore()
  const { token, currentDeployment } = useAuthStore()

  const connect = useCallback(() => {
    if (!token) return
    if (wsRef.current?.readyState === WebSocket.OPEN) return

    const proto = window.location.protocol === 'https:' ? 'wss:' : 'ws:'
    const wsUrl = `${proto}//${window.location.host}/ws`

    try {
      const ws = new WebSocket(wsUrl)
      wsRef.current = ws

      ws.onopen = () => {
        setWsConnected(true)
        reconnectAttempts.current = 0
        // Send auth token
        ws.send(JSON.stringify({ type: 'auth', token }))
      }

      ws.onclose = () => {
        setWsConnected(false)
        wsRef.current = null
        if (reconnectAttempts.current < MAX_RECONNECT_ATTEMPTS) {
          reconnectAttempts.current += 1
          reconnectTimer.current = setTimeout(connect, RECONNECT_DELAY)
        }
      }

      ws.onerror = () => {
        ws.close()
      }

      ws.onmessage = (event) => {
        try {
          const msg = JSON.parse(event.data as string)
          switch (msg.type) {
            case 'grid_update': {
              const stateForDep =
                msg.data?.[currentDeployment] || msg.data
              if (stateForDep) setGridState(stateForDep)
              break
            }
            case 'alert': {
              if (msg.data) addAlert(msg.data as GridAlert)
              break
            }
            case 'pong':
              break
          }
        } catch {
          // ignore parse errors
        }
      }
    } catch {
      // WebSocket not available or connection refused — silently fail
    }
  }, [token, currentDeployment, setGridState, setWsConnected, addAlert])

  useEffect(() => {
    connect()

    // Heartbeat
    const heartbeat = setInterval(() => {
      if (wsRef.current?.readyState === WebSocket.OPEN) {
        wsRef.current.send(JSON.stringify({ type: 'ping' }))
      }
    }, 30000)

    return () => {
      clearInterval(heartbeat)
      if (reconnectTimer.current) clearTimeout(reconnectTimer.current)
      wsRef.current?.close()
    }
  }, [connect])
}
