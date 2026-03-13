# ShadowBroker Engineering Roadmap

> **Version**: 1.0 | **Created**: 2026-03-12 | **Codebase**: v0.8.0
> **Purpose**: Structured, agent-executable roadmap to bring ShadowBroker to production-grade quality.
> **How to use**: Each task is an atomic unit of work. An AI agent or developer can pick any task whose dependencies are met and execute it independently. Mark tasks `[x]` when complete.

---

## Architecture Overview

```
live-risk-dashboard/
  frontend/                          # Next.js 16 + React 19 + MapLibre GL
    src/app/page.tsx                 #   621 LOC — dashboard orchestrator (19 state vars, 33 hooks)
    src/components/
      MaplibreViewer.tsx             #   3,065 LOC — GOD COMPONENT (map + all layers + icons + popups)
      CesiumViewer.tsx               #   1,813 LOC — DEAD CODE (never imported)
      NewsFeed.tsx                   #   1,088 LOC — news + entity detail panels
      + 15 more components
    next.config.ts                   #   ignoreBuildErrors: true, ignoreDuringBuilds: true (!!!)
  backend/                           # Python FastAPI + Node.js AIS proxy
    main.py                          #   315 LOC — FastAPI app entry
    services/
      data_fetcher.py                #   2,417 LOC — GOD MODULE (15+ data sources in one file)
      ais_stream.py                  #   367 LOC — WebSocket AIS client
      + 10 more service modules
    test_*.py (26 files)             #   ALL manual print-based, zero assertions, zero pytest
  docker-compose.yml                 #   No health checks, no resource limits
  .github/workflows/docker-publish.yml  # No test step, no image scanning
```

---

## Scoring Baseline (Pre-Roadmap)

| Category | Score | Key Issue |
|----------|-------|-----------|
| Thread Safety | 3/10 | Race conditions on `routes_fetch_in_progress`, unguarded `latest_data` writes |
| Type Safety | 2/10 | 50+ `any` types, TS/ESLint errors hidden by config flags |
| Testing | 0/10 | Zero automated tests, 26 manual print scripts |
| Error Handling | 4/10 | Bare `except: pass` clauses, no error boundaries on panels |
| Architecture | 3/10 | Two god files (3065 + 2417 LOC), massive prop drilling |
| DevOps | 5/10 | Good Docker multi-arch, but no health checks/limits/scanning |
| Security | 4/10 | No rate limiting, no input validation, no HTTPS docs |
| Accessibility | 1/10 | No ARIA labels, no keyboard nav, no semantic HTML |
| **Overall** | **3.5/10** | Production-adjacent, not production-ready |

---

## Phase 1: Stabilization & Safety

**Goal**: Fix things that silently corrupt data, hide bugs, or could cause production incidents. Every task here has outsized impact relative to effort.

**All Phase 1 tasks are independent and can be executed in parallel.**

---

### Task 1.1: Fix thread safety bugs in data_fetcher.py

- [ ] **Complete**

| Field | Value |
|-------|-------|
| **Effort** | S (1-3h) |
| **Priority** | P0 — data corruption risk |
| **Dependencies** | None |

**File**: `backend/services/data_fetcher.py`

**Problem**: `routes_fetch_in_progress` (~line 645) is a bare global boolean read/written from multiple threads with no lock. `latest_data` is written at ~lines 599, 627, 639 without `_data_lock`. These are TOCTOU race conditions.

**Scope**:
1. Add a `_routes_lock = threading.Lock()` and wrap all reads/writes of `routes_fetch_in_progress` and `dynamic_routes_cache` with it. The current pattern (`if routes_fetch_in_progress: return; routes_fetch_in_progress = True`) is a classic TOCTOU race.
2. Find every `latest_data[...] = ...` assignment NOT already under `_data_lock` and wrap it. Search pattern: `latest_data\[`.
3. Audit `_trails_lock` usage — ensure `flight_trails` dict is never accessed outside the lock. Check all references beyond the lock at ~line 1187.

**Verification**:
```bash
# Every latest_data write should be inside a lock
grep -n "latest_data\[" backend/services/data_fetcher.py
# Confirm routes_fetch_in_progress is no longer a bare boolean check
grep -n "routes_fetch_in_progress" backend/services/data_fetcher.py
```
All writes should be inside `with _data_lock:` or `with _routes_lock:` blocks.

