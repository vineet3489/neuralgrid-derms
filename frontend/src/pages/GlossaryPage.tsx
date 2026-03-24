import React, { useState } from 'react'
import { Search, ChevronRight, ExternalLink } from 'lucide-react'
import clsx from 'clsx'

// ─── Data ─────────────────────────────────────────────────────────────────────

const GLOSSARY_TERMS = [
  { term: 'ADMS', full: 'Advanced Distribution Management System', def: 'Utility-grade software (e.g. GE ADMS, OSIsoft PI) that monitors and controls medium-voltage (11 kV / 33 kV) distribution assets. Neural Grid connects to ADMS via the Integrations config manager and can operate independently when ADMS is unavailable.' },
  { term: 'BESS', full: 'Battery Energy Storage System', def: 'A grid-connected battery asset. In Neural Grid, BESS assets participate in flex dispatch as dispatchable storage — they can absorb excess solar (charge) or discharge to meet peak demand.' },
  { term: 'CMZ', full: 'Constraint Management Zone', def: 'A geographic grouping of assets and LV feeders managed under a single Operating Envelope. Each deployment has one or more CMZs. Flex offers and OE limits are scoped to a CMZ.' },
  { term: 'CPN', full: 'Customer/Connection Point Number', def: 'The unique identifier assigned to a connection point (home or business) on the LV network by the Distribution Network Operator.' },
  { term: 'DaaS', full: 'Data-as-a-Service', def: "L&T's commercial model for selling LV DERMS data to external SCADA operators. Clients receive scoped API keys (X-DaaS-Key header) with per-field read permissions and rate limits. Usage is metered for billing." },
  { term: 'DER', full: 'Distributed Energy Resource', def: 'Any small-scale energy asset connected at LV or MV: solar PV, battery storage, EV chargers, heat pumps, or flexible industrial loads. The core unit managed by a DERMS.' },
  { term: 'DERMS', full: 'Distributed Energy Resource Management System', def: 'Software platform that aggregates, monitors, forecasts, and dispatches DERs. Neural Grid is a multi-deployment DERMS covering the full stack from LV feeder modelling to OE messaging.' },
  { term: 'DistFlow', full: 'Distribution Power Flow (Baran & Wu 1989)', def: 'A backward-forward sweep power flow algorithm optimised for radial LV networks. Neural Grid runs DistFlow behind each DT when GE ADMS is absent, computing bus voltages (p.u.), branch currents, and losses.' },
  { term: 'DNO', full: 'Distribution Network Operator', def: 'The licensed entity that owns and operates the distribution network (SSEN for Scotland/south England; PUVVNL for Varanasi UP). Neural Grid is sold to DNOs and large aggregators.' },
  { term: 'DNP3', full: 'Distributed Network Protocol 3', def: 'A serial/IP protocol used in utility SCADA systems. Neural Grid supports DNP3 push via the L&T Edge Agent hardware gateway.' },
  { term: 'DOE', full: 'Dynamic Operating Envelope', def: 'Time-varying export/import limits assigned to individual DER assets. Derived from the OE headroom forecast and the DistFlow power flow result. Neural Grid recalculates DOEs every 30 minutes.' },
  { term: 'DT', full: 'Distribution Transformer', def: 'A 11 kV/0.4 kV transformer that steps down voltage to supply LV customers. Each DT is the root node of an LV feeder network modelled by Neural Grid using OSM or synthetic topology.' },
  { term: 'ENA-CPP-2024', full: 'ENA Common Power Platform 2024', def: 'The UK regulatory framework governing flexibility markets and OE messaging between DNOs and aggregators. SSEN deployment uses this protocol.' },
  { term: 'EV', full: 'Electric Vehicle', def: 'V1G (smart charge) and V2G (vehicle-to-grid) EV assets are modelled as flex-capable DERs. Neural Grid forecasts EV arrival patterns and dispatch availability.' },
  { term: 'Flex Dispatch', full: 'Flexibility Dispatch Event', def: 'A scheduled or emergency request to DER assets to modify their output. Neural Grid creates FlexEvent records with MW targets, dispatches them via IEEE 2030.5 or OpenADR, and tracks performance for settlement.' },
  { term: 'GIS', full: 'Geographic Information System', def: 'Neural Grid uses OpenStreetMap (via Overpass API) as its GIS layer. The GIS map shows assets, DTs, LV feeder routes, CMZ boundaries, and individual homes at zoom ≥ 15.' },
  { term: 'IEEE 2030.5', full: 'IEEE Smart Energy Profile 2.0', def: 'A REST-based protocol for communicating with DER aggregators and smart inverters. Neural Grid acts as the VTN (Virtual Top Node) and issues DOE, DER control, and pricing signals.' },
  { term: 'LV', full: 'Low Voltage (400 V / 230 V)', def: 'The final distribution tier from DT to homes. Invisible to most ADMS systems — Neural Grid fills this gap by modelling LV feeders using OSM topology and DistFlow power flow.' },
  { term: 'mRID', full: 'Master Resource Identifier', def: 'Unique identifier in IEC CIM / MarketDocument models. Neural Grid uses the convention OE-{event_ref}-{cmz_slug}-{yyyymmddHHMM} for OE documents.' },
  { term: 'MODBUS', full: 'Modbus TCP', def: 'A legacy industrial protocol used by older SCADA systems. Neural Grid supports Modbus push via the L&T Edge Agent hardware gateway.' },
  { term: 'OE', full: 'Operating Envelope', def: 'Time-bounded MW limits (import and export) for a CMZ or individual asset. SSEN uses IEC MarketDocument format (process.processType = "Z01"). Quantities are in MW (unit: MAW).' },
  { term: 'OpenADR', full: 'Open Automated Demand Response 2.0b', def: 'An OASIS standard for demand response signalling. Neural Grid supports OpenADR 2.0b EiEvent/EiReport for the aggregator VTN interface.' },
  { term: 'OSM', full: 'OpenStreetMap', def: 'The open-source global map used by Neural Grid for LV feeder topology. Queried via Overpass API for power=cable voltage~400|230. Falls back to synthetic radial topology when OSM data is absent.' },
  { term: 'OPC-UA', full: 'OPC Unified Architecture', def: 'A machine-to-machine communication protocol used in industrial SCADA. Supported via L&T Edge Agent.' },
  { term: 'p.u.', full: 'Per Unit (voltage)', def: 'Normalised voltage. 1.0 p.u. = nominal (230 V single-phase). Green = 0.95–1.05 p.u.; Amber = 0.90–0.95; Red < 0.90 (thermal/voltage violation).' },
  { term: 'PUVVNL', full: 'Poorvanchal Vidyut Vitran Nigam Limited', def: 'Uttar Pradesh DNO covering the Varanasi division. One of the two live deployments on Neural Grid. Uses UPERC-DR-2025 regulatory framework.' },
  { term: 'RIIO-ED2', full: 'Revenue = Incentives + Innovation + Outputs (ED2)', def: 'Ofgem regulatory framework covering SSEN network investment 2023–2028. Neural Grid compliance features target RIIO-ED2 flexibility cost reporting.' },
  { term: 'SCADA', full: 'Supervisory Control and Data Acquisition', def: 'The primary control system of a DNO. Neural Grid pushes LV DERMS data back to SCADA via the SCADA Gateway module, using REST, MODBUS, DNP3, OPC-UA, or MQTT.' },
  { term: 'SSEN', full: 'Scottish and Southern Electricity Networks', def: 'UK DNO for Scotland and southern England. One of the two live deployments on Neural Grid. Uses ENA-CPP-2024 / RIIO-ED2 and SSEN IEC MarketDocument OE format.' },
  { term: 'VTN', full: 'Virtual Top Node', def: 'The server-side role in IEEE 2030.5 / OpenADR. Neural Grid acts as VTN, issuing DOE and control signals to DER aggregators (VENs).' },
]

