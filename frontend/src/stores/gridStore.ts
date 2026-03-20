import { create } from 'zustand'
import type { GridState, GridAlert, ForecastData } from '../types'

interface GridStore {
  gridState: GridState | null
  alerts: GridAlert[]
  forecasts: { solar?: ForecastData; load?: ForecastData; flex?: ForecastData }
  wsConnected: boolean
  lastUpdated: string | null
  setGridState: (state: GridState) => void
  setAlerts: (alerts: GridAlert[]) => void
  addAlert: (alert: GridAlert) => void
  acknowledgeAlert: (id: string) => void
  setForecasts: (forecasts: { solar?: ForecastData; load?: ForecastData; flex?: ForecastData }) => void
  setWsConnected: (v: boolean) => void
}

export const useGridStore = create<GridStore>((set) => ({
  gridState: null,
  alerts: [],
  forecasts: {},
  wsConnected: false,
  lastUpdated: null,
  setGridState: (state) =>
    set({ gridState: state, lastUpdated: new Date().toISOString() }),
  setAlerts: (alerts) => set({ alerts }),
  addAlert: (alert) =>
    set((s) => ({ alerts: [alert, ...s.alerts].slice(0, 100) })),
  acknowledgeAlert: (id) =>
    set((s) => ({
      alerts: s.alerts.map((a) =>
        a.id === id ? { ...a, is_acknowledged: true } : a
      ),
    })),
  setForecasts: (forecasts) => set({ forecasts }),
  setWsConnected: (v) => set({ wsConnected: v }),
}))
