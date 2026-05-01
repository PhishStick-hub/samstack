---
phase: 03
slug: sub-container-cascade-verification
status: verified
threats_open: 0
asvs_level: 1
created: 2026-04-25
---

# Phase 3 — Security

> Per-phase security contract: threat register, accepted risks, and audit trail.

---

## Trust Boundaries

| Boundary | Description | Data Crossing |
|----------|-------------|---------------|
| Docker daemon socket | Test code uses `docker.from_env()` → `/var/run/docker.sock`. Container listing and network queries cross this boundary. | Container names, statuses (non-sensitive metadata) |
| Subprocess boundary | `subprocess.Popen` launches child pytest session. Parent sends SIGKILL via `os.kill()` and reads exit code independently. Socket inherited by child. | No data crossing (DEVNULL for stdout/stderr) |
| Filesystem (generated) | Generated conftest and test files written to `tmp_path` with embedded absolute paths. | Project-local paths only |

---

## Threat Register

| Threat ID | Category | Component | Disposition | Mitigation | Status |
|-----------|----------|-----------|-------------|------------|--------|
| T-03-01 | Tampering | `_write_subprocess_session` — generated conftest/test in tmp_path | accept | Files written by test itself to temp directory. No external input crosses this boundary. | closed |
| T-03-02 | Information Disclosure | Docker socket via `docker.from_env()` in test code | accept | Container metadata (names, statuses) is not sensitive. No credentials or secrets read. | closed |
| T-03-03 | Denial of Service | Subprocess SIGKILL via `os.kill(pid, SIGKILL)` | accept | Subprocess launched by test itself in isolated `tmp_path`. SIGKILL only affects child process. | closed |
| T-03-04 | Elevation of Privilege | Subprocess Docker socket inheritance | accept | Child pytest session uses same Docker socket as parent — by design (DinD path). No privilege boundary crossed. | closed |
| T-03-05 | Tampering | `_write_teardown_session` — generated conftest/test in tmp_path | accept | Same as T-03-01. `fixture_dir` computed as project-relative `Path.cwd() / ...`, not user-controlled. | closed |
| T-03-06 | Information Disclosure | Docker container metadata via `containers.list()` | accept | Same as T-03-02. Container names/statuses are non-sensitive. | closed |
| T-03-07 | Denial of Service | Subprocess launch + Docker image pull | accept | Subprocess bounded by 300s `proc.wait` timeout and 180s pytest `--timeout`. Image pull is one-time cached cost. | closed |
| T-03-08 | Elevation of Privilege | Subprocess Docker socket inheritance (teardown test) | accept | Same as T-03-04. Socket access by design — Docker-in-Docker for SAM CLI. | closed |

*Status: 8 closed, 0 open*
*Disposition: All 8 threats accepted with documented rationale in PLAN.md threat registers*

---

## Accepted Risks Log

| Risk ID | Threat Ref | Rationale | Accepted By | Date |
|---------|------------|-----------|-------------|------|
| R-03-01 | T-03-01, T-03-05 | Test-generated files in tmp_path — no external input, self-contained test logic | GSD secure-phase | 2026-04-25 |
| R-03-02 | T-03-02, T-03-06 | Docker metadata queries return non-sensitive container names/statuses — no credentials or env vars exposed | GSD secure-phase | 2026-04-25 |
| R-03-03 | T-03-03, T-03-07 | Subprocess lifecycle bounded by timeouts; SIGKILL only affects own child process. Image pull is cached. | GSD secure-phase | 2026-04-25 |
| R-03-04 | T-03-04, T-03-08 | Docker socket inheritance is by design — SAM CLI requires DinD for Lambda container creation | GSD secure-phase | 2026-04-25 |

---

## Security Audit Trail

| Audit Date | Threats Total | Closed | Open | Run By |
|------------|---------------|--------|------|--------|
| 2026-04-25 | 8 | 8 | 0 | gsd-security-auditor (inline) |

---

## Sign-Off

- [x] All threats have a disposition (mitigate / accept / transfer)
- [x] Accepted risks documented in Accepted Risks Log
- [x] `threats_open: 0` confirmed
- [x] `status: verified` set in frontmatter

**Approval:** verified 2026-04-25