---

### Task 1.2: Replace bare except clauses with specific exceptions

- [ ] **Complete**

| Field | Value |
|-------|-------|
| **Effort** | XS (30min) |
| **Priority** | P0 — swallows KeyboardInterrupt, SystemExit |
| **Dependencies** | None |

**Files**:
- `backend/services/cctv_pipeline.py` ~line 223: `except:` → `except (ValueError, TypeError) as e:` + `logger.debug()`
- `backend/services/liveuamap_scraper.py` ~lines 43, 59: `except:` → `except Exception as e:` + `logger.debug()`
- `backend/services/data_fetcher.py` ~lines 705-706: `except Exception: pass` → add `logger.warning()`

**Verification**:
```bash
# Must return ZERO matches
grep -rn "except:" backend/ --include="*.py" | grep -v "except Exception" | grep -v "except ("
# Also check for silent swallows
grep -rn "except.*: pass" backend/ --include="*.py"
```

---

### Task 1.3: Re-enable TypeScript and ESLint checking

- [ ] **Complete**

| Field | Value |
|-------|-------|
| **Effort** | M (3-6h) |
| **Priority** | P0 — currently hiding ALL type errors and lint violations |
| **Dependencies** | None (but pairs well with Phase 2 decomposition) |

**Files**:
- `frontend/next.config.ts` — remove `typescript: { ignoreBuildErrors: true }` and `eslint: { ignoreDuringBuilds: true }`
- `frontend/package.json` — fix lint script from `"lint": "eslint"` to `"lint": "next lint"` or `"lint": "eslint src/"`

**Scope**:
1. Run `npx tsc --noEmit` in `frontend/` and record all errors.
2. Fix type errors file by file. The heaviest offenders:
   - `MaplibreViewer.tsx`: ~55 occurrences of `: any` — create proper interfaces for props, GeoJSON features, events.
   - `page.tsx`: state types need explicit interfaces.
3. Replace `any` with proper interfaces. Key types needed:
   ```typescript
   interface DataPayload { commercial_flights: Flight[]; military_flights: Flight[]; satellites: Satellite[]; ... }
   interface Flight { hex: string; lat: number; lon: number; alt_baro: number; ... }
   interface MaplibreViewerProps { data: DataPayload; activeLayers: ActiveLayers; ... }
   ```
4. Only after ALL errors are fixed, remove the two `ignore*` flags from `next.config.ts`.
5. Fix the lint script and run `npm run lint` clean.

**Verification**:
```bash
cd frontend && npx tsc --noEmit  # Must exit 0
cd frontend && npm run lint       # Must exit 0
cd frontend && npm run build      # Must succeed WITHOUT ignoreBuildErrors
```

---

### Task 1.4: Add transaction safety to cctv_pipeline.py

- [ ] **Complete**

| Field | Value |
|-------|-------|
| **Effort** | XS (30min) |
| **Priority** | P1 |
| **Dependencies** | None |

**File**: `backend/services/cctv_pipeline.py`

**Scope**: Wrap all SQLite write operations in try/except with explicit `conn.rollback()` on failure. Currently if an insert fails midway, the connection may be left dirty.

**Verification**: Search for all `conn.execute` / `cursor.execute` calls and confirm each write path has rollback handling.

---

### Task 1.5: Add rate limiting and input validation to backend API

- [ ] **Complete**

| Field | Value |
|-------|-------|
| **Effort** | S (1-3h) |
| **Priority** | P1 — security exposure |
| **Dependencies** | None |

**File**: `backend/main.py`

**Scope**:
1. Add a simple in-memory rate limiter (e.g., `slowapi` or custom middleware). Target: 60 req/min per IP for data endpoints.
2. Add Pydantic validation for coordinate parameters on all endpoints that accept lat/lng:
   ```python
   from pydantic import Field, confloat
   lat: confloat(ge=-90, le=90)
   lng: confloat(ge=-180, le=180)
   ```
3. Add `slowapi` to `requirements.txt` if used.