const API_ENDPOINTS = [
  // Auth
  { method: 'POST', path: '/api/v1/auth/login', desc: 'Login — returns JWT bearer token' },
  { method: 'GET',  path: '/api/v1/auth/me', desc: 'Current user profile' },
  { method: 'GET',  path: '/api/v1/auth/deployments', desc: 'List accessible deployments' },
  // Grid
  { method: 'GET',  path: '/api/v1/grid/dashboard', desc: 'Dashboard KPIs — grid state + active alerts' },
  { method: 'GET',  path: '/api/v1/grid/state', desc: 'Real-time grid telemetry snapshot' },
  { method: 'GET',  path: '/api/v1/grid/alerts', desc: 'Active alerts list' },
  { method: 'POST', path: '/api/v1/grid/alerts/{id}/acknowledge', desc: 'Acknowledge an alert' },
  { method: 'GET',  path: '/api/v1/grid/topology', desc: 'Grid topology — nodes and edges' },
  { method: 'GET',  path: '/api/v1/grid/hosting-capacity', desc: 'DER hosting capacity by CMZ' },
  { method: 'POST', path: '/api/v1/grid/power-flow', desc: 'Run DistFlow power flow for deployment' },
  // Assets
  { method: 'GET',  path: '/api/v1/assets', desc: 'List DER assets (filterable by type, status, cmz)' },
  { method: 'POST', path: '/api/v1/assets', desc: 'Register a new DER asset' },
  { method: 'GET',  path: '/api/v1/assets/{id}', desc: 'Asset detail' },
  { method: 'PUT',  path: '/api/v1/assets/{id}', desc: 'Update asset metadata or configuration' },
  { method: 'GET',  path: '/api/v1/assets/{id}/telemetry', desc: 'Historical telemetry (hours param)' },
  // Dispatch
  { method: 'GET',  path: '/api/v1/events', desc: 'List flex dispatch events' },
  { method: 'POST', path: '/api/v1/events', desc: 'Create a flex dispatch event' },
  { method: 'GET',  path: '/api/v1/events/{id}', desc: 'Event detail + OE messages' },
  { method: 'POST', path: '/api/v1/events/{id}/dispatch', desc: 'Trigger dispatch of event to DERs' },
  { method: 'POST', path: '/api/v1/events/{id}/cancel', desc: 'Cancel an in-progress event' },
  { method: 'GET',  path: '/api/v1/events/{id}/oe-messages/formatted', desc: 'OE message in protocol format (?protocol=SSEN_IEC | IEEE_2030_5 | OPENADR_2B | IEC_62746_4 | RAW)' },
  // Forecasting
  { method: 'GET',  path: '/api/v1/forecasting/all', desc: 'Solar + load + flex forecasts (48 h)' },
  { method: 'GET',  path: '/api/v1/forecasting/solar', desc: 'Latest 48-hour solar forecast' },
  { method: 'GET',  path: '/api/v1/forecasting/load', desc: 'Latest 48-hour demand forecast' },
  { method: 'GET',  path: '/api/v1/forecasting/flex', desc: 'Latest 48-hour flex availability forecast' },
  { method: 'POST', path: '/api/v1/forecasting/refresh', desc: 'Regenerate all forecasts for deployment' },
  { method: 'GET',  path: '/api/v1/forecasting/lv-feeder/{id}', desc: 'LV feeder load/solar/EV forecast (?horizon_hours)' },
  { method: 'GET',  path: '/api/v1/forecasting/asset/{id}', desc: 'Asset-level generation/consumption forecast' },
  { method: 'GET',  path: '/api/v1/forecasting/oe-headroom/{cmz_id}', desc: 'OE headroom forecast for CMZ (?horizon_hours)' },
  // LV Network
  { method: 'GET',  path: '/api/v1/lv-network/', desc: 'List all LV feeder networks for deployment' },
  { method: 'GET',  path: '/api/v1/lv-network/providers', desc: 'List available GIS providers (overpass / overpass_fr / synthetic)' },
  { method: 'GET',  path: '/api/v1/lv-network/dt/{dt_id}', desc: 'Get or build LV network for a DT (?provider=overpass)' },
  { method: 'POST', path: '/api/v1/lv-network/dt/{dt_id}/power-flow', desc: 'Run DistFlow power flow for DT LV network' },
  // Programs / Contracts
  { method: 'GET',  path: '/api/v1/programs', desc: 'List flex programs' },
  { method: 'POST', path: '/api/v1/programs', desc: 'Create a flex program' },
  { method: 'GET',  path: '/api/v1/contracts', desc: 'List flex contracts' },
  { method: 'POST', path: '/api/v1/contracts', desc: 'Create a flex contract' },
  { method: 'POST', path: '/api/v1/contracts/{id}/activate', desc: 'Activate a contract' },
  // Optimization
  { method: 'POST', path: '/api/v1/optimization/dr-dispatch', desc: 'Optimal DR dispatch (linear programme)' },
  { method: 'GET',  path: '/api/v1/optimization/recommendations', desc: 'Heuristic flex action recommendations' },
  { method: 'POST', path: '/api/v1/optimization/recalculate-does', desc: 'Recalculate DOEs for all CMZs' },
  { method: 'POST', path: '/api/v1/optimization/p2p-market', desc: 'Run P2P energy market clearing' },
  // Settlement
  { method: 'GET',  path: '/api/v1/settlement', desc: 'List settlement records' },
  { method: 'POST', path: '/api/v1/settlement/calculate', desc: 'Calculate settlement for a contract+event pair' },
  { method: 'POST', path: '/api/v1/settlement/{id}/approve', desc: 'Approve a settlement record' },
  // Integrations
  { method: 'GET',  path: '/api/v1/integrations', desc: 'List external system integrations (GE ADMS, SCADA, MDM…)' },
  { method: 'POST', path: '/api/v1/integrations', desc: 'Register a new integration' },
  { method: 'PUT',  path: '/api/v1/integrations/{id}', desc: 'Update integration config' },
  { method: 'POST', path: '/api/v1/integrations/{id}/toggle-mode', desc: 'Toggle SIMULATION ↔ LIVE mode' },
  { method: 'POST', path: '/api/v1/integrations/{id}/test', desc: 'Test integration connectivity' },
  // SCADA Gateway
  { method: 'GET',  path: '/api/v1/scada/endpoints', desc: 'List SCADA push endpoints' },
  { method: 'POST', path: '/api/v1/scada/endpoints', desc: 'Create SCADA push endpoint' },
  { method: 'POST', path: '/api/v1/scada/endpoints/{id}/push', desc: 'Manually trigger push to endpoint' },
  { method: 'GET',  path: '/api/v1/scada/snapshot', desc: 'Full LV DERMS snapshot (JWT or X-DaaS-Key)' },
  { method: 'GET',  path: '/api/v1/scada/snapshot/grid', desc: 'Grid nodes + feeders snapshot' },
  { method: 'GET',  path: '/api/v1/scada/snapshot/lv-network', desc: 'LV bus voltages + feeder topology' },
  { method: 'GET',  path: '/api/v1/scada/snapshot/assets', desc: 'DER asset outputs snapshot' },
  { method: 'GET',  path: '/api/v1/scada/snapshot/oe-limits', desc: 'Current OE limits per asset' },
  { method: 'GET',  path: '/api/v1/scada/daas/keys', desc: 'List DaaS API keys' },
  { method: 'POST', path: '/api/v1/scada/daas/keys', desc: 'Issue new DaaS API key (plain key returned once)' },
  { method: 'DELETE', path: '/api/v1/scada/daas/keys/{id}', desc: 'Revoke DaaS API key' },
  { method: 'GET',  path: '/api/v1/scada/daas/keys/{id}/usage', desc: 'DaaS key usage stats (7-day)' },
  // Aggregator
  { method: 'GET',  path: '/api/v1/aggregator/devices', desc: 'List registered DER aggregator devices (IEEE 2030.5)' },
  { method: 'POST', path: '/api/v1/aggregator/register', desc: 'Register a new aggregator / VEN' },
  // Admin
  { method: 'GET',  path: '/api/v1/admin/users', desc: 'List platform users' },
  { method: 'POST', path: '/api/v1/admin/users/invite', desc: 'Invite a new user' },
  { method: 'GET',  path: '/api/v1/admin/audit-logs', desc: 'Audit log trail' },
  { method: 'GET',  path: '/api/v1/admin/system-health', desc: 'Background task and DB health check' },
  { method: 'GET',  path: '/api/v1/admin/config', desc: 'Deployment configuration' },
  { method: 'PUT',  path: '/api/v1/admin/config', desc: 'Update deployment configuration' },
  // Reports
  { method: 'GET',  path: '/api/v1/reports/summary', desc: 'Aggregated performance summary' },
  { method: 'GET',  path: '/api/v1/reports/export', desc: 'Export report (?format=json|csv|pdf)' },
  // WebSocket
  { method: 'WS',   path: '/ws', desc: 'Real-time grid telemetry WebSocket — broadcasts grid state + alerts every 5 s' },
  // Health
  { method: 'GET',  path: '/health', desc: 'Liveness probe — returns {status: ok, version}' },
]

