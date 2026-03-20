export interface Deployment {
  id: string
  slug: string
  name: string
  country: string
  currency_code: string
  timezone: string
  regulatory_framework: string
  settlement_cycle: string
}

export interface User {
  id: string
  email: string
  full_name: string
  is_superuser: boolean
  deployments: Array<{ deployment_id: string; role: string }>
}

export interface GridState {
  deployment_id: string
  timestamp: string
  total_gen_kw: number
  total_load_kw: number
  net_kw: number
  assets_online: number
  assets_curtailed: number
  assets_offline: number
  solar_factor: number
  load_factor: number
  nodes: GridNode[]
  assets: DERAssetLive[]
}

export interface GridNode {
  node_id: string
  node_type: 'FEEDER' | 'DISTRIBUTION_TRANSFORMER' | 'SUBSTATION'
  name: string
  cmz_id: string
  current_loading_pct: number
  voltage_l1_v?: number
  voltage_l2_v?: number
  voltage_l3_v?: number
  hosting_capacity_kw: number
  used_capacity_kw: number
  lat?: number
  lng?: number
}

export interface DERAssetLive {
  id: string
  asset_ref: string
  name: string
  type: string
  status: string
  feeder_id: string
  dt_id: string
  current_kw: number
  capacity_kw: number
  current_soc_pct?: number
  lat?: number
  lng?: number
  doe_export_max_kw?: number
  doe_import_max_kw?: number
}

export interface DERAsset {
  id: string
  deployment_id: string
  counterparty_id: string
  asset_ref: string
  name: string
  type: string
  status: string
  is_digital_twin: boolean
  feeder_id: string
  dt_id: string
  phase: string
  capacity_kw: number
  capacity_kwh?: number
  comm_capability: string
  current_kw: number
  current_soc_pct?: number
  last_telemetry_at?: string
  hosting_capacity_kw?: number
  lat?: number
  lng?: number
  doe_export_max_kw?: number
  doe_import_max_kw?: number
}

export interface Program {
  id: string
  deployment_id: string
  name: string
  type: string
  status: string
  target_mw: number
  enrolled_mw: number
  regulatory_basis?: string
  start_date: string
  end_date: string
}

export interface Contract {
  id: string
  deployment_id: string
  program_id: string
  counterparty_id: string
  contract_ref: string
  name: string
  type: string
  status: string
  cmz_id: string
  contracted_capacity_kw: number
  availability_rate_minor: number
  utilisation_rate_minor: number
  start_date: string
  end_date: string
}

export interface Counterparty {
  id: string
  deployment_id: string
  name: string
  type: string
  status: string
  portfolio_kw: number
  comm_capability: string
  prequalification_status: string
  contact_name: string
}

export interface FlexEvent {
  id: string
  deployment_id: string
  event_ref: string
  event_type: string
  status: string
  trigger: string
  target_kw: number
  dispatched_kw: number
  delivered_kw?: number
  start_time: string
  end_time?: string
  duration_minutes: number
  auto_generated: boolean
  cmz_id: string
  notes?: string
}

export interface GridAlert {
  id: string
  node_id?: string
  asset_id?: string
  alert_type: string
  severity: 'CRITICAL' | 'WARNING' | 'INFO'
  message: string
  is_acknowledged: boolean
  created_at: string
}

export interface ForecastPoint {
  timestamp: string
  value_kw: number
  confidence_low: number
  confidence_high: number
}

export interface ForecastData {
  type: string
  generated_at: string
  values: ForecastPoint[]
  model: string
}

export interface SettlementStatement {
  id: string
  deployment_id: string
  contract_id: string
  period_start: string
  period_end: string
  status: string
  availability_payment_minor: number
  utilisation_payment_minor: number
  penalty_amount_minor: number
  net_payment_minor: number
  currency_code: string
  events_count: number
  avg_delivery_pct: number
}

export interface TelemetryPoint {
  timestamp: string
  kw: number
  soc_pct?: number
  voltage_v?: number
  frequency_hz?: number
}

export interface AuditLog {
  id: string
  user_id: string
  user_email: string
  action: string
  resource_type: string
  resource_id: string
  details: string
  created_at: string
  ip_address?: string
}

export interface SystemHealth {
  database: 'healthy' | 'degraded' | 'down'
  simulation_engine: 'healthy' | 'degraded' | 'down'
  api_server: 'healthy' | 'degraded' | 'down'
  websocket: 'healthy' | 'degraded' | 'down'
  last_checked: string
  uptime_seconds: number
}

export interface OptimizationResult {
  target_kw: number
  achieved_kw: number
  assets: Array<{
    asset_id: string
    asset_name: string
    asset_type: string
    dispatch_kw: number
    reason: string
  }>
  ai_recommendation: string
  clearing_price?: number
}

export interface ReportSummary {
  events_this_month: number
  flex_delivered_mwh: number
  avg_delivery_pct: number
  settlement_pending_minor: number
  currency_code: string
  top_performers: Array<{ name: string; delivery_pct: number; events: number }>
  monthly_trend: Array<{ month: string; delivered_mwh: number; events: number }>
}