**Verification**:
```bash
# Rate limit test: 100 rapid requests should get 429 after ~60
for i in $(seq 1 100); do curl -s -o /dev/null -w "%{http_code}\n" http://localhost:8000/api/live-data/fast; done | sort | uniq -c
# Validation test: invalid coords should return 422
curl -s http://localhost:8000/api/region-dossier?lat=999&lng=999 | grep -c "error"
```

---

### Task 1.6: Delete dead code

- [ ] **Complete**

| Field | Value |
|-------|-------|
| **Effort** | XS (30min) |
| **Priority** | P1 |
| **Dependencies** | None |

**Files to delete**:
- `frontend/src/components/CesiumViewer.tsx` — 1,813 LOC, never imported anywhere
- Root one-off scripts: `refactor_cesium.py`, `zip_repo.py`, `jobs.json` (if tracked)
- Backend one-off scripts: `check_regions.py`, `analyze_xlsx.py`, `clean_osm_cctvs.py`, `extract_ovens.py`, `geocode_datacenters.py` (if tracked and not gitignored)

**Also**:
- Remove `fetch_bikeshare()` function from `data_fetcher.py` and its scheduler entry (if bikeshare layer no longer exists in the UI)

**Verification**:
```bash
grep -rn "CesiumViewer" frontend/src/   # Must return 0 matches
grep -rn "fetch_bikeshare" backend/     # Must return 0 matches
cd frontend && npm run build            # Must succeed
```

---

## Phase 2: Frontend Architecture — God Component Decomposition

**Goal**: Break `MaplibreViewer.tsx` (3,065 LOC) and `page.tsx` (621 LOC) into maintainable, testable units. This is the highest-impact refactor in the entire codebase.

**Dependency chain**: `2.1 + 2.2` (parallel) → `2.3` → `2.4` → `2.5`

---

### Task 2.1: Extract SVG icons and aircraft classification

- [ ] **Complete**

| Field | Value |
|-------|-------|
| **Effort** | S (1-3h) |
| **Priority** | P1 |
| **Dependencies** | None |

**Source**: `frontend/src/components/MaplibreViewer.tsx`

**New files to create**:
| File | Content | Source Lines |
|------|---------|-------------|
| `frontend/src/components/map/icons/AircraftIcons.ts` | All SVG path data constants (plane, heli, turboprop silhouettes) | ~1-150 |
| `frontend/src/components/map/icons/SvgMarkers.ts` | SVG factory functions (`makeFireSvg`, `makeAircraftSvg`, etc.) | ~60-91 |
| `frontend/src/utils/aircraftClassification.ts` | Military/private/commercial classifier function | ~163-169 |

**Scope**: Pure extraction — move constants and pure functions out. No logic changes. Update imports in MaplibreViewer.

**Verification**: `wc -l frontend/src/components/MaplibreViewer.tsx` decreases by ~200. `npm run build` succeeds.

---

### Task 2.2: Extract map utilities and style definitions

- [ ] **Complete**

| Field | Value |
|-------|-------|
| **Effort** | S (1-3h) |
| **Priority** | P1 |
| **Dependencies** | None (parallel with 2.1) |

**Source**: `frontend/src/components/MaplibreViewer.tsx`

**New files to create**:
| File | Content | Source Lines |
|------|---------|-------------|
| `frontend/src/utils/positioning.ts` | Interpolation helpers (lerp, bearing calc) | ~171-193 |
| `frontend/src/components/map/styles/mapStyles.ts` | Dark/light/satellite/FLIR/NVG/CRT style URL definitions | ~195-235 |

**Scope**: Pure extraction of stateless helpers.

**Verification**: Build succeeds. Grep confirms moved functions are only defined in the new files.

---

### Task 2.3: Extract custom hooks from MaplibreViewer

- [ ] **Complete**

| Field | Value |
|-------|-------|
| **Effort** | M (3-6h) |
| **Priority** | P1 |
| **Dependencies** | Tasks 2.1, 2.2 |

**Source**: `frontend/src/components/MaplibreViewer.tsx`

