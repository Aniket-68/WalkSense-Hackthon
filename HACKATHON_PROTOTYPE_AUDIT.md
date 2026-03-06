# WalkSense Hackathon Prototype Audit Report
Date: March 6, 2026  
Branch assessed: `prototype-test`  
Assessor: Codex (repo-based technical audit)

## 1) Executive Summary
WalkSense has strong hackathon potential on impact, architecture, and feature ambition, but it is not yet selection-ready as a stable prototype due to current integration breakpoints in auth and local dev runtime wiring.

Current readiness verdict: **Conditional (Not yet submit-ready)**

Estimated selection score (current state): **63/100**

Estimated selection score after P0 fixes below: **80+/100**

## 2) Assessment Criteria and Scores
| Criterion | Weight | Score | Weighted |
|---|---:|---:|---:|
| Problem relevance and social impact | 15 | 9 | 13.5 |
| Innovation and differentiation | 10 | 8 | 8.0 |
| Technical depth | 15 | 8 | 12.0 |
| End-to-end product flow | 15 | 5 | 7.5 |
| Reliability and robustness | 10 | 4 | 4.0 |
| Security and trust | 10 | 7 | 7.0 |
| Demo readiness | 10 | 4 | 4.0 |
| Deployment and operability | 5 | 6 | 3.0 |
| Testing and CI maturity | 5 | 4 | 2.0 |
| Documentation and pitch clarity | 5 | 4 | 2.0 |
| **Total** | **100** |  | **63.0** |

## 3) Evidence Summary
Reviewed:
- [README.md](/home/bot/repos/WalkSense-Hackthon/README.md)
- [SECURITY_ASSESSMENT.md](/home/bot/repos/WalkSense-Hackthon/SECURITY_ASSESSMENT.md)
- [Backend/API/server.py](/home/bot/repos/WalkSense-Hackthon/Backend/API/server.py)
- [Backend/API/auth.py](/home/bot/repos/WalkSense-Hackthon/Backend/API/auth.py)
- [Backend/API/database.py](/home/bot/repos/WalkSense-Hackthon/Backend/API/database.py)
- [Backend/API/models.py](/home/bot/repos/WalkSense-Hackthon/Backend/API/models.py)
- [Backend/API/manager.py](/home/bot/repos/WalkSense-Hackthon/Backend/API/manager.py)
- [Frontend/src/App.jsx](/home/bot/repos/WalkSense-Hackthon/Frontend/src/App.jsx)
- [Frontend/src/hooks/useAuth.js](/home/bot/repos/WalkSense-Hackthon/Frontend/src/hooks/useAuth.js)
- [Frontend/vite.config.js](/home/bot/repos/WalkSense-Hackthon/Frontend/vite.config.js)
- [Backend/tests/test_auth_integration.py](/home/bot/repos/WalkSense-Hackthon/Backend/tests/test_auth_integration.py)
- [.github/workflows/auth-integration.yml](/home/bot/repos/WalkSense-Hackthon/.github/workflows/auth-integration.yml)

Validation commands run:
- `python3 -m py_compile Backend/API/server.py Backend/API/auth.py Backend/API/manager.py Backend/API/database.py Backend/API/models.py` -> pass
- `cd Backend && python3 -m unittest discover -s tests -p 'test_auth_integration.py' -v` -> **5/6 tests failed**
- ASGI smoke test on `/api/auth/login` with email payload -> runtime failure: `RuntimeError: Database not available` when Mongo driver unavailable
- Module availability check -> `motor=False`, `bson=False` in current environment

## 4) Strengths That Help Hackathon Selection
1. Clear, high-impact problem statement for visually impaired navigation.
2. Real multimodal architecture: perception + reasoning + fusion + interaction layers.
3. Strong prototype feature set:
- Browser camera streaming for cloud deployment.
- Deepgram multilingual STT (`language: multi`) in [config.json](/home/bot/repos/WalkSense-Hackthon/Backend/Inference/config.json).
- Gemini VLM/LLM model targets aligned to modern API-first workflows.
4. Security hardening foundation already present:
- Access/refresh JWT rotation and token-family blacklisting.
- Brute-force controls and auth audit logs.
- Metrics and maintenance loop for auth artifacts.
5. Practical EC2 deployment artifacts:
- [start_backend.sh](/home/bot/repos/WalkSense-Hackthon/Backend/deploy/ec2/start_backend.sh)
- [walksense-backend.service](/home/bot/repos/WalkSense-Hackthon/Backend/deploy/ec2/walksense-backend.service)

## 5) Critical Blockers (P0)
These issues materially reduce hackathon selection odds because they can break the live demo.

### P0-1) Auth runtime dependency mismatch causes login failure
Evidence:
- Mongo auth path is now required in [server.py:165](/home/bot/repos/WalkSense-Hackthon/Backend/API/server.py:165).
- Mongo connection is optional/lazy and returns `None` when `motor` missing in [database.py:29](/home/bot/repos/WalkSense-Hackthon/Backend/API/database.py:29).
- Login path does not recover from DB unavailable runtime in [server.py:189](/home/bot/repos/WalkSense-Hackthon/Backend/API/server.py:189).
- `requirements.txt` and `requirements-server.txt` do not include `motor`/`pymongo`.

Impact:
- `/api/auth/login` can 500 at demo time.
- End-to-end user journey is not reliable.

### P0-2) Frontend dev API proxy port mismatch
Evidence:
- API proxy targets port 8000 in [vite.config.js:18](/home/bot/repos/WalkSense-Hackthon/Frontend/vite.config.js:18).
- Backend runs on port 8080 in [server.py:732](/home/bot/repos/WalkSense-Hackthon/Backend/API/server.py:732) and [README.md](/home/bot/repos/WalkSense-Hackthon/README.md).

