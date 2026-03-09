# Clausy Docker noVNC Visible Browser Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Add an optional noVNC web UI to Docker mode so users can see/control the in-container browser from localhost, while keeping Clausy API on host `3108` (container `5000`) and preserving current `docker-start` behavior by default.

**Architecture:** Keep current startup precedence and CDP behavior intact, and add a gated noVNC sidecar path inside the same container (`Xvfb + openbox + x11vnc + noVNC`). The feature is opt-in via env flags so existing Docker users are not impacted unless enabled. Enforce localhost-only exposure at publish-time (`127.0.0.1:6080:6080`) and document explicit security warning (no auth initially).

**Tech Stack:** Dockerfile (Debian slim), shell runtime (`scripts/docker-start.sh`), Xvfb/openbox, `x11vnc`, noVNC (`/usr/share/novnc/utils/novnc_proxy`), pytest (runtime script tests), curl/docker CLI smoke checks.

---

### Task 1: Add noVNC runtime dependencies to image (no behavior change yet)

**Files:**
- Modify: `Dockerfile`
- Test: `docker build -t clausy:novnc-plan-smoke .`

**Step 1: Write/adjust failing verification (build expectation)**

Add/update a Docker smoke test script command in plan execution notes to verify the image has noVNC components:

```bash
docker run --rm clausy:novnc-plan-smoke sh -lc 'command -v x11vnc && test -x /usr/share/novnc/utils/novnc_proxy'
```

**Step 2: Run verification before implementation (expect fail)**

Run:

```bash
docker build -t clausy:novnc-plan-smoke .
docker run --rm clausy:novnc-plan-smoke sh -lc 'command -v x11vnc && test -x /usr/share/novnc/utils/novnc_proxy'
```

Expected: second command fails because `x11vnc`/noVNC are not yet installed.

**Step 3: Minimal implementation**

Update `Dockerfile` apt package install list to include:
- `x11vnc`
- `novnc`
- `websockify` (if required by distro package split)

Keep existing packages and startup command unchanged.

**Step 4: Re-run verification (expect pass)**

Run:

```bash
docker build -t clausy:novnc-plan-smoke .
docker run --rm clausy:novnc-plan-smoke sh -lc 'command -v x11vnc && test -x /usr/share/novnc/utils/novnc_proxy'
```

Expected: pass.

**Step 5: Commit**

```bash
git add Dockerfile
git commit -m "feat(docker): add x11vnc and noVNC runtime dependencies"
```

---

### Task 2: Extend `docker-start` with optional noVNC process startup

**Files:**
- Modify: `scripts/docker-start.sh`
- Test: `tests/test_docker_start.py`

**Step 1: Write failing tests**

Add tests in `tests/test_docker_start.py` for dry-run mode (`CLAUSY_DOCKER_START_DRY_RUN=1`):

1. `test_docker_start_novnc_disabled_by_default()`
   - env does **not** set `CLAUSY_ENABLE_NOVNC`
   - assert output does not include `x11vnc`/`noVNC` startup logs.

2. `test_docker_start_novnc_enabled_emits_startup_commands()`
   - env sets:
     - `CLAUSY_ENABLE_NOVNC=1`
     - `CLAUSY_NOVNC_PORT=6080`
     - `CLAUSY_VNC_PORT=5900`
   - assert output includes deterministic log lines indicating:
     - x11vnc binds against current `DISPLAY`
     - noVNC proxy command maps `6080 -> 127.0.0.1:5900`

3. `test_docker_start_novnc_invalid_port_falls_back_to_default()`
   - env `CLAUSY_NOVNC_PORT=not-a-number`
   - assert default `6080` is used/logged.

**Step 2: Run targeted tests (expect fail)**

Run:

```bash
python -m pytest tests/test_docker_start.py -q
```

Expected: new noVNC tests fail.

**Step 3: Minimal implementation in `scripts/docker-start.sh`**