**New files to create**:
| File | Content | Source Lines |
|------|---------|-------------|
| `frontend/src/hooks/useImperativeSource.ts` | The `useImperativeSource` hook for direct MapLibre source updates | ~268-285 |
| `frontend/src/hooks/useMapDataLayers.ts` | GeoJSON builder `useMemo` hooks (earthquakes, jamming, CCTV, data centers, fires, outages, KiwiSDR) | ~405-582 |
| `frontend/src/hooks/useMapImages.ts` | Image loading system for `onMapLoad` callback | ~585-720 |
| `frontend/src/hooks/useTrafficGeoJSON.ts` | Flight/ship/satellite GeoJSON construction with interpolation | ~784-900 |

**Scope**: Each hook accepts the map instance ref and relevant data as parameters and returns GeoJSON/state. Must handle the `map.getSource()` / `src.setData()` imperative pattern cleanly.

**Verification**: `wc -l frontend/src/components/MaplibreViewer.tsx` is under 1,500 LOC. All map layers still render correctly (manual visual check required).

---

### Task 2.4: Extract HTML label rendering into MapMarkers component

- [ ] **Complete**

| Field | Value |
|-------|-------|
| **Effort** | S (1-3h) |
| **Priority** | P2 |
| **Dependencies** | Task 2.3 |

**Source**: `frontend/src/components/MaplibreViewer.tsx` ~lines 1800-1910

**New file**: `frontend/src/components/map/MapMarkers.tsx`

**Scope**: Move the HTML overlay rendering (flight labels, carrier labels, tracked aircraft labels, cluster count badges) into a dedicated component. Receives position arrays via props.

**Verification**: Labels still appear on map. `MaplibreViewer.tsx` drops below 1,200 LOC.

---

### Task 2.5: Introduce React Context for shared dashboard state

- [ ] **Complete**

| Field | Value |
|-------|-------|
| **Effort** | M (3-6h) |
| **Priority** | P1 |
| **Dependencies** | Tasks 2.1-2.4 (reduces merge conflicts) |

**Source**: `frontend/src/app/page.tsx` (621 LOC, 19 state variables, 33 hooks)

**New files to create**:
| File | Content |
|------|---------|
| `frontend/src/contexts/DashboardContext.tsx` | Context provider: `activeLayers`, `activeFilters`, `selectedEntity`, `eavesdrop` state, `effects`, `activeStyle`, `measureMode` |
| `frontend/src/hooks/useDataPolling.ts` | Data fetch interval logic (fast/slow ETag polling, currently inline in page.tsx) |
| `frontend/src/hooks/useGeocoding.ts` | LocateBar geocoding logic (Nominatim reverse geocoding on mouse move, currently inline in page.tsx) |

**Scope**:
1. Create `DashboardContext` wrapping the 19+ state variables.
2. Move the `LocateBar` inline component (defined inside page.tsx at ~line 26) into its own file.
3. Replace prop drilling to 9 child components with context consumption.
4. `page.tsx` becomes a thin layout shell under 150 LOC.

**Verification**: `wc -l frontend/src/app/page.tsx` is under 150. All panels still receive their data. No prop names in JSX return that were previously drilled.

---

## Phase 3: Backend Architecture — God Module Decomposition

**Goal**: Break `data_fetcher.py` (2,417 LOC) into per-source modules with proper error handling and bounded caches.

**Dependency**: Task 3.1 depends on Task 1.1 (thread safety fixes first). Tasks 3.2-3.4 can start after 3.1 or independently.

---

### Task 3.1: Split data_fetcher.py into per-source fetcher modules

- [ ] **Complete**

| Field | Value |
|-------|-------|
| **Effort** | L (6-12h) |
| **Priority** | P1 |
| **Dependencies** | Task 1.1 (lock pattern must be correct before splitting) |

**Source**: `backend/services/data_fetcher.py` (2,417 LOC)

**New directory structure**:
```
backend/services/fetchers/
  __init__.py              # Re-exports for backward compat
  store.py                 # latest_data, _data_lock, source_timestamps, get_latest_data()
  scheduler.py             # start_scheduler(), stop_scheduler(), APScheduler wiring
  flights.py               # OpenSky client, ADS-B fetch, route lookup, military classification, POTUS fleet
  ships.py                 # AIS data processing, vessel categorization
  satellites.py            # TLE parsing, SGP4 propagation
  news.py                  # RSS feeds, risk scoring, clustering
  markets.py               # yfinance stocks, oil prices
  weather.py               # RainViewer, space weather (NOAA SWPC)
  infrastructure.py        # CCTV, KiwiSDR, internet outages (IODA), data centers
  geospatial.py            # Earthquakes (USGS), FIRMS fires, GPS jamming
```