const METHOD_COLORS: Record<string, string> = {
  GET:    'bg-green-900/50 text-green-300 border-green-800',
  POST:   'bg-blue-900/50 text-blue-300 border-blue-800',
  PUT:    'bg-amber-900/50 text-amber-300 border-amber-800',
  DELETE: 'bg-red-900/50 text-red-300 border-red-800',
  WS:     'bg-purple-900/50 text-purple-300 border-purple-800',
}

const SECTIONS = [
  { id: 'overview', label: 'Platform Overview' },
  { id: 'terminology', label: 'Terminology' },
  { id: 'architecture', label: 'Architecture' },
  { id: 'endpoints', label: 'API Endpoints' },
  { id: 'flex-config', label: 'Flexible Configs' },
  { id: 'data-flow', label: 'Data Flow' },
  { id: 'customization', label: 'Admin Customization' },
]

// ─── Components ───────────────────────────────────────────────────────────────

function MethodBadge({ method }: { method: string }) {
  return (
    <span className={clsx('text-xs font-mono font-bold px-1.5 py-0.5 rounded border w-16 text-center flex-shrink-0', METHOD_COLORS[method] ?? 'bg-gray-800 text-gray-300 border-gray-700')}>
      {method}
    </span>
  )
}

function Section({ id, children }: { id: string; children: React.ReactNode }) {
  return (
    <section id={id} className="scroll-mt-6 space-y-4">
      {children}
    </section>
  )
}

