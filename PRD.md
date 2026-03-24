# Neural Grid — L&T DERMS Platform
## Product Requirements Document (PRD) v1.1
**Date:** March 2026
**Author:** L&T EduTech / Smart Grid Division
**Status:** Active Development
**Changelog v1.1:** Added CIM-based aggregator exchange (IEC 62325 + IEC 62746-4), Kafka transport, OSM bounding-box area query + congested DT identification (System Solaire), and time-series DistFlow dynamic OE calculation.

---

## Table of Contents

1. [Executive Summary](#1-executive-summary)
2. [Problem Statement](#2-problem-statement)
3. [System Architecture Overview](#3-system-architecture-overview)
4. [User Roles & Access Control](#4-user-roles--access-control)
5. [External System Roles](#5-external-system-roles)
6. [Core User Flows](#6-core-user-flows)
7. [LV Network Modelling](#7-lv-network-modelling)
8. [Power Flow Algorithm](#8-power-flow-algorithm)
9. [GIS Integration — OpenStreetMap](#9-gis-integration--openstreetmap)
10. [Forecasting Engine](#10-forecasting-engine)
11. [Optimisation & Scheduling](#11-optimisation--scheduling)
12. [Operating Envelope (OE)](#12-operating-envelope-oe)
13. [Dynamic OE via Time-Series Power Flow *(v1.1)*](#13-dynamic-oe-via-time-series-power-flow)
14. [Flex Dispatch Workflow](#14-flex-dispatch-workflow)
15. [Protocols & Messaging Formats](#15-protocols--messaging-formats)
16. [CIM-Based DER Aggregator Exchange *(v1.1)*](#16-cim-based-der-aggregator-exchange)
17. [SCADA Gateway & DaaS](#17-scada-gateway--daas)
18. [Integration Config Manager](#18-integration-config-manager)
19. [Settlement & Performance Measurement](#19-settlement--performance-measurement)
20. [System Flow Diagrams](#20-system-flow-diagrams)
21. [API Surface Summary](#21-api-surface-summary)
22. [Non-Functional Requirements](#22-non-functional-requirements)
23. [References](#23-references)
21. [References](#21-references)

---

## 1. Executive Summary

**Neural Grid** is a multi-deployment, cloud-native **Distributed Energy Resource Management System (DERMS)** developed by L&T. It manages the full lifecycle of distributed energy resources (DERs) — solar PV, battery storage (BESS), EV chargers, heat pumps, and flexible industrial loads — across low-voltage (LV) and medium-voltage (MV) distribution networks.

The platform is currently deployed for two DNOs (Distribution Network Operators):
- **SSEN South Scotland** — operating under the UK ENA-CPP-2024 / RIIO-ED2 regulatory framework
- **PUVVNL Varanasi** — operating under UPERC-DR-2025 (Uttar Pradesh Electricity Regulatory Commission)

L&T's differentiated value proposition is **LV network visibility** — modelling the 400V/230V "last mile" behind distribution transformers (DTs) that is invisible to traditional ADMS/SCADA systems — and selling that data back to operators as a **Data-as-a-Service (DaaS)** product.

---

## 2. Problem Statement

### What existing systems cannot do

| System | Limitation |
|---|---|
| GE ADMS / SCADA | Operates at 11 kV and above. No visibility below the DT into the 400V LV network. |
| MDM (Meter Data Management) | Has interval meter reads but no real-time grid state or power flow capability. |
| DER Aggregator | Manages asset dispatch but has no network awareness — cannot enforce grid-safe OE limits. |
| DNO planning tools | Static hosting capacity studies. Cannot reflect real-time DER state or dynamic OE. |

### The gap Neural Grid fills

```
HV (132kV/33kV)         MV (11kV)             LV (400V/230V)
┌──────────────┐       ┌────────────┐         ┌────────────────────┐
│ Transmission │──────▶│ Primary    │─────────▶│ Distribution       │
│ Grid         │       │ Substation │         │ Transformer (DT)   │
└──────────────┘       └────────────┘         └──────┬─────────────┘
        ↑                     ↑                       │  ← INVISIBLE TO ADMS/SCADA
   National Grid           GE ADMS /             ┌───▼───────────────────┐
   / State SLDC            SCADA                  │  LV Feeder Network    │
                           (sees this)            │  Homes, Solar, EVs,   │
                                                  │  BESS, Heat Pumps     │
                                                  └───────────────────────┘
                                                          ↑
                                                   Neural Grid fills this
```

---

## 3. System Architecture Overview

```
┌─────────────────────────────────────────────────────────────────────────┐
│                        NEURAL GRID PLATFORM                              │
│                                                                           │
│  ┌──────────────┐  ┌──────────────┐  ┌──────────────┐  ┌─────────────┐ │
│  │  Grid &      │  │  Flex        │  │  Forecasting │  │ Optimisation│ │
│  │  LV Network  │  │  Dispatch    │  │  Engine      │  │  Engine     │ │
│  └──────┬───────┘  └──────┬───────┘  └──────┬───────┘  └──────┬──────┘ │
│         │                 │                  │                  │        │
│  ┌──────▼─────────────────▼──────────────────▼──────────────────▼──────┐│
│  │                    FastAPI Backend (Python 3.11)                      ││
│  │              SQLAlchemy 2.0 async ORM  |  SQLite / PostgreSQL        ││
│  └──────────────────────────────────────────────────────────────────────┘│
│         │                 │                  │                            │
│  ┌──────▼───────┐  ┌──────▼───────┐  ┌──────▼───────────────────┐      │
│  │  Integration │  │  SCADA       │  │  Aggregator VTN           │      │
│  │  Config Mgr  │  │  Gateway     │  │  (IEEE 2030.5 / OpenADR)  │      │
│  └──────┬───────┘  └──────┬───────┘  └──────┬────────────────────┘      │
└─────────┼─────────────────┼─────────────────┼──────────────────────────-┘
          │                 │                  │
    ┌─────▼──────┐   ┌──────▼──────┐   ┌──────▼──────────┐
    │  GE ADMS   │   │  SCADA /    │   │  DER Aggregator │
    │  DMS / MDM │   │  OPC-UA /   │   │  (VEN clients)  │
    │  Weather   │   │  DNP3 /     │   │                 │
    │  APIs      │   │  MODBUS     │   │                 │
    └────────────┘   └─────────────┘   └─────────────────┘
```

### Technology Stack

**Backend**
- Runtime: Python 3.11, FastAPI, Uvicorn (ASGI)
- ORM: SQLAlchemy 2.0 async + Alembic migrations
- Database: SQLite (development), PostgreSQL (production)
- Auth: JWT HS256, 8-hour expiry; DaaS keys: SHA-256 hashed
- Background: asyncio tasks (simulation, dispatch, forecast, broadcast, SCADA push)
- Power flow: Pure-Python DistFlow (Baran & Wu) — no numpy dependency
- HTTP client: httpx (async) for external integrations

**Frontend**
- React 18 + TypeScript + Vite
- State: Zustand (auth + grid stores)
- Map: react-leaflet v5 + Leaflet.js (OSM / Esri Satellite / CartoDB Dark)
- Charts: Recharts
- Styling: Tailwind CSS v3
- API: Axios with auto-auth interceptor

**Real-time**
- WebSocket at `/ws` — broadcasts grid telemetry every 5 seconds
- Client sends `ping` / receives `pong` for keep-alive

---

## 4. User Roles & Access Control

| Role | Scope | Capabilities |
|---|---|---|
| `PLATFORM_ADMIN` | All deployments | Full access — user management, all deployments, all config |
| `DEPLOY_ADMIN` | Assigned deployment | Admin within their deployment — config, integrations, DaaS keys, SCADA endpoints |
| `OPERATOR` | Assigned deployment | Read + write — dispatch events, programs, contracts, forecasts, settlement |
| `VIEWER` | Assigned deployment | Read-only — dashboards, grid state, reports |

**Authentication flow:**
```
POST /api/v1/auth/login  →  { access_token, token_type: "bearer" }
                                        ↓
          All subsequent requests: Authorization: Bearer <token>
                                   X-Deployment-ID: <ssen|puvvnl>
```

Token contains: `email`, `role`, `deployment_ids[]`, `exp`

---

## 5. External System Roles

### 5.1 GE ADMS (Advanced Distribution Management System)

**Role:** Primary grid state source for MV (11 kV and above) network.

**What it provides to Neural Grid:**
- Real-time grid topology (nodes, feeders, substations)
- Feeder loading (MW, MVAr, voltage magnitude)
- Fault detection and restoration events
- Hosting capacity data (where DERs can connect without violation)

**What Neural Grid provides back:**
- LV-level DER aggregates per feeder (total solar export, BESS state, EV load)
- Power flow results from the LV network (voltage violations, branch losses)
- Flex dispatch status (assets curtailed / dispatched)
- Operating Envelope headroom per CMZ

**Integration:** REST/JSON via Integration Config Manager. Mode: SIMULATION (synthetic) or LIVE (real GE ADMS REST API). In the absence of GE ADMS, Neural Grid runs its own grid simulation loop and DistFlow power flow independently.

**Reference:** GE Grid Solutions ADMS — https://www.ge.com/digital/applications/adms

---

### 5.2 SCADA (Supervisory Control and Data Acquisition)

**Role:** Operator console for real-time monitoring and control of the distribution network. SCADA systems see MV; Neural Grid extends visibility to LV.

**What L&T sells to SCADA operators (DaaS):**
- LV bus voltage telemetry (p.u. + volts per bus)
- Feeder loading (MW, loading %)
- Individual DER asset outputs (kW, SOC for BESS, EV charge state)
- Current Operating Envelope limits (MW import/export per CMZ)
- Active flex dispatch events

**Protocols supported for SCADA push:**

| Protocol | Use Case | Hardware Required |
|---|---|---|
| REST/JSON | IP-connected modern SCADA, DMS, ADMS | None |
| MQTT | IoT-style pub/sub SCADA | None |
| MODBUS TCP | Legacy industrial SCADA, RTUs | L&T Edge Agent |
| DNP3 | Utility-standard SCADA protocol | L&T Edge Agent |
| OPC-UA | Industrial automation, ABB/Siemens SCADA | L&T Edge Agent |

**Reference:** DNP3 — IEEE 1815-2012; OPC-UA — IEC 62541; MODBUS — modbus.org

---

### 5.3 DMS (Distribution Management System)

**Role:** Sits between ADMS and SCADA; handles network switching, outage management, and restoration. Neural Grid feeds DMS with LV network topology and DER state.

**Integration:** REST/JSON push via SCADA Gateway. Typically the same endpoint as SCADA but different data subscription (topology focus rather than real-time telemetry).

---

### 5.4 DER Aggregators

**Role:** Companies that aggregate consumer-owned DERs (rooftop solar, home batteries, EV chargers) and offer their flex capacity to the DNO or energy market.

**How aggregators connect to Neural Grid:**

Neural Grid acts as the **VTN (Virtual Top Node)** — the server — and aggregator DER devices act as **VENs (Virtual End Nodes)** — the clients.

```
Neural Grid VTN                     Aggregator VEN
     │                                    │
     │  ◄── Registration (device info) ── │
     │  ──► DOE Limit (MW export/import)─▶│
     │  ──► DERControl (dispatch signal) ─▶│
     │  ◄── DERStatus (device response) ──│
     │  ◄── MirrorUsagePoint (metering) ──│
```

**Protocols:**
- **IEEE 2030.5** (Smart Energy Profile 2.0) — RESTful, TLS, used for DOE and DER control
- **OpenADR 2.0b** — SOAP/REST EiEvent/EiReport, used for demand response programs

**Reference:**
- IEEE 2030.5: https://standards.ieee.org/ieee/2030.5/5897/
- OpenADR: https://www.openadr.org/specification

---

### 5.5 MDM (Meter Data Management)

**Role:** Stores interval meter reads (typically 30-minute AMI/smart meter data) per connection point. MDM is the ground truth for settlement.

**What Neural Grid uses from MDM:**
- Historical load profiles per customer (for forecasting baseline)
- Actual delivered energy per DER asset per dispatch event (for settlement calculation)
- Customer connection point metadata (CPN, tariff, capacity limit)

**Integration:** REST/JSON polling via Integration Config Manager. Neural Grid imports MDM data to validate the performance measurement against its own simulated telemetry.

**Reference:** IEC 61968-9 (Meter Reading and Control); CIM (Common Information Model) — IEC 61970/61968

---

### 5.6 L&T DERMS Role in the Value Chain

```
Consumer Assets              L&T Neural Grid               Grid Operators
────────────────             ───────────────               ──────────────
Rooftop Solar    ──────────▶ Asset Registry                DNO / SSEN
Home BESS        ──────────▶ LV Network Model ──DaaS────▶ SCADA / DMS
EV Charger       ──────────▶ Power Flow (DistFlow)        GE ADMS
Heat Pump        ──────────▶ Forecasting Engine
Industrial Load  ──────────▶ Flex Dispatch     ──OE Msg──▶ Flex Markets
                             OE Calculator     ──IEEE2030.5▶ Aggregators
                             Settlement Engine ──Reports──▶ MDM / Billing
```

---

## 6. Core User Flows

### 6.1 Operator: Monitor Grid and Dispatch Flex

```
Login → Dashboard
  │
  ├─▶ Grid & Assets (map)
  │      │  Zoom < 12: CMZ boundaries + KPIs
  │      │  Zoom 12-14: DT nodes + LV feeder routes (OSM)
  │      │  Zoom ≥ 15: Individual homes + DER icons + flex rings
  │      │
  │      └─▶ Click DT → LV Network Panel (right side)
  │               Run Power Flow → voltage bar chart
  │               OE headroom → SSEN IEC message preview
  │
  ├─▶ Flex Dispatch
  │      Create Event → set CMZ, MW target, window
  │      Dispatch → signals sent via IEEE 2030.5 / OpenADR
  │      Monitor → real-time DER response via WebSocket
  │      OE Message → select protocol (SSEN_IEC / IEEE_2030_5 / etc.)
  │
  ├─▶ Forecasting
  │      48h Solar / Load / Flex charts
  │      LV Feeder forecast (30-min, load+solar+EV)
  │      OE Headroom forecast per CMZ
  │
  └─▶ Settlement
         Calculate → MDM actuals vs. dispatch target
         Approve → triggers payment instruction
```

### 6.2 Admin: Configure SCADA DaaS

```
SCADA Gateway → DaaS API Keys
  │
  ├─▶ Issue Key
  │      Name + client organisation
  │      Select permissions (LV voltages / feeder loading / DER outputs / OE limits / flex events)
  │      Rate limit (req/hour)
  │      → Key generated: lt_daas_<32hex> (shown once)
  │
  └─▶ SCADA operator stores key → calls GET /api/v1/scada/snapshot
         X-DaaS-Key: lt_daas_...
         X-Deployment-ID: ssen
         → receives filtered JSON snapshot
         → usage recorded for billing
```

---

## 7. LV Network Modelling

### 7.1 Why LV Networks are Hard to Model

The 400V/230V low-voltage network presents unique challenges:
- **Not in ADMS**: Utility ADMS typically stops at the 11 kV primary substation. The DT-to-home network is managed by paper records or basic GIS systems.
- **Rarely in OSM**: UK LV underground cables are sparsely mapped in OpenStreetMap. OSM covers overhead lines better.
- **Dynamic DER impact**: Solar PV reverse power flow, EV charging spikes, and BESS cycling cause voltage problems on LV that MV monitoring cannot detect.
- **Scale**: A single 11 kV feeder may serve 20–50 DTs, each with 50–200 customer connections = thousands of buses per deployment.

### 7.2 Network Topology Sources (Priority Order)

```
1. OpenStreetMap Overpass API (primary)
        ↓ if no LV cable data found
2. Overpass FR mirror (backup)
        ↓ if still no data
3. Synthetic radial topology (offline fallback)
```

### 7.3 OSM / Overpass Query

Neural Grid queries the Overpass API for LV cable data within a configurable radius of each DT's GPS coordinates:

```
[out:json][timeout:30];
(
  way["power"="cable"]["voltage"~"400|230"](around:{radius},{lat},{lng});
  way["power"="line"]["voltage"~"400|230"](around:{radius},{lat},{lng});
);
out geom;
```

**Endpoint:** `https://overpass-api.de/api/interpreter` (primary)
**Mirror:** `https://overpass.kumi.systems/api/interpreter` (backup)
**Reference:** OpenStreetMap Overpass API — https://wiki.openstreetmap.org/wiki/Overpass_API

Each way becomes a branch in the LV network graph. Nodes are created at intersections and customer connection points.

### 7.4 Synthetic Radial Topology Generation

When OSM data is unavailable, Neural Grid generates a synthetic radial topology from the DT's GPS coordinates using bearing-based haversine offsets:

```python
# Pure Python — no numpy
# DT is root node at (lat, lng)
# Generate N feeder arms at evenly spaced bearings
# Each arm has M customer buses at increasing distances
# Typical: 3 arms × 8 customers = 24 buses per DT

bearing = (arm_index / feeder_count) * 360  # degrees
new_lat = lat + (distance_m / 111320) * cos(bearing_rad)
new_lng = lng + (distance_m / (111320 * cos(lat_rad))) * sin(bearing_rad)
```

**Assumptions for synthetic network:**
- Topology: 3-phase 4-wire radial (standard UK LV)
- Feeder length: 150–400m per arm (UK standard LV service length)
- Cable type: 16 mm² or 95 mm² XLPE underground (r = 1.15 Ω/km or 0.32 Ω/km)
- Nominal voltage: 0.4 kV (line-to-line), 0.23 kV (line-to-neutral)
- Base: 100 kVA, Vbase = 0.4 kV

### 7.5 LV Network Data Model

```
LVFeeder (lv_feeders table)
  ├── dt_node_id         → links to GridNode (the DT)
  ├── route_geojson      → LineString GeoJSON for map rendering
  ├── rated_kva          → transformer rating (100/200/500 kVA)
  ├── pf_result_json     → last DistFlow result (bus voltages, losses)
  └── source             → osm | synthetic

LVBus (lv_buses table)
  ├── feeder_id          → parent LVFeeder
  ├── bus_id             → unique within feeder
  ├── lat, lng           → GPS for map marker
  ├── v_pu               → voltage (per unit, 1.0 = nominal)
  ├── v_v                → voltage (volts)
  ├── voltage_status     → normal | warning | violation
  ├── p_kw               → net load (positive = consuming)
  └── asset_id           → linked DER asset if any
```

---

## 8. Power Flow Algorithm

### 8.1 DistFlow (Baran & Wu, 1989)

Neural Grid implements the **DistFlow backward-forward sweep** algorithm for radial LV networks.

**Reference:** M.E. Baran and F.F. Wu, "Network reconfiguration in distribution systems for loss reduction and load balancing," IEEE Trans. Power Delivery, vol. 4, no. 2, pp. 1401–1407, Apr. 1989.

**Why DistFlow over Newton-Raphson or Gauss-Seidel?**
- Optimised for radial (tree) topology — O(n) complexity vs. O(n²) for mesh methods
- Numerically stable for high R/X ratio cables (LV cables have R >> X, which breaks Newton-Raphson convergence)
- Pure Python implementation — no numpy or LAPACK dependency needed

### 8.2 Algorithm

**Initialisation:**
```
For each bus i:
  V_i = 1.0 p.u.  (flat start)
  P_i = scheduled load (kW) − DER generation (kW)
  Q_i = scheduled reactive load (kVAr)
```

**Backward Sweep (leaf → root):**
```
For each branch (i→j) from leaf to root:
  P_ij = P_j + r_ij * (P_ij² + Q_ij²) / V_j²   (branch active power)
  Q_ij = Q_j + x_ij * (P_ij² + Q_ij²) / V_j²   (branch reactive power)
```

**Forward Sweep (root → leaf):**
```
For each branch (i→j) from root to leaf:
  V_j² = V_i² - 2*(r_ij*P_ij + x_ij*Q_ij) + (r_ij² + x_ij²)*(P_ij²+Q_ij²)/V_i²
```

**Convergence:** Iterate until max |ΔV| < ε (typically ε = 1e-6 p.u.), usually 3–10 iterations.

### 8.3 Outputs

| Parameter | Unit | Interpretation |
|---|---|---|
| Bus voltage V_i | p.u. | 1.0 = 230V nominal; < 0.95 = low voltage violation (UK ESQCR limit) |
| Branch current I_ij | A | Compare against cable ampacity rating |
| Active losses P_loss | kW | Sum of I²R losses across all branches |
| Total load P_total | kW | Sum of all bus loads |
| Total generation Q_total | kW | Sum of all DER outputs |

### 8.4 UK Voltage Limits (ESQCR 2002)

```
Normal:    0.95 – 1.05 p.u.  (217.5V – 241.5V)  → Green
Warning:   0.90 – 0.95 p.u.  (207.0V – 217.5V)  → Amber
Violation: < 0.90 p.u.        (< 207.0V)         → Red  (statutory limit breach)
```

---

## 9. GIS Integration — OpenStreetMap

### 9.1 Map Architecture

```
react-leaflet v5 (frontend)
  │
  ├── Tile Layer Options:
  │     ├── OpenStreetMap (default) — https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png
  │     ├── Esri World Imagery — satellite imagery
  │     └── CartoDB Dark Matter — dark theme for ops dashboards
  │
  ├── Vector Layers:
  │     ├── CMZ boundaries (GeoJSON polygons)
  │     ├── LV feeder routes (GeoJSON LineStrings from OSM or synthetic)
  │     ├── Asset markers (CircleMarker — colour by type/status)
  │     ├── DT nodes (DivIcon transformer symbol)
  │     └── Flex interconnections (dashed polylines at zoom ≥ 13)
  │
  └── Zoom-level progressive detail:
        zoom < 12:  CMZ polygons + KPI overlays
        zoom 12-14: DT nodes + LV feeder route lines
        zoom ≥ 15:  Individual LVBus nodes (homes/premises)
                    DER type icons (solar/battery/EV/HP)
                    Flex enrolment rings (dashed circle = enrolled)
                    Voltage status colouring (green/amber/red)
```

### 9.2 GIS Data Flow

```
Backend: LVFeeder.route_geojson (stored in DB)
  ↓ GET /api/v1/lv-network/dt/{id}
Frontend: Deserialise GeoJSON → Polyline layer on map
  ↓ Zoom ≥ 13: show feeder routes
  ↓ Zoom ≥ 15: show LVBus markers from /api/v1/lv-network/dt/{id} buses[]
```

### 9.3 Overpass API Rate Limits and Caching

- Overpass public: ~10,000 requests/day, 2 concurrent
- Neural Grid caches LV topology in the `lv_feeders` table. Re-fetch only on `force_rebuild=true`
- For production: consider self-hosted Overpass instance or MapTiler API

### 9.4 Bounding-Box Area Query *(v1.1)*

In addition to per-DT radial queries, the platform now supports area-level OSM queries using a geographic bounding box. This is used to load the complete LV network for a pilot zone in one request.

**Overpass QL — bbox format:**
```
[out:json][timeout:30][bbox:{south},{west},{north},{east}];
(
  way["power"="cable"]["voltage"~"400|230|11000"];
  way["power"="line"]["voltage"~"400|230|11000"];
  way["power"="minor_line"];
  node["power"="transformer"];
  node["power"="substation"];
  node["power"~"meter|connection"];
);
out geom;
```

**API:** `GET /api/v1/lv-network/area?south=&west=&north=&east=&provider=overpass`

Returns a GeoJSON FeatureCollection covering the full LV network (cables, transformers, substations, connection points) in the selected area. The frontend GIS map renders this with a draw-rectangle interaction: user selects an area, backend queries OSM, all features appear as an overlay layer.

### 9.5 Congested DT Identification — System Solaire *(v1.1)*

**System Solaire** is L&T's first solar-heavy pilot deployment. The primary grid constraint is **reverse power flow overvoltage**: midday solar generation pushes LV bus voltages above 1.05 p.u. (UK ESQCR statutory limit), but this is invisible to MV ADMS/SCADA.

Neural Grid identifies congested DTs by ranking all distribution transformers with power flow results by a composite congestion score:

```
congestion_score = max_branch_loading_pct
                 + (count of buses with v_pu < 0.95) × 20    ← undervoltage
                 + (count of buses with v_pu > 1.05) × 20    ← solar overvoltage ← primary

congestion_type:
  VOLTAGE_HIGH  → solar reverse flow (System Solaire primary)
  VOLTAGE_LOW   → heavy load / cable undersized
  THERMAL       → branch current > ampacity limit
  MIXED         → combination of above
  NONE          → no violations
```

**API:** `GET /api/v1/lv-network/congested-dts?threshold_pct=75&limit=20`

The GIS map `CongestedDTOverlay` component shows congested DTs colour-coded:
- Red = VOLTAGE_HIGH or THERMAL critical
- Amber = VOLTAGE_LOW or THERMAL moderate
- Green = no congestion

Clicking a congested DT auto-loads its LV network and triggers power flow, feeding the dynamic OE pipeline (§13).

---

## 10. Forecasting Engine

### 10.1 Forecast Types

| Forecast | Horizon | Resolution | Algorithm |
|---|---|---|---|
| Solar generation | 48 h | 30 min | Bell-curve PV model + cloud noise |
| Demand (load) | 48 h | 30 min | Diurnal profile + day-type weekday/weekend |
| Flex availability | 48 h | 30 min | Asset availability probability |
| LV feeder (load + solar + EV) | 1–168 h | 30 min | Composite per-feeder model |
| Asset-level | 1–168 h | 30 min | Type-dispatched per asset class |
| OE headroom | 1–72 h | 30 min | Rated capacity − forecast load + generation |

### 10.2 Solar PV Bell-Curve Model

```python
# For each 30-min interval t:
hour = t.hour + t.minute / 60
if 6 <= hour <= 20:
    angle = pi * (hour - 6) / 14        # sunrise to sunset
    base = sin(angle)                    # bell-curve 0→1→0
    cloud_factor = 1 + noise * random.gauss(0, 0.15)
    solar_kw = rated_kw * base * cloud_factor * 0.85  # 85% inverter efficiency
```

### 10.3 Asset-Level Type-Dispatched Forecasts

| Asset Type | Model |
|---|---|
| `SOLAR_PV` | Bell-curve (peak at solar noon ±1.5h) with weather noise |
| `BESS` | Flat zero (dispatchable — not forecastable as generation) |
| `EV_V1G` | Evening arrival probability (peak 18:00–22:00) |
| `EV_V2G` | Evening arrival + morning export (06:00–08:00 export peak) |
| `HEAT_PUMP` | Temperature-inverse profile (higher demand in cold mornings) |
| `INDUSTRIAL_LOAD` | Weekday 08:00–18:00 constant load; weekends 30% baseline |

### 10.4 OE Headroom Forecast

```
headroom_kw(t) = rated_kva × power_factor
                 − forecast_load_kw(t)
                 + forecast_generation_kw(t)

If headroom > 0: export headroom available → set export OE limit
If headroom < 0: import headroom needed → set import OE limit
```

### 10.5 Production Upgrade Path

The current engine uses deterministic models with noise injection. Production upgrade would replace with:
- **LSTM / Transformer** time-series models trained on MDM historical data
- **NWP (Numerical Weather Prediction)** integration — Met Office DataPoint API or Open-Meteo API (open-source)
- **Probabilistic forecasting** — quantile regression for P10/P50/P90 confidence intervals

**References:**
- Open-Meteo (free NWP API): https://open-meteo.com
- ENTSO-E Transparency Platform (historical generation data): https://transparency.entsoe.eu
- UK Met Office DataPoint: https://www.metoffice.gov.uk/services/data/datapoint

---

## 11. Optimisation & Scheduling

### 11.1 DR Dispatch Optimisation (Linear Programme)

Neural Grid formulates the demand response dispatch as a linear programme:

```
Minimise:   Σ c_i × (P_i_max − P_i_dispatched)    (minimise curtailment cost)

Subject to:
  Σ P_i_dispatched ≥ P_target                      (meet MW target)
  0 ≤ P_i_dispatched ≤ P_i_max      ∀ asset i      (asset limits)
  P_i_dispatched ≤ OE_export_limit   ∀ asset i      (OE constraints)
  V_bus_j ≥ 0.95 p.u.               ∀ bus j        (voltage limits)
```

Where:
- `P_target` = dispatch event MW target
- `c_i` = asset cost (from contract)
- `P_i_max` = asset rated capacity

**Solver:** Greedy heuristic (current). Production: GLPK (open-source LP) or Gurobi.

**Reference:** D.P. Bertsekas, "Linear Network Optimization," MIT Press, 1991.

### 11.2 Dynamic Operating Envelope (DOE) Calculation

```
DOE_export_i(t) = min(
    asset_rated_kw_i,
    OE_headroom_cmz(t) × asset_share_i,
    voltage_headroom_bus_i(t)
)

DOE_import_i(t) = min(
    asset_rated_kw_i,
    grid_import_capacity_cmz(t) × asset_share_i
)
```

DOEs are recalculated every 30 minutes triggered by `POST /api/v1/optimization/recalculate-does`.

### 11.3 P2P Energy Market (Future)

The platform includes a market-clearing mechanism for peer-to-peer energy trading between prosumers within a CMZ:

```
Double-auction clearing:
  Buyers sorted by willingness-to-pay (descending)
  Sellers sorted by willingness-to-accept (ascending)
  Clear at intersection → market clearing price (MCP)
  Constrained by OE limits — trades that would cause violations are rejected
```

**Reference:** E. Moret and P. Pinson, "Energy Collectives: A Community and Fairness Based Approach to Future Electricity Markets," IEEE Trans. Power Systems, 2019.

### 11.4 Background Task Schedule

| Task | Interval | Description |
|---|---|---|
| `grid_simulation_loop` | 20 s | Simulate grid telemetry, update bus voltages and asset outputs |
| `dispatch_loop` | 15 s | Check for pending dispatch events, send signals to DERs |
| `forecast_loop` | 5 min | Regenerate deployment-level forecasts |
| `broadcast_loop` | 5 s | Push grid state + alerts to all WebSocket clients |
| `scada_push_loop` | 30 s | Push LV DERMS snapshot to all active SCADA endpoints |

---

## 12. Operating Envelope (OE)

### 12.1 What is an Operating Envelope?

An Operating Envelope is a **time-varying MW limit** (import and/or export) assigned to a connection point or constraint management zone. It tells DER owners and aggregators how much power they can inject or absorb at each 30-minute interval without causing network violations.

### 12.2 OE Lifecycle

```
1. Forecast                Neural Grid forecasts load + solar for next 24h
   │
2. Power Flow              DistFlow computes headroom at each DT/CMZ
   │
3. OE Calculation          headroom → per-asset DOE limits
   │
4. OE Message              Format as SSEN_IEC MarketDocument or IEEE 2030.5
   │
5. Deliver                 Push to aggregator VTN / Flex Market platform
   │
6. Acknowledge             Aggregator ACKs receipt (Acknowledgement_MarketDocument)
   │
7. Activate                Grid event triggers → Activation_MarketDocument
   │
8. Perform                 Assets dispatch → telemetry flows back
   │
9. Measure                 Performance compared to OE limits
   │
10. Report                 Performance_MarketDocument → DNO / settlement system
```

### 12.3 SSEN IEC MarketDocument Format

SSEN uses an IEC CIM-based MarketDocument JSON format (not IEEE 2030.5) per **ENA-CPP-2024**.

All quantities in **MW** (unit code: `"MAW"`). Timestamps in **UTC ISO-8601**.

**5 Document Types:**

#### Document 1: OperatingEnvelope_MarketDocument
```json
{
  "OperatingEnvelope_MarketDocument": {
    "mRID": "OE-EVT001-EDINBURGH-NORTH-202603231400",
    "type": "A38",
    "process.processType": "Z01",
    "sender_MarketParticipant.mRID": "NEURALGRID_LT",
    "receiver_MarketParticipant.mRID": "SSEN_SOUTH_SCOTLAND",
    "createdDateTime": "2026-03-23T14:00:00Z",
    "period.timeInterval": {
      "start": "2026-03-23T14:00:00Z",
      "end": "2026-03-23T15:00:00Z"
    },
    "powerEnvelope": {
      "maxQuantity": { "quantity": 2.5, "measureUnit.name": "MAW" },
      "flowDirection.direction": "Increase"
    },
    "TimeSeries": [
      {
        "mRID": "TS-ASSET-001",
        "registeredResource.mRID": "ASSET-BESS-001",
        "measureUnit.name": "MAW",
        "Period": {
          "timeInterval": { "start": "...", "end": "..." },
          "Point": [{ "position": 1, "quantity": 0.05 }]
        }
      }
    ]
  }
}
```

#### Document 2: ReferenceEnergyCurveFlexOffer_MarketDocument
```json
{
  "ReferenceEnergyCurveFlexOffer_MarketDocument": {
    "mRID": "OFFER-OE-EVT001-EDINBURGH-NORTH-202603231400",
    "constraintZone.mRID": "OE-EVT001-EDINBURGH-NORTH-202603231400",
    "registeredResource.mRID": "AGGREGATOR-001",
    "flowDirection.direction": "Increase",
    "energyCurve": {
      "point": [{ "position": 1, "quantity": 2.0 }]
    }
  }
}
```
**Constraint:** `energyCurve.point.quantity` ≤ `powerEnvelope.maxQuantity.quantity`

#### Document 3: Acknowledgement_MarketDocument
```json
{
  "Acknowledgement_MarketDocument": {
    "mRID": "ACK-OE-EVT001-...",
    "receivedDocument.mRID": "OE-EVT001-EDINBURGH-NORTH-202603231400",
    "reason.code": "A01",
    "reason.text": "Envelope accepted"
  }
}
```

#### Document 4: Activation_MarketDocument
```json
{
  "Activation_MarketDocument": {
    "mRID": "ACT-EVT001-...",
    "linkedDocument.mRID": "OE-EVT001-EDINBURGH-NORTH-202603231400",
    "requestedQuantity": { "quantity": 1.8, "measureUnit.name": "MAW" },
    "activationStart": "2026-03-23T14:30:00Z"
  }
}
```

#### Document 5: Performance_MarketDocument
```json
{
  "Performance_MarketDocument": {
    "mRID": "PERF-EVT001-...",
    "linkedDocument.mRID": "ACT-EVT001-...",
    "period": { "start": "2026-03-23T14:30:00Z", "end": "2026-03-23T15:00:00Z" },
    "actualDeliveredQuantity": { "quantity": 1.75, "measureUnit.name": "MAW" },
    "activatedQuantity": { "quantity": 1.8, "measureUnit.name": "MAW" },
    "performanceRatio": 0.972
  }
}
```

**mRID Convention:** `OE-{event_ref}-{CMZ_SLUG}-{yyyymmddHHMM}`

**Reference:** ENA CPP OE Technical Specification — https://www.energynetworks.org/customers-and-community/new-connections/connecting-new-energy-resources/oe-toolkit

---

## 13. Dynamic OE via Time-Series Power Flow

> **v1.1 addition.** Replaces the arithmetic OE estimate with a physics-based calculation driven by DistFlow power flow run against 48-hour load and solar forecasts.

### 13.1 The Gap in v1.0

The v1.0 OE headroom formula was:
```
headroom_kw(t) = rated_kva × pf − forecast_load_kw(t) + forecast_generation_kw(t)
```
This ignores network topology entirely. Two assets with identical rated capacities on different feeders can have very different real OE limits depending on cable impedance, network length, and voltage profile. The arithmetic estimate can be 20–40% optimistic — it allows more export than the network can safely carry.

### 13.2 Time-Series DistFlow Architecture

```
48h Load Forecast (per LV bus)       48h Solar Forecast (per LV bus)
         │                                     │
         └─────────────────┬───────────────────┘
                           │
              For each 30-min slot t (96 slots):
                           │
              Set P_bus[i,t] = load[i,t] − solar[i,t]
                           │
              Run DistFlowSolver.solve()   ← existing solver
                           │
         ┌─────────────────┴────────────────────┐
         │                                      │
   V_bus[i,t] (p.u.)             I_branch[j,t] (kA)
   min/max voltage                max loading %
         │                                      │
         └──────────────┬───────────────────────┘
                        │
         compute_doe_from_pf_result()
                        │
    ┌───────────────────┴──────────────────────┐
    │                                          │
export_max_kw[t]                    import_max_kw[t]
  = min(rated_kw,                   = min(rated_kw,
        voltage_headroom_kw,               voltage_headroom_kw)
        thermal_headroom_kw)
    │                                          │
    └──────────────────┬───────────────────────┘
                       │
            DynamicOESlot (DB table)
            {cmz_id, asset_id, slot_start, slot_end,
             export_max_kw, import_max_kw,
             min_voltage_pu, max_voltage_pu,
             max_branch_loading_pct, source=DISTFLOW}
                       │
            Packaged as SSEN IEC OperatingEnvelope_MarketDocument
            with 96 × Point[] entries (48h at 30-min resolution)
```

### 13.3 DOE Calculation per Slot

For each 30-min interval t and each asset i connected at bus b(i):

```
voltage_headroom_kw(t) = (V_max_limit − V_max_pu[b,t]) / V_max_limit × rated_kw × 3
thermal_headroom_kw(t) = (1 − max_loading_pct[t] / 100) × rated_kw

export_max_kw[i,t] = min(
    rated_kw[i],
    voltage_headroom_kw(t),      ← prevents overvoltage from solar
    thermal_headroom_kw(t)       ← prevents cable overloading
)

import_max_kw[i,t] = min(
    rated_kw[i],
    (V_min_pu[b,t] − V_min_limit) / V_min_limit × rated_kw × 3   ← prevents undervoltage
)
```

Where:
- `V_max_limit = 1.05 p.u.` (UK ESQCR upper limit)
- `V_min_limit = 0.95 p.u.` (UK ESQCR lower limit)
- Limiting factor flagged: `VOLTAGE_HIGH | VOLTAGE_LOW | THERMAL | RATING`

### 13.4 Voltage Sensitivity Matrix

After the initial full DistFlow, a sensitivity matrix is computed:
```
∂V_i/∂P_j ≈ −2 × R_ij_shared / V_nom²
```
Where `R_ij_shared` is the resistance of the shared path from slack to the LCA (lowest common ancestor) of buses i and j. This enables fast OE updates (milliseconds) when a single asset changes state, without re-running full DistFlow.

### 13.5 Background Recalculation Schedule

| Trigger | Action |
|---|---|
| `dynamic_oe_loop` (every 30 min) | Recalculate OE for all CMZs, store in `dynamic_oe_slots` |
| `POST /lv-network/dt/{id}/power-flow` | Recalculate OE for DTs in that CMZ immediately |
| `GET /lv-network/dynamic-oe/{cmz_id}?recalculate=true` | On-demand forced recalculation |

### 13.6 Fallback Chain

```
1. DynamicOESlot records (DISTFLOW) — physics-based, preferred
   ↓ if not enough future slots
2. Arithmetic estimate (ARITHMETIC) — rated_kva − load + generation
   ↓ if forecasting fails
3. Static default — 70% of rated_kva as conservative default
```

### 13.7 System Solaire Context

For solar-heavy pilot zones (System Solaire), the primary congestion type is **VOLTAGE_HIGH**: midday solar export pushes bus voltages above 1.05 p.u., which is a statutory violation. The dynamic OE directly constrains solar export during these periods — DER aggregators receive tighter export limits at 11:00–14:00 and recover full export capacity at evening when solar drops.

A congested DT ranking endpoint (`GET /api/v1/lv-network/congested-dts`) identifies DTs by a composite score:
```
score = max_branch_loading_pct
      + (buses_below_0.95_pu × 20)
      + (buses_above_1.05_pu × 20)   ← solar overvoltage — primary for System Solaire
```

---

## 14. Flex Dispatch Workflow

```
Program                    Contract                   Event
───────                    ────────                   ─────
POST /programs      ──────▶ POST /contracts   ──────▶ POST /events
  service_type              program_id                  cmz_id
  payment_rate_£/MWh        aggregator_id               mw_target
  start/end date            min/max_mw                  window_start
  cmz_id                    payment_terms               window_end
                                                        dispatch_type
                                                         (CURTAILMENT |
                                                          INCREASE |
                                                          EMERGENCY)
        ↓
POST /events/{id}/dispatch
  → OE message generated (SSEN_IEC or IEEE 2030.5)
  → IEEE 2030.5 DERControl sent to each enrolled aggregator VEN
  → OpenADR EiEvent published if OpenADR aggregators registered
  → dispatch_loop monitors DER response
        ↓
DER response (30-60 seconds latency)
  → telemetry updated via grid_simulation_loop
  → WebSocket broadcasts to frontend
        ↓
POST /settlement/calculate
  → MDM actuals vs. dispatch target
  → performance_ratio = actual_MW / requested_MW
  → payment = performance_ratio × mw_delivered × duration_h × £/MWh
        ↓
POST /settlement/{id}/approve
  → Settlement record locked
  → Performance_MarketDocument generated for SSEN
```

---

## 15. Protocols & Messaging Formats

### 14.1 Protocol Comparison Table

| Protocol | Standard | Transport | Format | Use Case in Neural Grid |
|---|---|---|---|---|
| SSEN IEC | ENA-CPP-2024, IEC 62746 | HTTPS REST | JSON (IEC MarketDocument) | OE messages to SSEN |
| IEEE 2030.5 | IEEE 2030.5-2018 | HTTPS REST | JSON/XML | DOE + DER control to aggregators |
| OpenADR 2.0b | OASIS | HTTP/SOAP | XML EiEvent | Demand response to VENs |
| IEC 62746-4 | IEC 62746-4 | HTTPS REST | JSON | Generic OE (non-SSEN) |
| REST/JSON | HTTP/1.1 | HTTP | JSON | SCADA DaaS, integrations |
| MQTT | OASIS v5 | TCP | JSON payload | IoT SCADA push |
| MODBUS TCP | Modbus.org | TCP/502 | Register map | Legacy SCADA |
| DNP3 | IEEE 1815-2012 | TCP/20000 | Binary | Utility SCADA |
| OPC-UA | IEC 62541 | TCP/4840 | Binary/XML | Industrial SCADA |
| WebSocket | RFC 6455 | WS/WSS | JSON | Real-time frontend telemetry |
| JWT | RFC 7519 | HTTP Header | Base64 JSON | Platform authentication |

### 14.2 IEEE 2030.5 DOE Message Example

```json
{
  "DERControl": {
    "mRID": "DOE-BESS001-20260323T1400Z",
    "deviceCategory": "0x0002",
    "DERControlBase": {
      "opModExpLimW": { "value": 5000, "multiplier": 0 },
      "opModImpLimW": { "value": 3000, "multiplier": 0 }
    },
    "interval": {
      "duration": 1800,
      "start": 1742731200
    }
  }
}
```

### 14.3 OpenADR 2.0b EiEvent Example

```xml
<oadrPayload>
  <oadrSignedObject>
    <oadrDistributeEvent>
      <eiEvent>
        <eventDescriptor>
          <eventID>EVT-001</eventID>
          <eventStatus>far</eventStatus>
          <testEvent>false</testEvent>
          <vtnComment>Flex dispatch — curtail 2MW Edinburgh North</vtnComment>
        </eventDescriptor>
        <eiActivePeriod>
          <dtstart>2026-03-23T14:00:00Z</dtstart>
          <duration>PT30M</duration>
        </eiActivePeriod>
        <eiEventSignals>
          <eiEventSignal>
            <signalName>LOAD_DISPATCH</signalName>
            <signalType>delta</signalType>
            <intervals>
              <interval>
                <dtstart>2026-03-23T14:00:00Z</dtstart>
                <duration>PT30M</duration>
                <signalPayload>-2000</signalPayload>
              </interval>
            </intervals>
          </eiEventSignal>
        </eiEventSignals>
      </eiEvent>
    </oadrDistributeEvent>
  </oadrSignedObject>
</oadrPayload>
```

---

## 16. CIM-Based DER Aggregator Exchange

> **v1.1 addition; v1.2 updated** to align with the **Digital4Grids (D4G) IEC 62746-4 messaging profile** (AsyncAPI v1.0.0 / OpenAPI v2.0.0). The implementation follows the exact D4G `ReferenceEnergyCurve*_MarketDocument` format and Kafka topic names from the D4G specification.

### 16.1 Why CIM Over Proprietary Formats?

The existing aggregator interface (IEEE 2030.5 + OpenADR) is device-centric. For large aggregators managing portfolios as a group (Service Providing Groups / SPGs), the industry is moving to **fleet-level CIM market document exchange**:

| Approach | Granularity | Standard | Use case |
|---|---|---|---|
| IEEE 2030.5 | Per device (DERControl, DERStatus) | IEEE 2030.5-2018 | Smart inverters, residential DERs |
| OpenADR 2.0b | Per event (EiEvent, EiReport) | OASIS OpenADR | Demand response programs |
| **IEC 62325-301** | **Per market bid (ReserveBidMarketDocument)** | **IEC 62325-301** | **Flex market bids, DNO-TSO exchange** |
| **IEC 62746-4 / D4G** | **Per CMZ (ReferenceEnergyCurve*_MarketDocument)** | **IEC 62746-4 + D4G profile** | **DSO-SPG operating envelopes and flex offers** |

**SPG (Service Providing Group)**: the aggregator entity in the D4G model — a legal entity that aggregates DER assets and exchanges flex with the DSO.

### 16.2 D4G IEC 62746-4 — Message Format

All four document types share the same top-level structure:

```json
{
  "MessageDocumentHeader": {
    "messageId": "550e8400-e29b-41d4-a716-446655440000",
    "messageType": "OperatingEnvelope",
    "timestamp": "2026-03-24T14:00:00Z",
    "version": "1.0",
    "source": "NeuralGrid-DERMS",
    "correlationId": "EVT-042"
  },
  "ReferenceEnergyCurveOperatingEnvelope_MarketDocument": {
    "mRID": "OE-SSEN-A1B2C3D4E5F6",
    "revisionNumber": "1",
    "type": "A26",
    "createdDateTime": "2026-03-24T14:00:00Z",
    "Sender_MarketParticipant": {
      "MarketParticipant.mRID": { "value": "NEURALGRID-SSEN", "codingScheme": "A01" },
      "MarketParticipant.MarketRole": { "type": "Z01" }
    },
    "Receiver_MarketParticipant": {
      "MarketParticipant.mRID": { "value": "SPG-CMZ-001", "codingScheme": "A01" },
      "MarketParticipant.MarketRole": { "type": "Z02" }
    },
    "Process": { "processType": "A01" },
    "Period": { "timeInterval": { "start": "...", "end": "..." } },
    "Series": [{
      "curveType": "A01",
      "RegisteredResource": {
        "RegisteredResource.mRID": { "value": "CMZ-001", "codingScheme": "A01" }
      },
      "FlowDirection": { "direction": "A01" },
      "ResourceTimeSeries": { "value1ScheduleType": "generation" },
      "Series": [{
        "Measurement_Unit": { "name": "MAW" },
        "Period": [{
          "resolution": "PT30M",
          "timeInterval": { "start": "...", "end": "..." },
          "Point": [{ "position": 1, "Max_Quantity": { "quantity": 0.075, "quality": "A06" } }]
        }]
      }]
    }]
  }
}
```

**Key field definitions:**
- `codingScheme: "A01"` = EIC (Energy Identification Coding Scheme, ENTSO-E)
- `MarketRole.type: "Z01"` = DSO/DERMS; `"Z02"` = SPG/Aggregator
- `processType: "A01"` = Day-ahead; `"A16"` = Realised (historical)
- `FlowDirection.direction`: `"A01"` = UP (export/generation); `"A02"` = DOWN (import/curtailment)
- `Measurement_Unit.name: "MAW"` = megawatt — **all quantities in MW, not kW**
- `quality: "A06"` = Calculated; `"A04"` = As provided
- `resolution: "PT30M"` = 30-minute slots (ISO 8601 duration)

### 16.3 Four Document Types

| Document | Direction | Kafka Topic | messageType | Point field |
|---|---|---|---|---|
| `ReferenceEnergyCurveOperatingEnvelope_MarketDocument` | DSO → SPG | `dso_operating_envelope` | `OperatingEnvelope` | `Max_Quantity` |
| `ReferenceEnergyCurveFlexOffer_MarketDocument` | SPG → DSO | `flex-offers` | `FlexOffer` | `Quantity` |
| `ReferenceEnergyCurveBaselineNotification_MarketDocument` | DSO → SPG | `baseline_24h` | `BaselineNotification` | `Baseline_Quantity` |
| `ReferenceEnergyCurveHistoricalData_MarketDocument` | DSO → SPG | `historical_data` | `HistoricalData` | `Historical_Quantity` |

**OperatingEnvelope**: DSO tells SPG the maximum export and import limits at each CMZ for each 30-min slot. Two Series per document — one UP (export ceiling) and one DOWN (import ceiling).

**FlexOffer**: SPG tells DSO how much flexibility is available (up/down, in MW) for each slot. The DSO uses this to plan activations.

**BaselineNotification**: DSO sends the SPG the expected baseline consumption/generation for the next 24 hours. SPG uses this to size their flex offer relative to baseline.

**HistoricalData**: DSO sends actual measured data back to the SPG (for settlement reconciliation and model calibration).

### 16.4 Message Flow

```
Neural Grid DERMS (DSO)                     SPG / Aggregator
        |                                          |
        |-- OperatingEnvelope ----------------->   |  Kafka: dso_operating_envelope
        |   ReferenceEnergyCurveOperatingEnvelope  |  48 x 30-min slots, in MAW
        |   (export_max + import_max per slot)     |
        |                                          |
        |-- BaselineNotification --------------->  |  Kafka: baseline_24h
        |   Expected baseline for next 24h         |
        |                                          |
        |<- FlexOffer ---------------------------  |  Kafka: flex-offers / REST POST
        |   Available flex up/down per slot (MAW)  |
        |                                          |
        |-- Activation (IEC 62325 A53) --------->  |  REST: triggered by flex event
        |   Accepted quantity + event ref          |
        |                                          |
        |<- HistoricalData (post-event) ---------  |  Kafka: historical_data
```

### 16.5 Kafka Transport

| Topic | Direction | Document Type | Purpose |
|---|---|---|---|
| `dso_operating_envelope` | DSO -> SPG | OperatingEnvelope | OE limits per CMZ, every 30 min |
| `flex-offers` | SPG -> DSO | FlexOffer | Aggregator flex availability |
| `baseline_24h` | DSO -> SPG | BaselineNotification | 24-h baseline ahead |
| `historical_data` | DSO -> SPG | HistoricalData | Post-event actuals for settlement |

Kafka is optional — disabled when `KAFKA_BOOTSTRAP_SERVERS` is empty. Library: `aiokafka`. All paths degrade gracefully to REST-only.

### 16.6 CIM API Endpoints

| Method | Path | Description |
|---|---|---|
| `GET` | `/api/v1/aggregator/cim/dispatch/{event_id}` | Build + publish OperatingEnvelopeMessage for event |
| `POST` | `/api/v1/aggregator/cim/flex-offer` | Receive FlexOfferMessage from SPG |
| `POST` | `/api/v1/aggregator/cim/capability` | Register SPG fleet (asset catalogue) |
| `POST` | `/api/v1/aggregator/cim/status` | Receive fleet telemetry from SPG |
| `GET` | `/api/v1/aggregator/cim/bid/{cmz_id}` | Get IEC 62325 ReserveBid template |
| `POST` | `/api/v1/aggregator/cim/bid` | Submit IEC 62325 ReserveBid |
| `GET` | `/api/v1/aggregator/cim/protocols` | List supported protocols + topics |

### 16.7 Esoteric Terms Explained

**EIC (Energy Identification Coding Scheme)**: A 16-character alphanumeric code maintained by ENTSO-E that uniquely identifies any party in the European electricity market — DSOs, TSOs, aggregators, market participants. Think of it as an IBAN for energy actors. `codingScheme: "A01"` in CIM documents always means EIC.

**MAW (Megawatt)**: The UN/CEFACT unit code for megawatt in CIM market documents. All power quantities in IEC 62325 / IEC 62746-4 documents are in MAW, not kW. The platform converts internally: `maw = kw / 1000`.

**SPG (Service Providing Group)**: The D4G term for an aggregator or portfolio manager — an entity that pools DER assets and exchanges flexibility offers with the DSO. Equivalent to a VEN in OpenADR, or a Balance Responsible Party in wholesale markets.

**CMZ (Constraint Management Zone)**: A geographic zone of the distribution network defined by a thermal or voltage constraint. OE limits are issued per CMZ, not per asset. A CMZ typically corresponds to a 11kV feeder section downstream of a primary substation.

**mRID (Master Resource Identifier)**: The CIM identifier for any object — documents, market participants, grid nodes. In IEC 62325/62746-4, `mRID` is typically a UUID or structured string (e.g., `OE-SSEN-A1B2C3`). In CIM XML, it maps to the `rdf:about` attribute.

**curveType "A01"**: In IEC 62325, `"A01"` means a sequential fixed-size time series (constant-resolution slots). Other values: `"A02"` = point, `"A03"` = variable resolution. Almost all OE/flex documents use `"A01"`.

**processType**: Classifies what the document is about. Key values: `"A01"` = day-ahead, `"A14"` = forecast, `"A16"` = realised, `"A40"` = intraday. The D4G OE documents use `"A01"` (day-ahead, 48-slot horizon).

**revisionNumber**: Monotonically increasing integer (`"1"`, `"2"`, ...) on the same `mRID`. If the DSO reissues an OE document for the same CMZ and period, they increment `revisionNumber`. Receivers always use the highest revision.

**FCA (Flexibility Contracting and Activation)**: The D4G use-case label for the full workflow — from capability registration through to OE publication, flex offers, activation, and settlement. The four D4G document types implement FCA between DSO and SPG.

**References:**
- D4G AsyncAPI spec: `d4g-iec62746_4_messages-_asyncapi.yaml` (v1.0.0)
- D4G OpenAPI spec: `d4g-iec62746_4_messages-swagger.yml` (v2.0.0)
- IEC 62325-301 (Electricity market comms): https://www.iec.ch/62325
- IEC 62746-4 (DERMS-DER interface): https://www.iec.ch/62746-4
- Digital4Grids schema repo: https://github.com/Digital4Grids/Bridge_energy_schemas/tree/main/IEC62746-4
## 17. SCADA Gateway & DaaS

### 17.1 Architecture

```
Neural Grid Backend
       │
       ├── scada_push_loop (every 30s)
       │      │
       │      ▼  For each active SCADAEndpoint:
       │      get_lv_derms_snapshot()
       │        ├── Grid nodes + feeder loading
       │        ├── LV bus voltages (pu, volts, status)
       │        ├── DER asset outputs (kW, SOC, state)
       │        ├── OE limits per asset
       │        └── Active flex events
       │      │
       │      ├── REST/JSON → POST {target_url}/derms-data
       │      ├── MQTT → publish to {topic}/derms-data
       │      └── MODBUS/DNP3/OPC-UA → L&T Edge Agent gateway
       │
       └── DaaS API (pull)
              GET /api/v1/scada/snapshot
              Header: X-DaaS-Key: lt_daas_<32hex>
              Header: X-Deployment-ID: ssen
                   ↓
              Verify SHA-256 hash, check rate limit, check permissions
                   ↓
              Return filtered snapshot JSON
                   ↓
              Record usage (path, bytes, latency, status) → billing
```

### 17.2 DaaS API Key Security

1. `generate_api_key()` generates: `lt_daas_{32 hex chars}` (128-bit entropy)
2. Returns `(plain_key, sha256_hash, key_prefix[:16])`
3. **Only the SHA-256 hash is stored** in the `daas_api_keys` table
4. Plain key shown once in the creation response — never retrievable again
5. Verification: `hashlib.sha256(incoming_key.encode()).hexdigest() == stored_hash`

### 17.3 DaaS Permission Scopes

| Scope | Snapshot Section | Typical Customer |
|---|---|---|
| `can_read_lv_voltages` | `lv_network.buses[].v_pu` | Grid planner, DSO |
| `can_read_feeder_loading` | `grid.feeders[].loading_pct` | SCADA operator |
| `can_read_der_outputs` | `assets[].output_kw` | Aggregator billing |
| `can_read_oe_limits` | `oe_limits[]` | Flex market operator |
| `can_read_flex_events` | `active_flex_events[]` | Energy trader |

---

## 18. Integration Config Manager

All external system connections are configured per-deployment via the Integration Config Manager. Each integration has a **mode** that can be toggled at runtime without restart.

| Mode | Behaviour |
|---|---|
| `SIMULATION` | Returns synthetic data; no external API calls; safe for development and demos |
| `LIVE` | Connects to real external endpoint; reads/writes to production systems |

**Supported Integration Types:**

| system_type | External System | Integration Purpose |
|---|---|---|
| `GE_ADMS` | GE Grid ADMS | MV grid state, topology, hosting capacity |
| `SCADA` | SCADA / DCS | Push LV data, receive control commands |
| `DMS` | Distribution Management System | Network switching, outage management |
| `MDM` | Meter Data Management | AMI reads, settlement actuals |
| `WEATHER_API` | Open-Meteo, Met Office | Solar irradiance, temperature for forecasting |
| `MARKET_API` | Balancing Mechanism / Flex Market | Market clearing prices, auction results |
| `DER_AGGREGATOR` | Aggregator backend | Device registration, dispatch confirmation |

**API:**
```
GET  /api/v1/integrations              → list all
POST /api/v1/integrations              → create
POST /api/v1/integrations/{id}/toggle-mode    → SIMULATION ↔ LIVE
POST /api/v1/integrations/{id}/test    → connectivity test
GET  /api/v1/integrations/{id}/sim-params → get simulation parameters
PUT  /api/v1/integrations/{id}/sim-params → override simulated values
```

---

## 19. Settlement & Performance Measurement

```
Event Dispatched
      │
      ├── Telemetry recorded (30s intervals) for duration of event
      │     Source: grid_simulation_loop or real MDM readings
      │
      └── POST /api/v1/settlement/calculate
              input:
                contract_id        → payment rate (£/MWh)
                event_id           → requested_mw, duration
                metered_actuals    → MW delivered per interval (from MDM)
              output:
                performance_ratio  = actual_mw_delivered / requested_mw
                baseline_energy_mwh
                adjusted_energy_mwh
                payment_£          = adj_energy × rate × performance_ratio
                settlement_status  = CALCULATED
              │
              └── POST /settlement/{id}/approve
                      settlement_status  = APPROVED
                      Performance_MarketDocument generated → SSEN / DNO
```

**Performance ratio benchmark (typical UK flexibility markets):**
- ≥ 0.95 → Full payment
- 0.80–0.95 → Pro-rata payment
- < 0.80 → Penalty clause may apply (contract-dependent)

---

## 20. System Flow Diagrams

### 18.1 End-to-End OE Dispatch Flow

```
DNO Operator                Neural Grid                  Aggregator / DERs
     │                           │                               │
     │── Create Event ──────────▶│                               │
     │   (MW target, CMZ,        │                               │
     │    time window)           │── Run DistFlow ───────────────│
     │                           │   (LV power flow)             │
     │                           │── Calculate OE headroom       │
     │                           │── Generate OE message         │
     │                           │   (SSEN_IEC format)           │
     │◀─ Preview OE message ─────│                               │
     │                           │                               │
     │── Dispatch Event ─────────│                               │
     │                           │── IEEE 2030.5 DERControl ────▶│
     │                           │── OpenADR EiEvent ───────────▶│
     │                           │                               │
     │                           │◀─ Acknowledgement ────────────│
     │                           │◀─ DER telemetry (30s) ────────│
     │                           │                               │
     │◀─ WebSocket updates ──────│                               │
     │   (real-time MW response) │                               │
     │                           │                               │
     │── Approve Settlement ─────│                               │
     │                           │── Performance_MarketDocument  │
     │                           │   → SSEN reporting            │
     │◀─ Payment confirmed ──────│                               │
```

### 18.2 LV Network Data Flow

```
Map (Frontend)               API                   Backend Services
      │                       │                          │
      │ User zooms to DT      │                          │
      │──── GET /lv-network/dt/{id} ──────────────────▶  │
      │                       │    1. Check DB cache     │
      │                       │    2. If miss:           │
      │                       │       Overpass API query │
      │                       │       (or synthetic gen) │
      │                       │    3. Store GeoJSON       │
      │◀─── route_geojson + buses[] ─────────────────────│
      │                       │                          │
      │ Click Run Power Flow  │                          │
      │──── POST /lv-network/dt/{id}/power-flow ───────▶  │
      │                       │    DistFlow backward     │
      │                       │    sweep (3-10 iter)     │
      │                       │    → bus voltages (pu)   │
      │                       │    → violations flagged  │
      │◀─── LVBus[] with v_pu, status ───────────────────│
      │                       │                          │
      │ Render voltage chart   │                          │
      │ Red markers = violations                          │
      │                       │                          │
      │──── GET /forecasting/oe-headroom/{cmz} ────────▶  │
      │◀─── headroom_kw[] per 30-min interval ───────────│
      │                       │                          │
      │ SSEN OE doc preview    │                          │
```

### 18.3 SCADA DaaS Architecture

```
L&T Neural Grid Platform
┌─────────────────────────────────────────────┐
│                                             │
│  LV Network  ──┐                            │
│  Grid State  ──┼──▶ get_lv_derms_snapshot   │
│  DER Assets  ──┤          │                 │
│  OE Limits   ──┘          │                 │
│  Flex Events──┘           │                 │
│                     ┌─────▼───────────────┐ │
│  PUSH (every 30s)   │  SCADA Push Loop    │ │    SCADA / DMS / ADMS
│  ──────────────────▶│  REST/MQTT/MODBUS   │─┼──────────────────────▶
│                     │  DNP3 / OPC-UA      │ │
│                     └─────────────────────┘ │
│                                             │
│  PULL (on demand)                           │
│  External SCADA ──X-DaaS-Key header────────▶│ GET /api/v1/scada/snapshot
│                 ◀──filtered JSON────────────│
│                 ──usage recorded────────────│
└─────────────────────────────────────────────┘
```

---

## 21. API Surface Summary

Full interactive documentation: `http://localhost:8080/api/docs`

| Module | Routes | Key Endpoints |
|---|---|---|
| Auth | 3 | `/auth/login`, `/auth/me`, `/auth/deployments` |
| Grid | 6 | `/grid/dashboard`, `/grid/state`, `/grid/topology`, `/grid/power-flow` |
| Assets | 5 | `/assets` CRUD, `/assets/{id}/telemetry` |
| Dispatch | 6 | `/events` CRUD, `/events/{id}/dispatch`, `/events/{id}/oe-messages/formatted` |
| Forecasting | 8 | `/forecasting/all`, `/forecasting/lv-feeder/{id}`, `/forecasting/oe-headroom/{cmz_id}` |
| LV Network | 4 | `/lv-network/dt/{id}`, `/lv-network/dt/{id}/power-flow` |
| Programs | 4 | `/programs` CRUD |
| Contracts | 5 | `/contracts` CRUD, `/contracts/{id}/activate` |
| Optimization | 4 | `/optimization/dr-dispatch`, `/optimization/recalculate-does` |
| Settlement | 3 | `/settlement/calculate`, `/settlement/{id}/approve` |
| Integrations | 7 | `/integrations` CRUD, `/integrations/{id}/toggle-mode`, `test`, `sim-params` |
| SCADA Gateway | 13 | `/scada/endpoints`, `/scada/snapshot/*`, `/scada/daas/keys` |
| Aggregator | 2 | `/aggregator/devices`, `/aggregator/register` |
| Admin | 6 | `/admin/users`, `/admin/audit-logs`, `/admin/system-health`, `/admin/config` |
| Reports | 2 | `/reports/summary`, `/reports/export` |
| Counterparties | 4 | `/counterparties` CRUD |
| WebSocket | 1 | `/ws` — real-time telemetry push |
| Health | 1 | `/health` — liveness probe |

---

## 22. Non-Functional Requirements

| Requirement | Target | Current Status |
|---|---|---|
| API response time (P95) | < 200 ms | ✓ (SQLite, no network calls in SIMULATION) |
| WebSocket broadcast latency | < 1 s | ✓ (5s interval, asyncio) |
| DistFlow convergence time | < 100 ms for 50-bus network | ✓ |
| Forecast generation time | < 5 s for 48h × 30min | ✓ |
| SCADA push interval | Configurable 10–3600 s | ✓ (default 60s) |
| Multi-deployment isolation | Hard isolation per X-Deployment-ID header | ✓ |
| Authentication | JWT HS256, 8-hour expiry | ✓ |
| DaaS key security | SHA-256 hashed, plain key not stored | ✓ |
| Horizontal scaling | Stateless API, shared DB | ✓ (Render.com config present) |
| Audit trail | All write operations logged to audit_logs | ✓ |

---

## 23. References

### Standards & Protocols
1. **IEEE 2030.5** (Smart Energy Profile 2.0) — https://standards.ieee.org/ieee/2030.5/5897/
2. **OpenADR 2.0b** — https://www.openadr.org/specification
3. **IEC 62746-4** (Systems Interface between Customer Energy Management System and the Power Management System) — https://www.iec.ch/62746-4
4. **IEC 62541** (OPC Unified Architecture) — https://opcfoundation.org/developer-tools/documents/opc-ua-specification/
5. **IEEE 1815-2012** (DNP3) — https://standards.ieee.org/ieee/1815/4937/
6. **IEC 61968/61970** (CIM — Common Information Model) — https://cimug.ucaiug.org
7. **ENA CPP 2024** (Common Power Platform, Operating Envelopes) — https://www.energynetworks.org/customers-and-community/new-connections/oe-toolkit
8. **ESQCR 2002** (UK Electricity Safety, Quality and Continuity Regulations — voltage limits) — https://www.legislation.gov.uk/uksi/2002/2665/contents

### Algorithms & Academic References
9. **DistFlow (Baran & Wu, 1989)** — M.E. Baran and F.F. Wu, "Network reconfiguration in distribution systems for loss reduction and load balancing," IEEE Trans. Power Delivery, vol. 4, no. 2, pp. 1401–1407, 1989. https://doi.org/10.1109/61.25622
10. **P2P Energy Markets** — E. Moret and P. Pinson, "Energy Collectives: A Community and Fairness Based Approach to Future Electricity Markets," IEEE Trans. Power Systems, vol. 34, no. 5, 2019. https://doi.org/10.1109/TPWRS.2019.2896259
11. **Dynamic Operating Envelopes** — CSIRO EDGE Project — https://www.csiro.au/en/research/technology-space/energy/distributed-energy-resources

### GIS & Open Data
12. **OpenStreetMap Overpass API** — https://wiki.openstreetmap.org/wiki/Overpass_API
13. **Overpass Turbo (Query Tester)** — https://overpass-turbo.eu
14. **Open-Meteo (Free NWP API)** — https://open-meteo.com/en/docs
15. **ENTSO-E Transparency Platform** — https://transparency.entsoe.eu

### Regulatory
16. **RIIO-ED2** (Ofgem SSEN price control framework) — https://www.ofgem.gov.uk/check-if-energy-price-cap-affects-you/riio-ed2
17. **UPERC-DR-2025** (Uttar Pradesh Electricity Regulatory Commission — Demand Response) — https://www.uperc.org
18. **ENA Engineering Recommendation P2/7** (Security of Supply) — https://www.energynetworks.org/industry-hub/resource-library/?type=Engineering+Recommendation&sub=P2

### Tools & Libraries
19. **FastAPI** — https://fastapi.tiangolo.com
20. **SQLAlchemy 2.0 async** — https://docs.sqlalchemy.org/en/20/orm/extensions/asyncio.html
21. **react-leaflet v5** — https://react-leaflet.js.org
22. **Leaflet.js** — https://leafletjs.com
23. **Recharts** — https://recharts.org

---

*Document generated from Neural Grid v1.0 platform codebase. For technical questions contact the L&T Smart Grid Division.*