Add opt-in noVNC block that runs only when enabled:

- New env vars (with safe defaults):
  - `CLAUSY_ENABLE_NOVNC` default `0`
  - `CLAUSY_VNC_PORT` default `5900`
  - `CLAUSY_NOVNC_PORT` default `6080`
- Startup behavior:
  1. Keep existing `Xvfb` + `openbox` startup unchanged.
  2. If noVNC enabled:
     - start `x11vnc` against `$DISPLAY`, no password (`-nopw`), persistent (`-forever`), shared (`-shared`), local bind (`-localhost`) on VNC port.
     - start noVNC proxy (`/usr/share/novnc/utils/novnc_proxy --vnc 127.0.0.1:${CLAUSY_VNC_PORT} --listen ${CLAUSY_NOVNC_PORT}`)
     - log explicit warning: noVNC has no auth and must be exposed localhost-only.
- Keep all current host-CDP/local-fallback logic and final `exec python -m clausy` unchanged.

**Step 4: Re-run tests (expect pass)**

Run:

```bash
python -m pytest tests/test_docker_start.py -q
```

Expected: pass including new noVNC coverage.

**Step 5: Commit**

```bash
git add scripts/docker-start.sh tests/test_docker_start.py
git commit -m "feat(docker): add optional noVNC startup path in docker-start"
```

---

### Task 3: Publish localhost-only noVNC port in Docker assets

**Files:**
- Modify: `docker-compose.yml`
- Modify: `README.md` (Docker section)
- Optional modify: `.env.example` (new noVNC env vars)

**Step 1: Write failing checks**

Create/extend assertions (shell or doc-lint style in CI task) that expected localhost mappings appear:

```bash
grep -n "127.0.0.1:3108:5000" docker-compose.yml
grep -n "127.0.0.1:6080:6080" docker-compose.yml
grep -n "no auth.*localhost" README.md
```

Expected pre-change: missing at least noVNC mapping/warning.

**Step 2: Update compose and docs**

1. `docker-compose.yml`
   - Keep Clausy API published to host `3108`:
     - `127.0.0.1:3108:5000`
   - Add noVNC publish:
     - `127.0.0.1:6080:6080`
   - Add env defaults:
     - `CLAUSY_ENABLE_NOVNC: "1"` (for compose UX) or keep `0` and document override (pick one and document clearly)
     - `CLAUSY_NOVNC_PORT: "6080"`
     - `CLAUSY_VNC_PORT: "5900"`

2. `README.md`
   - Add one-liner run command exposing both ports:

```bash
docker build -t clausy . && docker run --rm \
  -p 127.0.0.1:3108:5000 \
  -p 127.0.0.1:6080:6080 \
  -e CLAUSY_BIND=0.0.0.0 \
  -e CLAUSY_PORT=5000 \
  -e CLAUSY_ENABLE_NOVNC=1 \
  -e CLAUSY_NOVNC_PORT=6080 \
  -e CLAUSY_VNC_PORT=5900 \
  -v "$(pwd)/profile:/app/profile" \
  clausy
```

   - Document access URL: `http://127.0.0.1:6080/vnc.html`
   - Add warning: noVNC currently has no auth; localhost-only publishing is required.

3. `.env.example` (recommended)
   - Add commented noVNC env vars with defaults and warning note.

**Step 3: Re-run checks**

Run:

```bash
grep -n "127.0.0.1:3108:5000" docker-compose.yml
grep -n "127.0.0.1:6080:6080" docker-compose.yml
grep -n "http://127.0.0.1:6080/vnc.html" README.md
grep -n "no auth" README.md
```

Expected: all checks return matches.

**Step 4: Commit**

```bash
git add docker-compose.yml README.md .env.example
git commit -m "docs(docker): document localhost-only noVNC run and ports"
```

---

### Task 4: Add practical smoke checks for API + noVNC reachability