**Scope**:
1. Each fetcher module exports a `fetch_*()` function.
2. `store.py` holds `latest_data`, `_data_lock`, `source_timestamps`, and `get_latest_data()`.
3. `scheduler.py` imports all fetchers and wires them to APScheduler jobs.
4. The original `data_fetcher.py` becomes a thin re-export shim so `main.py` imports remain unchanged:
   ```python
   from .fetchers.scheduler import start_scheduler, stop_scheduler
   from .fetchers.store import get_latest_data, latest_data
   ```

**Verification**:
```bash
wc -l backend/services/data_fetcher.py  # Should be under 50 (shim only)
python -c "from services.data_fetcher import start_scheduler, stop_scheduler, get_latest_data"  # Must succeed
# Start backend and confirm data flows through all endpoints
```

---

### Task 3.2: Add TTL and max-size bounds to all caches

- [ ] **Complete**

| Field | Value |
|-------|-------|
| **Effort** | S (1-3h) |
| **Priority** | P1 |
| **Dependencies** | Task 3.1 (cleaner after split, but can be done before) |

**Files**: `backend/services/data_fetcher.py` (or the new fetcher modules after 3.1)

**Problem caches**:
- `_region_geocode_cache` (~line 1600): unbounded dict, no TTL, grows forever
- `dynamic_routes_cache` (~line 644): has manual pruning but should use `cachetools`

**Scope**: Replace unbounded dicts with `cachetools.TTLCache`:
```python
from cachetools import TTLCache
_region_geocode_cache = TTLCache(maxsize=2000, ttl=86400)   # 24h
dynamic_routes_cache = TTLCache(maxsize=5000, ttl=7200)     # 2h
```
`cachetools` is already in `requirements.txt`.

**Verification**: After running for 1 hour, `len(cache)` stays bounded.

---

### Task 3.3: Replace bare Exception catches with specific types and structured logging

- [ ] **Complete**

| Field | Value |
|-------|-------|
| **Effort** | S (1-3h) |
| **Priority** | P2 |
| **Dependencies** | Task 1.2, Task 3.1 |

**Files**: All `backend/services/*.py`

**Scope**:
1. Replace `except Exception as e: logger.error(...)` with specific exceptions where possible: `requests.RequestException`, `json.JSONDecodeError`, `ValueError`, `KeyError`.
2. Add structured context to log messages: data source name, URL, HTTP status code.
3. Ensure zero `except Exception: pass` patterns remain.

**Verification**:
```bash
grep -rn "except Exception: pass" backend/  # Must return 0
grep -rn "except:" backend/ --include="*.py" | grep -v "except Exception" | grep -v "except ("  # Must return 0
```

---

### Task 3.4: Pin all Python dependencies and audit fragile ones

- [ ] **Complete**

| Field | Value |
|-------|-------|
| **Effort** | S (1-3h) |
| **Priority** | P2 |
| **Dependencies** | None |

**File**: `backend/requirements.txt`

**Scope**:
1. Pin all dependencies to exact versions (run `pip freeze` from working venv).
2. Evaluate `cloudscraper` — if only used in one fetcher, document clearly or consider removal.
3. Evaluate `playwright` — if only used by `liveuamap_scraper.py`, document and consider making it optional (it pulls ~150MB of browsers).
4. Create `backend/requirements-dev.txt` for test dependencies: `pytest`, `httpx`, `pytest-asyncio`.

**Verification**:
```bash
pip install -r requirements.txt  # In fresh venv, must succeed deterministically
pip check                         # Must report no conflicts
```

---

## Phase 4: Testing Infrastructure

**Goal**: Go from zero automated tests to a meaningful suite that catches regressions.

**Dependency**: Task 4.2 depends on Phase 2 (extracted hooks are what make frontend testing feasible). Task 4.3 depends on 4.1 and 4.2.

---

### Task 4.1: Set up pytest for backend and write smoke tests

