import axios from 'axios'
import { useAuthStore } from '../stores/authStore'

const API_BASE = import.meta.env.VITE_API_URL || ''

export const apiClient = axios.create({
  baseURL: `${API_BASE}/api/v1`,
  headers: { 'Content-Type': 'application/json' },
  timeout: 90000,   // 90s — accommodates Render free-tier cold-start (~60s)
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

  // Integration config
  integrations: () => apiClient.get('/integrations'),
  integration: (id: string) => apiClient.get(`/integrations/${id}`),
  createIntegration: (data: any) => apiClient.post('/integrations', data),
  updateIntegration: (id: string, data: any) => apiClient.put(`/integrations/${id}`, data),
  testIntegration: (id: string) => apiClient.post(`/integrations/${id}/test`),
  toggleIntegrationMode: (id: string) => apiClient.post(`/integrations/${id}/toggle-mode`),
  getSimParams: (id: string) => apiClient.get(`/integrations/${id}/sim-params`),
  updateSimParams: (id: string, params: any) => apiClient.put(`/integrations/${id}/sim-params`, params),

  // OE formatted messages
  oeMessagesFormatted: (eventId: string, protocol: string) =>
    apiClient.get(`/events/${eventId}/oe-messages/formatted?protocol=${protocol}`),

  // Aggregator
  aggregatorDevices: () => apiClient.get('/aggregator/devices'),
  registerAggregator: (data: any) => apiClient.post('/aggregator/register', data),

  // Power flow
  runPowerFlow: () => apiClient.post('/grid/power-flow'),

  // LV Network
  lvNetwork: (dtNodeId: string, provider?: string) =>
    apiClient.get(`/lv-network/dt/${dtNodeId}?provider=${provider || 'overpass'}`),
  lvNetworkPowerFlow: (dtNodeId: string) =>
    apiClient.post(`/lv-network/dt/${dtNodeId}/power-flow`),
  lvNetworkRebuild: (dtNodeId: string, provider: string) =>
    apiClient.get(`/lv-network/dt/${dtNodeId}?provider=${provider}&force_rebuild=true`),
  lvNetworkProviders: () => apiClient.get('/lv-network/providers'),
  lvNetworkList: () => apiClient.get('/lv-network/'),

  // SSEN OE format
  oeMessagesSSEN: (eventId: string) =>
    apiClient.get(`/events/${eventId}/oe-messages/formatted?protocol=SSEN_IEC`),

  // Enhanced forecasting
  forecastLVFeeder: (feederId: string) =>
    apiClient.get(`/forecasts/lv-feeder/${feederId}`),
  forecastAsset: (assetId: string) =>
    apiClient.get(`/forecasts/asset/${assetId}`),
  forecastOEHeadroom: (cmzId: string) =>
    apiClient.get(`/forecasts/oe-headroom/${cmzId}`),

  // Active events (for OE documents)
  activeEvents: (params?: Record<string, string>) =>
    apiClient.get('/events/active', { params }),

  // SCADA Gateway — endpoints
  scadaEndpoints: () => apiClient.get('/scada/endpoints'),
  createScadaEndpoint: (data: unknown) => apiClient.post('/scada/endpoints', data),
  updateScadaEndpoint: (id: string, data: unknown) => apiClient.put(`/scada/endpoints/${id}`, data),
  deleteScadaEndpoint: (id: string) => apiClient.delete(`/scada/endpoints/${id}`),
  pushScadaEndpoint: (id: string) => apiClient.post(`/scada/endpoints/${id}/push`),

  // SCADA Gateway — snapshot
  scadaSnapshot: () => apiClient.get('/scada/snapshot'),
  scadaSnapshotGrid: () => apiClient.get('/scada/snapshot/grid'),
  scadaSnapshotLvNetwork: () => apiClient.get('/scada/snapshot/lv-network'),
  scadaSnapshotAssets: () => apiClient.get('/scada/snapshot/assets'),
  scadaSnapshotOeLimits: () => apiClient.get('/scada/snapshot/oe-limits'),

  // SCADA Gateway — DaaS API keys
  daasKeys: () => apiClient.get('/scada/daas/keys'),
  createDaasKey: (data: unknown) => apiClient.post('/scada/daas/keys', data),
  revokeDaasKey: (id: string) => apiClient.delete(`/scada/daas/keys/${id}`),
  daasKeyUsage: (id: string) => apiClient.get(`/scada/daas/keys/${id}/usage`),

  // LV Network — area and congested DTs
  congestedDTs: (threshold_pct?: number, limit?: number) =>
    apiClient.get(`/lv-network/congested-dts?threshold_pct=${threshold_pct ?? 75}&limit=${limit ?? 20}`),
  lvNetworkArea: (south: number, west: number, north: number, east: number, provider?: string) =>
    apiClient.get(`/lv-network/area?south=${south}&west=${west}&north=${north}&east=${east}&provider=${provider ?? 'overpass'}`),

  // Dynamic OE (time-series DistFlow)
  dynamicOE: (cmzId: string, horizonHours?: number, recalculate?: boolean) =>
    apiClient.get(`/lv-network/dynamic-oe/${cmzId}?horizon_hours=${horizonHours ?? 48}&recalculate=${recalculate ?? false}`),

  // CIM aggregator — IEC 62325 + IEC 62746-4
  cimProtocols: () => apiClient.get('/aggregator/cim/protocols'),
  cimCapability: (data: unknown) => apiClient.post('/aggregator/cim/capability', data),
  cimStatus: (data: unknown) => apiClient.post('/aggregator/cim/status', data),
  cimDispatch: (eventId: string) => apiClient.get(`/aggregator/cim/dispatch/${eventId}`),
  cimBidTemplate: (cmzId: string) => apiClient.get(`/aggregator/cim/bid/${cmzId}`),
  cimSubmitBid: (data: unknown) => apiClient.post('/aggregator/cim/bid', data),
}