**Files:**
- Create: `scripts/smoke/docker-novnc-smoke.sh`
- Modify: `README.md` (reference smoke script)
- Optional CI: `.github/workflows/ci.yml` (manual/optional job)

**Step 1: Add failing smoke command expectations**

Define smoke acceptance commands:

```bash
curl -fsS http://127.0.0.1:3108/health
curl -fsS http://127.0.0.1:6080/vnc.html | grep -qi novnc
```

Expected pre-script: manual flow only, no reusable smoke script.

**Step 2: Implement script**

Create `scripts/smoke/docker-novnc-smoke.sh` to:
1. build image (`clausy:novnc-smoke`)
2. run container detached with localhost-only mappings for 3108/6080
3. wait/retry health endpoints (bounded retries)
4. verify:
   - API health endpoint returns success
   - noVNC page returns HTML containing `noVNC`
5. print logs on failure
6. clean up container on exit (`trap`).

**Step 3: Execute smoke script**

Run:

```bash
bash scripts/smoke/docker-novnc-smoke.sh
```

Expected: pass locally when Docker daemon is available.

**Step 4: Commit**

```bash
git add scripts/smoke/docker-novnc-smoke.sh README.md .github/workflows/ci.yml
git commit -m "test(docker): add API+noVNC smoke verification"
```

(If CI change is omitted, remove `.github/workflows/ci.yml` from `git add`.)

---

### Task 5: Final verification and release notes

**Files:**
- Modify: `README.md` (final consistency pass)
- Modify: `docs/runbook-browser-runtime.md` (add noVNC operational troubleshooting)

**Step 1: Full verification run**

Run:

```bash
python -m pytest -q
bash scripts/smoke/docker-novnc-smoke.sh
```

Expected: tests pass; smoke passes (or clearly documented daemon limitation if unavailable in local environment).

**Step 2: Sanity runtime check (manual)**

Run final one-liner from README and confirm:

```bash
curl -s http://127.0.0.1:3108/health | jq
open http://127.0.0.1:6080/vnc.html
```

Expected:
- API healthy at host `3108`
- noVNC UI opens and shows X display/browser session.

**Step 3: Commit**

```bash
git add README.md docs/runbook-browser-runtime.md
git commit -m "docs(runbook): add noVNC localhost-only guidance and troubleshooting"
```

---

## Notes / Guardrails

- Preserve existing default runtime behavior: noVNC disabled unless explicitly enabled (or enabled only in compose if intentionally chosen and documented).
- Keep `scripts/docker-start.sh` precedence (`host-launch -> probe -> local fallback`) untouched.
- Do not add auth in this milestone; explicitly warn that unauthenticated noVNC must remain localhost-only.
- Keep OpenClaw-facing Clausy base URL behavior unchanged (`http://127.0.0.1:3108/v1`).

## Suggested PR Checklist

- [x] Docker image includes `x11vnc` + noVNC tooling
- [x] `docker-start` can start noVNC stack when enabled
- [x] Host API remains on `127.0.0.1:3108`
- [x] noVNC published only on `127.0.0.1:6080`
- [x] README includes one-liner with both ports and security warning
- [ ] Tests/smoke checks added and passing *(blocked in this environment: Docker daemon socket access denied)*

## Evidence Update (2026-03-09)

Commands run:

```bash
scripts/release-gate.sh
bash scripts/smoke/docker-novnc-smoke.sh
```

Results:
- `scripts/release-gate.sh`: **PASS**
  - Full suite: `297 passed, 8 subtests passed`
  - Targeted routing/provider regressions: `56 passed`
  - Installer smoke + package build completed successfully.
- `bash scripts/smoke/docker-novnc-smoke.sh`: **FAIL (environmental blocker)**
  - Build step reached Docker but failed with:
  - `permission denied while trying to connect to the docker API at unix:///var/run/docker.sock`

Conclusion:
- Milestone verification is complete except for local Docker noVNC smoke execution, which is explicitly blocked by host Docker daemon permissions in this session.
