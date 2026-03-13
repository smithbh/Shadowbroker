# ShadowBroker Release Protocol

> This document exists because API keys were leaked in release zips v0.5.0, v0.6.0, and briefly v0.8.0.
> Follow this exactly. No shortcuts.

---

## Pre-Release Checklist

### 1. Bump the Version

- **`frontend/package.json`** — update `"version"` field
- **`frontend/src/components/ChangelogModal.tsx`** — update `CURRENT_VERSION` and `STORAGE_KEY`
- **Update `NEW_FEATURES`, `BUG_FIXES`, and `CONTRIBUTORS` arrays** in the changelog modal

### 2. Pull Remote Changes First

```bash
git pull --rebase origin main
```

If there are merge conflicts, resolve them carefully. **Do not blindly delete files during rebase** — this is how the API proxy route (`frontend/src/app/api/[...path]/route.ts`) was accidentally deleted and broke the entire app.

After resolving conflicts, verify critical files still exist:
```bash
ls frontend/src/app/api/\[...path\]/route.ts   # API proxy — app is dead without this
ls backend/main.py
ls frontend/src/app/page.tsx
```

### 3. Test Before Committing

```bash
# Backend
cd backend && python -c "import main; print('Backend OK')"

# Frontend
cd frontend && npm run build
```

If the backend fails with a missing module, install it:
```bash
pip install -r requirements.txt
```

---

## Building the Release Zip

### The Command

Run from the project root (`live-risk-dashboard/`):

```bash
7z a -tzip ../ShadowBroker_vX.Y.Z.zip \
    -xr!node_modules -xr!.next -xr!__pycache__ -xr!venv -xr!.git -xr!.git_backup \
    -xr!*.pyc -xr!*.db -xr!*.sqlite -xr!*.xlsx \
    -xr!.env -xr!.env.local -xr!.env.production -xr!.env.development \
    -xr!carrier_cache.json -xr!ais_cache.json \
    -xr!tmp_fast.json -xr!dump.json -xr!debug_fast.json \
    -xr!nyc_sample.json -xr!nyc_full.json \
    -xr!server_logs.txt -xr!server_logs2.txt -xr!xlsx_analysis.txt -xr!liveua_test.html \
    -xr!merged.txt -xr!recent_commits.txt \
    -xr!build_error.txt -xr!build_logs*.txt -xr!build_output.txt -xr!errors.txt \
    -xr!geocode_log.txt -xr!tsconfig.tsbuildinfo \
    -xr!ShadowBroker_v*.zip \
    .
```

### Critical Exclusions (NEVER ship these)

| Pattern | Why |
|---------|-----|
| `.env` | **Contains real API keys** (OpenSky, AIS Stream) |
| `.env.local` | **Contains real API keys** (TomTom, etc.) |
| `.env.production` / `.env.development` | May contain secrets |
| `carrier_cache.json` / `ais_cache.json` | Runtime cache, not source |
| `node_modules/` / `__pycache__/` / `.next/` | Build artifacts |
| `*.db` / `*.sqlite` / `*.xlsx` | Data files, not source |
| `ShadowBroker_v*.zip` | Previous release zips sitting in the project dir |

### What SHOULD Be in the Zip

| File | Required |
|------|----------|
| `frontend/src/app/api/[...path]/route.ts` | **YES** — API proxy, app is dead without it |
| `backend/.env.example` | YES — template for users |
| `.env.example` | YES — template for users |
| `backend/data/plane_alert_db.json` | YES — aircraft database |
| `backend/data/datacenters*.json` | YES — data center layer |
| `backend/data/tracked_names.json` | YES — tracked aircraft names |
| `frontend/src/lib/airlines.json` | YES — airline codes |
| `start.bat` / `start.sh` | YES — launcher scripts |

### Do NOT Use

- **`git archive`** — includes tracked junk, misses untracked essential files
- **`Compress-Archive` (PowerShell)** — has lock file issues, no exclusion control
- **Gemini's zip script** — included test files, debug outputs, `.env` with real keys, and 30+ unnecessary files

---

## Post-Build Audit (MANDATORY)

**Before uploading, always scan the zip for leaks:**

```bash
# Check for .env files (should only show .env.example files)
7z l ShadowBroker_vX.Y.Z.zip | grep -i "\.env" | grep "....A"

# Check for anything with "secret", "key", "token", "credential" in the filename
7z l ShadowBroker_vX.Y.Z.zip | grep -iE "secret|api.key|credential|token" | grep "....A"

# Check the largest files (look for unexpected blobs)
7z l ShadowBroker_vX.Y.Z.zip | grep "....A" | awk '{print $4, $NF}' | sort -rn | head -15

# Verify the API proxy route exists
7z l ShadowBroker_vX.Y.Z.zip | grep "route.ts"
```