- [ ] **Complete**

| Field | Value |
|-------|-------|
| **Effort** | M (3-6h) |
| **Priority** | P1 |
| **Dependencies** | None (but benefits from Task 3.1) |

**New files**:
- `backend/tests/__init__.py`
- `backend/tests/conftest.py` — FastAPI test client fixture using `httpx.AsyncClient`
- `backend/tests/test_api_smoke.py` — smoke tests for every endpoint in `main.py`
- `backend/pytest.ini` or `pyproject.toml` pytest section
- `backend/requirements-dev.txt` — `pytest`, `httpx`, `pytest-asyncio`

**Scope**:
1. Create proper test infrastructure with fixtures.
2. Write smoke tests: assert 200 status, valid JSON, expected top-level keys for every endpoint.
3. Archive or delete the 26 manual `test_*.py` files (move to `backend/tests/_archived/` if keeping for reference).

**Verification**:
```bash
cd backend && pip install -r requirements-dev.txt && pytest tests/ -v
# At least 10 tests green
```

---

### Task 4.2: Set up Vitest for frontend and write component tests

- [ ] **Complete**

| Field | Value |
|-------|-------|
| **Effort** | M (3-6h) |
| **Priority** | P2 |
| **Dependencies** | Phase 2 (extracted hooks/utils are what make testing feasible) |

**New files**:
- `frontend/vitest.config.ts`
- `frontend/src/__tests__/` directory
- Tests for: utility functions (aircraftClassification, positioning), ErrorBoundary, FilterPanel, MarketsPanel

**Scope**:
1. Install `vitest`, `@testing-library/react`, `@testing-library/jest-dom`, `jsdom` as devDeps.
2. Add `"test": "vitest run"` script to `package.json`.
3. Write tests for pure utility functions first (from Phase 2 extractions).
4. Write render tests for at least 3 components.
5. Do NOT test MaplibreViewer directly (needs GL context mock).

**Verification**:
```bash
cd frontend && npx vitest run  # At least 8 tests green
```

---

### Task 4.3: Add test steps to CI pipeline

- [ ] **Complete**

| Field | Value |
|-------|-------|
| **Effort** | S (1-3h) |
| **Priority** | P1 |
| **Dependencies** | Tasks 4.1, 4.2 |

**File**: `.github/workflows/docker-publish.yml`

**Scope**:
1. Add a `test` job that runs before build jobs.
2. Backend: `pip install -r requirements.txt -r requirements-dev.txt && pytest tests/ -v`
3. Frontend: `npm ci && npm run lint && npm run build && npx vitest run`
4. Make `build-frontend` and `build-backend` depend on `test` job.

**Verification**: Push a branch with a failing test → CI fails and blocks Docker build.

---

## Phase 5: DevOps Hardening

**Goal**: Production-grade container config, proper `.dockerignore`, health checks, graceful shutdown.

**All Phase 5 tasks are independent and can be executed in parallel.**

---

### Task 5.1: Add Docker health checks and resource limits

- [ ] **Complete**

| Field | Value |
|-------|-------|
| **Effort** | S (1-3h) |
| **Priority** | P2 |
| **Dependencies** | None |

**File**: `docker-compose.yml`

**Scope**:
1. Backend healthcheck: `test: ["CMD", "curl", "-f", "http://localhost:8000/api/live-data/fast"]`, interval 30s, timeout 10s, retries 3, start_period 15s.
2. Frontend healthcheck: `test: ["CMD", "curl", "-f", "http://localhost:3000/"]`, interval 30s, timeout 10s, retries 3, start_period 20s.
3. Resource limits: backend 2GB memory / 2 CPUs, frontend 512MB memory / 1 CPU.
4. Frontend `depends_on: backend: condition: service_healthy`.

**Verification**:
```bash
docker compose up -d
docker ps  # Shows health status column
# Kill backend process inside container, confirm Docker restarts it
```

---

### Task 5.2: Create .dockerignore and fix backend Dockerfile

- [ ] **Complete**

| Field | Value |
|-------|-------|
| **Effort** | XS (30min) |
| **Priority** | P2 |
| **Dependencies** | None |