Impact:
- Local demo path breaks or appears flaky.

### P0-3) Auth integration tests are red
Evidence:
- [test_auth_integration.py](/home/bot/repos/WalkSense-Hackthon/Backend/tests/test_auth_integration.py) still sends `username` payload while server now expects `email`.
- Current test run result: 5 failures out of 6.

Impact:
- CI confidence is invalid for the currently implemented auth flow.

## 6) High-Priority Risks (P1)
### P1-1) Split identity stores (Mongo users + SQLite auth users)
Evidence:
- Mongo used for user auth.
- SQLite still used for token families/rate-limits/users in [auth.py](/home/bot/repos/WalkSense-Hackthon/Backend/API/auth.py).
- Bridge behavior updates SQLite user password from login payload in [server.py:204](/home/bot/repos/WalkSense-Hackthon/Backend/API/server.py:204).

Impact:
- Consistency drift risk.
- Increased complexity under demo pressure.

### P1-2) Missing dependency declaration for auth path
Evidence:
- [models.py](/home/bot/repos/WalkSense-Hackthon/Backend/API/models.py) imports `bcrypt`.
- [database.py](/home/bot/repos/WalkSense-Hackthon/Backend/API/database.py) depends on `motor`.
- Neither appears in backend requirements files.

Impact:
- Fresh environment bootstrap can fail unexpectedly.

### P1-3) Repo hygiene and packaging noise
Evidence:
- Large untracked virtualenv folder `Backend/venv-server/`.
- `.gitignore` excludes `Backend/venv/` but not `Backend/venv-server/` in [.gitignore](/home/bot/repos/WalkSense-Hackthon/.gitignore).

Impact:
- Risk of bloated submissions and noisy diffs near deadline.

## 7) User Journey Audit (Current State)
| Journey Stage | Status | Evidence |
|---|---|---|
| Signup | Partial | Frontend sends email+username+password; backend supports Mongo register. |
| Login | **At risk** | Can fail if Mongo dependency/connection absent (`Database not available`). |
| Authenticated API usage | Good | Bearer checks via `require_user`; protected endpoints present. |
| Token refresh rotation | Good | Refresh rotation + family blacklist logic implemented. |
| Compromise handling | Good | Reuse detection revokes family; alert hooks and metrics exposed. |
| WebSocket auth | Good | `/ws`, `/ws/camera`, `/ws/audio` validate access token. |
| Logout | Good | Family revoke + refresh cookie clearing path exists. |
| Dev environment run-through | **At risk** | Vite `/api` proxy port mismatch (8000 vs 8080). |

## 8) Security and Trust Audit
Positive:
1. Access + refresh token model with rotation and family blacklisting is a strong hackathon differentiator.
2. Auth audit events and retention cleanup are in place.
3. Rate limiting for login/refresh and compromise alerting hooks are present.
4. Cookie policy controls are well-structured (`Secure`, `SameSite`, cross-site gating).

Gaps:
1. Default JWT secret fallbacks still exist in code path (acceptable for dev, risky if env misconfigured).
2. `/metrics/auth` has no auth gate; should be behind internal route/reverse proxy in production.
3. Mixed Mongo+SQLite auth model adds attack surface and operational complexity.

## 9) Performance and Runtime Readiness
Positive:
1. Non-blocking architecture improvements exist in manager lifecycle controls and bounded queues.
2. Voice-query concurrency is capped via semaphore to avoid threadpool starvation.
3. Browser-camera pipeline has bounded frame queue for backpressure.

Risks:
1. Runtime stability now depends on Mongo availability and undeclared dependencies.
2. No automated load/perf regression checks in CI.

## 10) What Judges Will Likely Ask
1. "Can you demo login -> run pipeline -> voice query -> refresh -> logout live?"
- Current answer: **not safely repeatable** until P0 fixes are done.
2. "Can this run reproducibly on a clean EC2 machine?"
- Current answer: **not guaranteed** due dependency/config mismatch and dual-auth-store complexity.
3. "How safe is user session handling?"
- Current answer: **strong conceptually**, but integration quality currently inconsistent.

## 11) 48-Hour Remediation Plan (Selection-Oriented)
### Day 1 (P0)
1. Unify auth contract:
- Choose one: Mongo-first or SQLite-only for prototype.
- Update frontend payloads, backend models, and tests to one canonical schema.
2. Fix Vite API proxy:
- Set `/api` target to backend port 8080 or align backend to configured port.
3. Make tests green:
- Update [test_auth_integration.py](/home/bot/repos/WalkSense-Hackthon/Backend/tests/test_auth_integration.py) to current auth schema and run in CI.
4. Dependency lock:
- Add required deps (`motor`, `bcrypt`, optional `pymongo`) to requirements if Mongo path remains.

### Day 2 (P1)
1. Add one fast smoke test workflow:
- Login, start pipeline, hit `/api/system/status`, logout.
2. Add health endpoints:
- `/healthz` and `/readyz` to simplify demo checks.
3. Harden operational docs:
- One exact EC2 runbook with env matrix for browser camera + Deepgram + Gemini.
4. Clean repo hygiene:
- Ignore local virtualenv artifacts and keep submission slim.

## 12) Final Recommendation
Current recommendation: **Do not submit as-is for final judging demo.**

Submit after P0 closure and green CI:
1. Auth flow must be deterministic in a clean environment.
2. Frontend-backend local/dev wiring must be consistent.
3. Core integration tests must pass on the same branch being demoed.

If those are completed, WalkSense is a strong hackathon prototype candidate with a compelling impact story and credible technical depth.