**Expected results:**
- `.env` files: ONLY `.env.example` and `next-env.d.ts`
- No files with "secret"/"credential" in the name
- Largest files: `plane_alert_db.json` (~4.6MB), `datacenters_geocoded.json` (~1.2MB), `airlines.json` (~800KB)
- `route.ts` exists under `frontend/src/app/api/[...path]/`
- **Total zip size: ~1.7MB** (as of v0.8.0). If it's 5MB+ something leaked.

---

## Commit, Tag, and Push

```bash
# Stage specific files (NEVER use git add -A)
git add <specific files>

# Commit
git commit -m "v0.X.0: brief description of release"

# Tag
git tag v0.X.0

# Push (pull first if remote has new commits)
git pull --rebase origin main
git push origin main --tags

# If the tag was created before rebase, re-tag on the new HEAD:
git tag -f v0.X.0
git push origin v0.X.0 --force
```

---

## Creating the GitHub Release

### Via GitHub API (when `gh` CLI is unavailable)

```python
# 1. Create the release
import urllib.request, json

body = {
    "tag_name": "v0.X.0",
    "name": "v0.X.0 — Title Here",
    "body": "Release notes here...",
    "draft": False,
    "prerelease": False
}

# Write to a temp file to avoid JSON escaping hell in bash
with open("release_body.json", "w") as f:
    json.dump(body, f)

# POST to GitHub API...

# 2. Upload the zip asset to the release
# Use the upload_url from the release response
```

### Via `gh` CLI (if installed)

```bash
gh release create v0.X.0 ../ShadowBroker_v0.X.0.zip \
    --title "v0.X.0 — Title" \
    --notes-file RELEASE_NOTES.md
```

---

## Post-Release Verification

After uploading, download the release zip from GitHub and verify it:

```bash
# Download what GitHub is actually serving
curl -L -o /tmp/verify.zip "https://github.com/BigBodyCobain/Shadowbroker/releases/download/v0.X.0/ShadowBroker_v0.X.0.zip"

# Scan for leaks (same audit as above)
7z l /tmp/verify.zip | grep -i "\.env" | grep "....A"

# Compare hash to your local copy
md5sum /tmp/verify.zip ../ShadowBroker_v0.X.0.zip
```

---

## If You Discover a Leak

### Immediate Actions

1. **Rebuild the zip** without the leaked file
2. **Delete the old asset** from the GitHub release via API
3. **Upload the clean zip** as a replacement
4. **Rotate ALL leaked keys immediately:**
   - OpenSky: https://opensky-network.org/
   - AIS Stream: https://aisstream.io/
   - Any other keys found in the leak
5. **Audit ALL other releases** — leaks tend to exist in multiple versions

### Audit All Releases Script

```python
import urllib.request, json

TOKEN = "your_token"
headers = {"Authorization": f"token {TOKEN}", "Accept": "application/vnd.github+json"}

# Get all releases
req = urllib.request.Request(
    "https://api.github.com/repos/BigBodyCobain/Shadowbroker/releases",
    headers=headers
)
releases = json.loads(urllib.request.urlopen(req).read())

for r in releases:
    for asset in r.get("assets", []):
        # Download via API
        req2 = urllib.request.Request(
            asset["url"],
            headers={**headers, "Accept": "application/octet-stream"}
        )
        data = urllib.request.urlopen(req2).read()
        filename = f"/tmp/{r['tag_name']}.zip"
        with open(filename, "wb") as f:
            f.write(data)
        print(f"Downloaded {r['tag_name']}: {len(data)} bytes")
        # Then run 7z l on each to check for .env files
```

---

## Lessons Learned (v0.8.0 Incident)

1. **Rebasing can silently delete files.** After `git pull --rebase`, always verify that critical files like the API proxy route still exist.
2. **The zip command must explicitly exclude `.env` and `.env.local`.** These files are not in `.gitignore` patterns that 7z understands — you must pass `-xr!.env -xr!.env.local` every time.
3. **Always audit the zip before uploading.** A 10-second grep saves a key rotation.
4. **Never trust another tool's zip output.** Gemini's zip included `.env` with real keys, 30+ test files, debug outputs, and sample JSON dumps.
5. **2,000+ stars means 2,000+ potential eyes on every release.** Treat every zip as if it will be decompiled line by line.