**Files**:
- New: `backend/.dockerignore` — exclude `test_*.py`, `*.json` (except `package*.json`, `news_feeds.json`), `*.html`, `*.xlsx`, debug outputs
- New: `.dockerignore` (root) — exclude `node_modules`, `.next`, `venv`, `.git`, `*.db`, `*.xlsx`, debug JSONs
- Modify: `backend/Dockerfile` — change `npm install` to `npm ci` (~line 19)

**Verification**:
```bash
docker build ./backend  # Image under 500MB
docker run --rm <image> ls /app/  # No debug files visible
```

---

### Task 5.3: Add signal trapping for graceful shutdown in start scripts

- [ ] **Complete**

| Field | Value |
|-------|-------|
| **Effort** | XS (30min) |
| **Priority** | P2 |
| **Dependencies** | None |

**Files**:
- `start.sh` — add `trap 'kill 0' EXIT SIGINT SIGTERM` near the top
- `start.bat` — add error checking after `call npm run dev`

**Verification**: Start app → Ctrl+C → confirm no orphan node/python processes remain (`ps aux | grep -E "node|python"` on Unix, Task Manager on Windows).

---

### Task 5.4: Clean root directory clutter and update .gitignore

- [ ] **Complete**

| Field | Value |
|-------|-------|
| **Effort** | XS (30min) |
| **Priority** | P3 |
| **Dependencies** | None |

**Files**: `.gitignore` + root directory

**Scope**:
1. Run `git rm --cached` on any tracked files that should be ignored: `TheAirTraffic Database.xlsx`, `zip_repo.py`, etc.
2. Add missing patterns to `.gitignore`: `*.swp`, `*.swo`, `coverage/`, `.coverage`, `dist/`, `build/`, `*.tar.gz`
3. Confirm all backend debug files (`tmp_fast.json`, `dump.json`, `debug_fast.json`, `merged.txt`) are gitignored.

**Verification**:
```bash
git status   # No large untracked files
git ls-files | xargs wc -c | sort -rn | head -20  # No file over 500KB tracked
```

---

### Task 5.5: Document Docker secrets configuration

- [ ] **Complete**

| Field | Value |
|-------|-------|
| **Effort** | XS (30min) |
| **Priority** | P3 |
| **Dependencies** | None |

**File**: `README.md`

**Scope**: Add a section documenting the Docker Swarm secrets support already implemented in `main.py` (lines 8-36). The `_SECRET_VARS` list supports `_FILE` suffix convention for: `AIS_API_KEY`, `OPENSKY_CLIENT_ID`, `OPENSKY_CLIENT_SECRET`, `LTA_ACCOUNT_KEY`, `CORS_ORIGINS`. Include a `docker-compose.yml` secrets example.

**Verification**: The README section exists and matches the `_SECRET_VARS` list in `main.py`.

---

## Phase 6: Long-term Quality & Accessibility

**Goal**: Address code quality, accessibility, and developer experience improvements that compound over time.

**Dependencies**: 6.1 depends on Phase 2. Others are independent.

---

### Task 6.1: Replace inline styles with Tailwind classes

- [ ] **Complete**

| Field | Value |
|-------|-------|
| **Effort** | L (6-12h) |
| **Priority** | P3 |
| **Dependencies** | Phase 2 (much easier after component decomposition) |

**Files**: All components in `frontend/src/components/`

**Scope**:
1. Audit all `style={{...}}` occurrences. Heaviest offenders: MaplibreViewer.tsx, NewsFeed.tsx, FilterPanel.tsx.
2. Convert inline styles to Tailwind utility classes.
3. For dynamic values (e.g., `style={{ left: x + 'px' }}`), keep as inline but extract repeated patterns to `globals.css`:
   ```css
   .marker-label { @apply text-xs font-mono font-bold text-white pointer-events-none; text-shadow: 0 0 3px #000; }
   .carrier-label { @apply text-xs font-mono font-bold text-amber-400 pointer-events-none; text-shadow: 0 0 3px #000; }
   ```
4. CSS variables (`var(--...)`) can stay as-is for theme integration.

**Verification**:
```bash
grep -rn "style={{" frontend/src/components/ | wc -l  # Count should decrease by 70%+
npm run build  # Must succeed
```

---