function SectionTitle({ children }: { children: React.ReactNode }) {
  return <h2 className="text-xl font-bold text-white border-b border-gray-800 pb-3">{children}</h2>
}

// ─── Page ─────────────────────────────────────────────────────────────────────

export default function GlossaryPage() {
  const [search, setSearch] = useState('')
  const [activeSection, setActiveSection] = useState('overview')

  const filteredTerms = GLOSSARY_TERMS.filter(
    (t) =>
      !search ||
      t.term.toLowerCase().includes(search.toLowerCase()) ||
      t.full.toLowerCase().includes(search.toLowerCase()) ||
      t.def.toLowerCase().includes(search.toLowerCase())
  )

  const filteredEndpoints = API_ENDPOINTS.filter(
    (e) =>
      !search ||
      e.path.toLowerCase().includes(search.toLowerCase()) ||
      e.desc.toLowerCase().includes(search.toLowerCase()) ||
      e.method.toLowerCase().includes(search.toLowerCase())
  )

  const scrollTo = (id: string) => {
    setActiveSection(id)
    document.getElementById(id)?.scrollIntoView({ behavior: 'smooth' })
  }

  return (
    <div className="max-w-7xl mx-auto flex gap-6">
      {/* Left sidebar */}
      <aside className="w-52 flex-shrink-0 sticky top-0 h-fit space-y-1 pt-1">
        <p className="text-xs text-gray-500 uppercase tracking-wider font-semibold px-2 mb-3">
          Contents
        </p>
        {SECTIONS.map(({ id, label }) => (
          <button
            key={id}
            onClick={() => scrollTo(id)}
            className={clsx(
              'flex items-center gap-2 w-full text-left text-sm px-3 py-1.5 rounded-lg transition-colors',
              activeSection === id
                ? 'bg-indigo-900/50 text-indigo-300'
                : 'text-gray-400 hover:text-gray-200 hover:bg-gray-800'
            )}
          >
            <ChevronRight className="w-3.5 h-3.5 flex-shrink-0" />
            {label}
          </button>
        ))}
      </aside>

      {/* Main content */}
      <div className="flex-1 space-y-10 min-w-0">
        {/* Header + search */}
        <div>
          <h1 className="text-2xl font-bold text-white mb-1">Glossary & Documentation</h1>
          <p className="text-sm text-gray-400">
            Complete reference for the Neural Grid L&T DERMS platform — terminology, all API endpoints,
            architecture, data flow, and admin customization options.
          </p>
          <div className="mt-4 relative max-w-lg">
            <Search className="absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4 text-gray-500" />
            <input
              value={search}
              onChange={(e) => setSearch(e.target.value)}
              placeholder="Search terms, endpoints, descriptions…"
              className="w-full bg-gray-900 border border-gray-700 text-white pl-10 pr-4 py-2 rounded-lg text-sm focus:outline-none focus:ring-1 focus:ring-indigo-500"
            />
          </div>
        </div>

        {/* ── Overview ── */}
        <Section id="overview">
          <SectionTitle>Platform Overview</SectionTitle>
          <div className="grid grid-cols-2 gap-4">
            {[
              { title: 'Multi-Deployment', desc: 'Supports multiple DNO deployments (SSEN Scotland, PUVVNL Varanasi) from a single backend. Deployment context is set via the X-Deployment-ID header on every API request.' },
              { title: 'LV Network Modelling', desc: 'Models the 400V/230V network behind distribution transformers using OpenStreetMap topology or synthetic radial networks. Runs DistFlow power flow to compute bus voltages and identify violations.' },
              { title: 'Flex Dispatch', desc: 'Full flexibility dispatch workflow: Program → Contract → Event → Dispatch → Performance → Settlement. Supports IEEE 2030.5, OpenADR 2.0b, IEC 62746-4, and SSEN IEC MarketDocument formats.' },
              { title: 'SCADA Gateway', desc: 'Pushes LV DERMS data to external SCADA/DMS/MDM systems via REST, MODBUS, DNP3, OPC-UA, or MQTT. DaaS API keys allow SCADA operators to pull scoped data without accessing the main platform.' },
              { title: 'Forecasting', desc: '48-hour ahead solar, load, and flex forecasts at deployment level. Asset-level type-dispatched forecasts (PV bell-curve, BESS, EV, heat pump). LV feeder forecasts with 30-minute resolution.' },
              { title: 'GIS Map', desc: 'react-leaflet map with OSM, Esri Satellite, and CartoDB Dark tile layers. Zoom-level progressive detail: CMZ at zoom < 12, DT + LV routes at zoom 12-14, individual homes with DER icons at zoom ≥ 15.' },
            ].map(({ title, desc }) => (
              <div key={title} className="bg-gray-900 rounded-xl border border-gray-800 p-4">
                <h3 className="text-sm font-semibold text-indigo-400 mb-1">{title}</h3>
                <p className="text-xs text-gray-400 leading-relaxed">{desc}</p>
              </div>
            ))}
          </div>
        </Section>

        {/* ── Terminology ── */}
        <Section id="terminology">
          <SectionTitle>Terminology</SectionTitle>
          {filteredTerms.length === 0 ? (
            <p className="text-gray-500 text-sm">No matching terms.</p>
          ) : (
            <div className="space-y-3">
              {filteredTerms.map(({ term, full, def }) => (
                <div key={term} className="bg-gray-900 rounded-xl border border-gray-800 p-4">
                  <div className="flex items-baseline gap-3 mb-1">
                    <span className="font-mono font-bold text-indigo-400 text-sm">{term}</span>
                    <span className="text-gray-400 text-xs">{full}</span>
                  </div>
                  <p className="text-sm text-gray-300 leading-relaxed">{def}</p>
                </div>
              ))}
            </div>
          )}
        </Section>

        {/* ── Architecture ── */}
        <Section id="architecture">
          <SectionTitle>Architecture</SectionTitle>
          <div className="space-y-4">
            <div className="bg-gray-900 rounded-xl border border-gray-800 p-5 space-y-3">
              <h3 className="text-sm font-semibold text-white">Backend Stack</h3>
              <div className="grid grid-cols-2 gap-3 text-xs">
                {[
                  ['Framework', 'FastAPI (Python 3.11) — async, OpenAPI auto-docs at /api/docs'],
                  ['Database', 'SQLite (dev) / PostgreSQL (prod) via SQLAlchemy 2.0 async ORM'],
                  ['Auth', 'JWT bearer tokens — HS256, 8-hour expiry. DaaS keys: SHA-256 hashed, 16-char prefix stored.'],
                  ['Background Tasks', 'asyncio tasks: grid_simulation_loop (5s), dispatch_loop (10s), forecast_loop (15 min), broadcast_loop (5s), scada_push_loop (30s)'],
                  ['Power Flow', 'DistFlow (Baran & Wu) — backward-forward sweep, pure Python, no numpy dependency'],
                  ['GIS', 'OpenStreetMap Overpass API (power=cable voltage~400|230) with synthetic radial fallback'],
                ].map(([k, v]) => (
                  <div key={k} className="bg-gray-800/60 rounded-lg p-3">
                    <div className="text-indigo-400 font-medium mb-1">{k}</div>
                    <div className="text-gray-400 leading-relaxed">{v}</div>
                  </div>
                ))}
              </div>
            </div>

            <div className="bg-gray-900 rounded-xl border border-gray-800 p-5 space-y-3">
              <h3 className="text-sm font-semibold text-white">Frontend Stack</h3>
              <div className="grid grid-cols-2 gap-3 text-xs">
                {[
                  ['Framework', 'React 18 + TypeScript + Vite'],
                  ['State', 'Zustand stores: authStore (JWT + deployment), gridStore (telemetry + alerts + forecasts)'],
                  ['Map', 'react-leaflet v5 with Leaflet.js — OSM / Esri Satellite / CartoDB Dark tile layers'],
                  ['Charts', 'Recharts — BarChart, LineChart, AreaChart, PieChart'],
                  ['Styling', 'Tailwind CSS v3 + clsx'],
                  ['API', 'Axios with auto-auth interceptor (X-Deployment-ID + Bearer) and 401 auto-logout'],
                ].map(([k, v]) => (
                  <div key={k} className="bg-gray-800/60 rounded-lg p-3">
                    <div className="text-indigo-400 font-medium mb-1">{k}</div>
                    <div className="text-gray-400 leading-relaxed">{v}</div>
                  </div>
                ))}
              </div>
            </div>

            <div className="bg-gray-900 rounded-xl border border-gray-800 p-5">
              <h3 className="text-sm font-semibold text-white mb-3">Backend Module Map</h3>
              <div className="font-mono text-xs text-gray-400 space-y-0.5">
                {[
                  ['app/auth/', 'JWT auth, user management, deployment access'],
                  ['app/grid/', 'Grid simulation, topology, hosting capacity, DistFlow power flow'],
                  ['app/assets/', 'DER asset CRUD and telemetry'],
                  ['app/dispatch/', 'Flex events, OE messages, SSEN IEC MarketDocument builders'],
                  ['app/forecasting/', 'Solar/load/flex/LV feeder/asset/OE headroom forecasts'],
                  ['app/lv_network/', 'LV feeder models, OSM client, DistFlow per DT'],
                  ['app/programs/', 'DR program management'],
                  ['app/contracts/', 'Flex contract lifecycle'],
                  ['app/settlement/', 'Performance measurement and settlement calculation'],
                  ['app/optimization/', 'Linear DR dispatch, DOE recalculation, P2P market'],
                  ['app/aggregator/', 'IEEE 2030.5 VTN + OpenADR 2.0b aggregator interface'],
                  ['app/integrations/', 'GE ADMS, SCADA, MDM integration config manager'],
                  ['app/scada_gateway/', 'SCADA push endpoints + DaaS API key management'],
                  ['app/admin/', 'Users, audit logs, system health, deployment config'],
                  ['app/reporting/', 'Aggregated performance reports'],
                  ['app/counterparties/', 'Counterparty (aggregator/customer) registry'],
                ].map(([mod, desc]) => (
                  <div key={mod} className="flex gap-3">
                    <span className="text-indigo-400 w-48 flex-shrink-0">{mod}</span>
                    <span>{desc}</span>
                  </div>
                ))}
              </div>
            </div>
          </div>
        </Section>

        {/* ── API Endpoints ── */}
        <Section id="endpoints">
          <SectionTitle>All API Endpoints</SectionTitle>
          <p className="text-xs text-gray-500">
            All routes require <code className="bg-gray-800 px-1 rounded">Authorization: Bearer &lt;token&gt;</code> and{' '}
            <code className="bg-gray-800 px-1 rounded">X-Deployment-ID: &lt;slug&gt;</code> headers unless noted.
            Interactive docs at <code className="bg-gray-800 px-1 rounded">/api/docs</code>.
          </p>
          {filteredEndpoints.length === 0 ? (
            <p className="text-gray-500 text-sm">No matching endpoints.</p>
          ) : (
            <div className="space-y-1.5">
              {filteredEndpoints.map((ep, i) => (
                <div key={i} className="flex items-start gap-3 bg-gray-900 rounded-lg px-3 py-2.5 border border-gray-800/60">
                  <MethodBadge method={ep.method} />
                  <code className="text-xs text-gray-300 font-mono flex-shrink-0 w-80">{ep.path}</code>
                  <span className="text-xs text-gray-500 leading-relaxed">{ep.desc}</span>
                </div>
              ))}
            </div>
          )}
        </Section>

        {/* ── Flexible Configs ── */}
        <Section id="flex-config">
          <SectionTitle>Flexible Configurations</SectionTitle>
          <div className="space-y-4">
            {[
              {
                title: 'GIS Provider',
                config: 'GET /api/v1/lv-network/dt/{id}?provider=<value>',
                options: ['overpass — OpenStreetMap Overpass API (primary)', 'overpass_fr — Overpass FR mirror (backup)', 'synthetic — offline radial topology generation'],
                note: 'Provider can be changed per DT. The platform falls back automatically to synthetic if Overpass returns no LV cables.',
              },
              {
                title: 'OE Message Protocol',
                config: 'GET /api/v1/events/{id}/oe-messages/formatted?protocol=<value>',
                options: ['SSEN_IEC — IEC MarketDocument (5-document chain, MW, process.processType Z01)', 'IEEE_2030_5 — IEEE Smart Energy Profile DERControl', 'OPENADR_2B — OpenADR 2.0b EiEvent', 'IEC_62746_4 — Generic IEC 62746-4', 'RAW — internal DERMS JSON'],
                note: 'Protocol is set per request. SSEN deployments default to SSEN_IEC. PUVVNL uses IEC_62746_4.',
              },
              {
                title: 'Integration Mode',
                config: 'POST /api/v1/integrations/{id}/toggle-mode',
                options: ['SIMULATION — synthetic responses, no external calls', 'LIVE — real API calls to GE ADMS, SCADA, MDM endpoints'],
                note: 'Mode can be toggled per integration at runtime. New integrations default to SIMULATION.',
              },
              {
                title: 'SCADA Push Protocol',
                config: 'POST /api/v1/scada/endpoints  (body: protocol field)',
                options: ['REST_JSON — direct HTTP POST, no hardware required', 'MQTT — IP-based pub/sub, no hardware required', 'MODBUS_TCP — requires L&T Edge Agent hardware gateway', 'DNP3 — requires L&T Edge Agent hardware gateway', 'OPC-UA — requires L&T Edge Agent hardware gateway'],
                note: 'REST_JSON and MQTT work in any environment. MODBUS/DNP3/OPC-UA require the hardware gateway appliance sold by L&T.',
              },
              {
                title: 'Forecast Horizon',
                config: 'GET /api/v1/forecasting/lv-feeder/{id}?horizon_hours=<1-168>',
                options: ['LV feeder forecast: 1–168 hours (default 48)', 'Asset forecast: 1–168 hours (default 48)', 'OE headroom forecast: 1–72 hours (default 24)'],
                note: 'Longer horizons increase uncertainty bands. The forecast engine uses a sinusoidal base with noise injection; replace with a real ML model by overriding the service functions.',
              },
              {
                title: 'DaaS Key Permissions',
                config: 'POST /api/v1/scada/daas/keys  (body: permission flags)',
                options: ['can_read_lv_voltages — LV bus voltage telemetry', 'can_read_feeder_loading — feeder MW loading', 'can_read_der_outputs — individual DER asset outputs', 'can_read_oe_limits — current OE export/import limits', 'can_read_flex_events — active flex dispatch events'],
                note: 'Each permission maps to a snapshot section. A key with only can_read_lv_voltages will receive only the lv_network section of the snapshot.',
              },
            ].map(({ title, config, options, note }) => (
              <div key={title} className="bg-gray-900 rounded-xl border border-gray-800 p-5">
                <h3 className="text-sm font-semibold text-white mb-2">{title}</h3>
                <code className="text-xs text-indigo-300 font-mono bg-gray-800/60 px-2 py-1 rounded block mb-3">
                  {config}
                </code>
                <ul className="space-y-1 mb-3">
                  {options.map((opt) => {
                    const [key, ...rest] = opt.split(' — ')
                    return (
                      <li key={opt} className="text-xs text-gray-400 flex gap-2">
                        <span className="text-indigo-400 font-mono flex-shrink-0">{key}</span>
                        {rest.length > 0 && <span>— {rest.join(' — ')}</span>}
                      </li>
                    )
                  })}
                </ul>
                <p className="text-xs text-gray-500 italic">{note}</p>
              </div>
            ))}
          </div>
        </Section>

        {/* ── Data Flow ── */}
        <Section id="data-flow">
          <SectionTitle>Data Flow Diagrams</SectionTitle>
          <div className="space-y-4">
            {[
              {
                title: 'Flex Dispatch Flow',
                steps: [
                  ['1', 'Admin creates a Program (capacity, service type, payment rate)'],
                  ['2', 'Aggregator signs a Contract against the Program'],
                  ['3', 'Grid operator creates a Flex Event (MW target, CMZ, window)'],
                  ['4', 'POST /events/{id}/dispatch — platform sends DOE signals via IEEE 2030.5 / OpenADR to all enrolled DERs'],
                  ['5', 'DERs respond; telemetry flows back via WebSocket and grid simulation'],
                  ['6', 'POST /forecasting/oe-headroom — OE headroom forecast updated'],
                  ['7', 'POST /settlement/calculate — settlement calculated against metered performance'],
                  ['8', 'OE message generated in SSEN_IEC format for DNO reporting'],
                ],
              },
              {
                title: 'LV Network Power Flow',
                steps: [
                  ['1', 'DT node selected on GIS map (zoom ≥ 13)'],
                  ['2', 'GET /lv-network/dt/{id} — fetch or build LV topology (OSM → synthetic fallback)'],
                  ['3', 'POST /lv-network/dt/{id}/power-flow — DistFlow backward-forward sweep'],
                  ['4', 'Bus voltages (p.u.) and branch currents returned in LVBus records'],
                  ['5', 'LVNetworkPanel shows voltage profile bar chart — red buses = violations'],
                  ['6', 'GET /forecasting/oe-headroom/{cmz_id} — headroom = rated_kva − net_load + generation'],
                  ['7', 'OE limits derived from headroom and pushed to aggregator via SCADA Gateway'],
                ],
              },
              {
                title: 'SCADA DaaS Pull Flow',
                steps: [
                  ['1', 'Admin creates DaaS API key with scoped permissions (POST /scada/daas/keys)'],
                  ['2', 'Plain key returned once — SCADA operator stores it securely'],
                  ['3', 'SCADA system calls GET /scada/snapshot with X-DaaS-Key header'],
                  ['4', 'Platform verifies key (SHA-256 hash compare), checks rate limit'],
                  ['5', 'Response filtered to permitted sections only'],
                  ['6', 'Usage recorded to daas_usage_records table (billing/monitoring)'],
                  ['7', 'Daily usage stats available at GET /scada/daas/keys/{id}/usage'],
                ],
              },
            ].map(({ title, steps }) => (
              <div key={title} className="bg-gray-900 rounded-xl border border-gray-800 p-5">
                <h3 className="text-sm font-semibold text-white mb-3">{title}</h3>
                <div className="space-y-2">
                  {steps.map(([num, desc]) => (
                    <div key={num} className="flex gap-3 items-start">
                      <span className="w-6 h-6 rounded-full bg-indigo-900/60 border border-indigo-700 text-indigo-300 text-xs flex items-center justify-center flex-shrink-0 font-bold">
                        {num}
                      </span>
                      <span className="text-xs text-gray-400 leading-relaxed pt-0.5">{desc}</span>
                    </div>
                  ))}
                </div>
              </div>
            ))}
          </div>
        </Section>

        {/* ── Admin Customization ── */}
        <Section id="customization">
          <SectionTitle>Admin Customization Reference</SectionTitle>
          <div className="space-y-3">
            {[
              {
                area: 'Deployment Configuration',
                endpoint: 'GET/PUT /api/v1/admin/config',
                fields: ['regulatory_framework (ENA-CPP-2024 | UPERC-DR-2025)', 'default_oe_protocol (SSEN_IEC | IEC_62746_4 | IEEE_2030_5)', 'lv_gis_provider (overpass | synthetic)', 'forecast_horizon_hours (default: 48)', 'scada_push_interval_seconds (default: 60)', 'enable_p2p_market (true | false)', 'enable_daas_billing (true | false)'],
              },
              {
                area: 'Integration Endpoints',
                endpoint: 'POST /api/v1/integrations',
                fields: ['system_type (GE_ADMS | SCADA | DMS | MDM | WEATHER_API | MARKET_API)', 'mode (SIMULATION | LIVE)', 'base_url, api_key, username/password', 'sim_params — JSON object of simulated response overrides', 'polling_interval_seconds'],
              },
              {
                area: 'User Roles',
                endpoint: 'POST /api/v1/admin/users/invite',
                fields: ['PLATFORM_ADMIN — full access all deployments', 'DEPLOY_ADMIN — admin for assigned deployment only', 'OPERATOR — dispatch, forecast, reports (read+write)', 'VIEWER — read-only access'],
              },
              {
                area: 'Asset Registration',
                endpoint: 'POST /api/v1/assets',
                fields: ['asset_type (SOLAR_PV | BESS | EV_V1G | EV_V2G | HEAT_PUMP | INDUSTRIAL_LOAD)', 'rated_kw, rated_kva', 'lat, lng — GPS position for GIS map', 'node_id — links to GridNode (DT or feeder)', 'flex_eligible (true | false)', 'protocol (IEEE_2030_5 | OPENADR | MODBUS | DIRECT_API)'],
              },
              {
                area: 'LV Network GIS Provider',
                endpoint: 'GET /api/v1/lv-network/dt/{id}?provider=<value>&force_rebuild=true',
                fields: ['overpass — query OpenStreetMap for real cable routes', 'overpass_fr — FR mirror (fallback)', 'synthetic — auto-generate radial topology from DT GPS', 'force_rebuild=true — re-fetch and overwrite cached topology'],
              },
              {
                area: 'SCADA Push Data Flags',
                endpoint: 'PUT /api/v1/scada/endpoints/{id}',
                fields: ['push_lv_voltages — LV bus voltage telemetry', 'push_feeder_loading — feeder MW loading', 'push_der_outputs — DER asset outputs', 'push_oe_limits — current OE export/import limits', 'push_flex_events — active flex dispatch events', 'push_interval_seconds — auto-push frequency'],
              },
            ].map(({ area, endpoint, fields }) => (
              <div key={area} className="bg-gray-900 rounded-xl border border-gray-800 p-4">
                <div className="flex items-start justify-between gap-4 mb-2">
                  <h3 className="text-sm font-semibold text-white">{area}</h3>
                  <code className="text-xs text-indigo-300 font-mono bg-gray-800/60 px-2 py-0.5 rounded flex-shrink-0">
                    {endpoint}
                  </code>
                </div>
                <ul className="space-y-1">
                  {fields.map((f) => {
                    const [key, ...rest] = f.split(' — ')
                    return (
                      <li key={f} className="text-xs text-gray-400 flex gap-2">
                        <span className="text-amber-400 font-mono">{key}</span>
                        {rest.length > 0 && <span className="text-gray-500">— {rest.join(' — ')}</span>}
                      </li>
                    )
                  })}
                </ul>
              </div>
            ))}
          </div>
        </Section>
      </div>
    </div>
  )
}
