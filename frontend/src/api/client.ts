import axios from 'axios'
import { useAuthStore } from '../stores/authStore'

const API_BASE = import.meta.env.VITE_API_URL || ''

export const apiClient = axios.create({
  baseURL: `${API_BASE}/api/v1`,
  headers: { 'Content-Type': 'application/json' }
})

// Auth token interceptor
apiClient.interceptors.request.use((config) => {
  const token = useAuthStore.getState().token
  const deployment = useAuthStore.getState().currentDeployment
  if (token) config.headers.Authorization = `Bearer ${token}`
  if (deployment) config.headers['X-Deployment-ID'] = deployment
  return config
})

// 401 auto-logout
apiClient.interceptors.response.use(
  (r) => r,
  (error) => {
    if (error.response?.status === 401) {
      useAuthStore.getState().logout()
    }
    return Promise.reject(error)
  }
)

// API helpers
export const api = {
  // Auth
  login: (email: string, password: string) =>
    apiClient.post('/auth/login', { email, password }),
  me: () => apiClient.get('/auth/me'),
  deployments: () => apiClient.get('/auth/deployments'),

  // Grid
  gridDashboard: () => apiClient.get('/grid/dashboard'),
  gridState: () => apiClient.get('/grid/state'),
  gridAlerts: () => apiClient.get('/grid/alerts'),
  acknowledgeAlert: (id: string) => apiClient.post(`/grid/alerts/${id}/acknowledge`),
  topology: () => apiClient.get('/grid/topology'),
  hostingCapacity: () => apiClient.get('/grid/hosting-capacity'),

  // Assets
  assets: (params?: Record<string, string>) =>
    apiClient.get('/assets', { params }),
  asset: (id: string) => apiClient.get(`/assets/${id}`),
  assetTelemetry: (id: string, hours = 24) =>
    apiClient.get(`/assets/${id}/telemetry?hours=${hours}`),
  createAsset: (data: unknown) => apiClient.post('/assets', data),
  updateAsset: (id: string, data: unknown) => apiClient.put(`/assets/${id}`, data),

  // Programs
  programs: (status?: string) =>
    apiClient.get(`/programs${status ? `?status=${status}` : ''}`),
  program: (id: string) => apiClient.get(`/programs/${id}`),
  programKpis: (id: string) => apiClient.get(`/programs/${id}/kpis`),
  createProgram: (data: unknown) => apiClient.post('/programs', data),
  updateProgram: (id: string, data: unknown) => apiClient.put(`/programs/${id}`, data),

  // Contracts
  contracts: (programId?: string) =>
    apiClient.get(`/contracts${programId ? `?program_id=${programId}` : ''}`),
  contract: (id: string) => apiClient.get(`/contracts/${id}`),
  createContract: (data: unknown) => apiClient.post('/contracts', data),
  activateContract: (id: string) => apiClient.post(`/contracts/${id}/activate`),
  simulateSettlement: (id: string, data: unknown) =>
    apiClient.post(`/contracts/${id}/simulate-settlement`, data),

  // Counterparties
  counterparties: (status?: string) =>
    apiClient.get(`/counterparties${status ? `?status=${status}` : ''}`),
  counterparty: (id: string) => apiClient.get(`/counterparties/${id}`),
  createCounterparty: (data: unknown) => apiClient.post('/counterparties', data),
  updateCounterparty: (id: string, data: unknown) =>
    apiClient.put(`/counterparties/${id}`, data),

  // Dispatch / Events
  events: (status?: string) =>
    apiClient.get(`/events${status ? `?status=${status}` : ''}`),
  event: (id: string) => apiClient.get(`/events/${id}`),
  createEvent: (data: unknown) => apiClient.post('/events', data),
  dispatchEvent: (id: string) => apiClient.post(`/events/${id}/dispatch`),
  cancelEvent: (id: string) => apiClient.post(`/events/${id}/cancel`),

  // Settlement
  settlements: (contractId?: string) =>
    apiClient.get(`/settlement${contractId ? `?contract_id=${contractId}` : ''}`),
  calculateSettlement: (data: unknown) => apiClient.post('/settlement/calculate', data),
  approveSettlement: (id: string) => apiClient.post(`/settlement/${id}/approve`),

  // Forecasting
  forecastAll: () => apiClient.get('/forecasting/all'),
  forecastRefresh: () => apiClient.post('/forecasting/refresh'),

  // Optimization
  optimizeDR: (data: unknown) => apiClient.post('/optimization/dr-dispatch', data),
  optimizationRecommendations: () => apiClient.get('/optimization/recommendations'),
  recalculateDOEs: () => apiClient.post('/optimization/recalculate-does'),
  p2pMarket: (data: unknown) => apiClient.post('/optimization/p2p-market', data),

  // Admin
  auditLogs: (params?: Record<string, string>) =>
    apiClient.get('/admin/audit-logs', { params }),
  systemHealth: () => apiClient.get('/admin/system-health'),
  users: () => apiClient.get('/admin/users'),
  inviteUser: (data: unknown) => apiClient.post('/admin/users/invite', data),
  deploymentConfig: () => apiClient.get('/admin/config'),
  updateConfig: (data: unknown) => apiClient.put('/admin/config', data),

  // Reports
  reportSummary: () => apiClient.get('/reports/summary'),
  exportReport: (format: string) =>
    apiClient.get(`/reports/export?format=${format}`, { responseType: 'blob' }),
}