### Task 6.2: Add error boundaries to all child panels

- [ ] **Complete**

| Field | Value |
|-------|-------|
| **Effort** | S (1-3h) |
| **Priority** | P2 |
| **Dependencies** | None (but cleaner after Task 2.5) |

**Files**:
- `frontend/src/components/ErrorBoundary.tsx` (already exists, reuse it)
- `frontend/src/app/page.tsx` (or post-refactor layout component)

**Scope**: Wrap every child panel with `<ErrorBoundary name="PanelName">`:
- FilterPanel, NewsFeed, RadioInterceptPanel, MarketsPanel
- WorldviewLeftPanel, WorldviewRightPanel
- SettingsPanel, MapLegend

**Verification**: Add `throw new Error("test")` to MarketsPanel render → confirm error boundary catches it, other panels remain functional. Remove the throw after testing.

---

### Task 6.3: Add basic accessibility (ARIA labels, keyboard navigation)

- [ ] **Complete**

| Field | Value |
|-------|-------|
| **Effort** | M (3-6h) |
| **Priority** | P3 |
| **Dependencies** | None (easier after Phase 2) |

**Files**: All components in `frontend/src/components/`

**Scope**:
1. `aria-label` on all buttons, toggles, inputs.
2. `role` attributes on panel containers (`role="complementary"`, `role="navigation"`).
3. `aria-pressed` on toggle buttons, `aria-expanded` on collapsible panels.
4. Keyboard handlers: Escape to close modals/panels, Enter to confirm.
5. `tabIndex` on custom interactive elements.
6. Focus management: modal open → focus modal, close → focus trigger.

**Verification**: Run Axe accessibility browser extension on running dashboard → zero critical violations. Tab through UI → all interactive elements reachable.

---

### Task 6.4: Add image scanning and SBOM generation to CI

- [ ] **Complete**

| Field | Value |
|-------|-------|
| **Effort** | S (1-3h) |
| **Priority** | P3 |
| **Dependencies** | Task 4.3 |

**File**: `.github/workflows/docker-publish.yml`

**Scope**:
1. Add Trivy scan step after Docker build: `uses: aquasecurity/trivy-action@master` with `severity: CRITICAL,HIGH`.
2. Add SBOM generation using `anchore/sbom-action`, upload as build artifact.
3. PRs: scan but don't fail. Pushes to main: scan and fail on critical.

**Verification**: CI shows Trivy results in PR checks. Image with known CVE fails the build.

---

## Dependency Graph

```
PHASE 1 (all parallel)
  1.1  1.2  1.3  1.4  1.5  1.6
   |
   v
PHASE 2:  2.1 + 2.2 (parallel) ──> 2.3 ──> 2.4 ──> 2.5
   |
PHASE 3:  3.1 (needs 1.1) ──> 3.2 + 3.3 (parallel)
          3.4 (independent)
   |
PHASE 4:  4.1 (independent)  +  4.2 (needs Phase 2) ──> 4.3
   |
PHASE 5 (all parallel)
  5.1  5.2  5.3  5.4  5.5
   |
PHASE 6:  6.1 (needs Phase 2)  6.2  6.3  6.4 (needs 4.3)
```

---

## Effort Summary

| Size | Count | Hours Each | Total Hours |
|------|-------|-----------|-------------|
| XS | 6 | 0.5-1h | 3-6h |
| S | 10 | 1-3h | 10-30h |
| M | 5 | 3-6h | 15-30h |
| L | 2 | 6-12h | 12-24h |
| **Total** | **23 tasks** | | **~40-90h** |

---

## Target Scores (Post-Roadmap)

| Category | Before | After | Delta |
|----------|--------|-------|-------|
| Thread Safety | 3/10 | 9/10 | +6 |
| Type Safety | 2/10 | 8/10 | +6 |
| Testing | 0/10 | 7/10 | +7 |
| Error Handling | 4/10 | 8/10 | +4 |
| Architecture | 3/10 | 8/10 | +5 |
| DevOps | 5/10 | 9/10 | +4 |
| Security | 4/10 | 7/10 | +3 |
| Accessibility | 1/10 | 6/10 | +5 |
| **Overall** | **3.5/10** | **8/10** | **+4.5** |
