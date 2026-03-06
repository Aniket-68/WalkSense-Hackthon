# WalkSense Security Assessment (2026-03-06)

## Scope
- Backend API and WebSocket surface (`Backend/API/server.py`)
- Frontend client flow (`Frontend/src`)
- Authentication/session handling

## Key Findings (Before Fix)
1. Critical: No authentication or authorization on API/WS endpoints.
2. Critical: No session lifecycle (login/logout/refresh) existed.
3. High: `CORS` allowed all origins while credentials were enabled.
4. High: Camera and WebSocket channels were publicly accessible.
5. Medium: No compromise response path for token replay/reuse.

## End-to-End User Journey Validation
Current implemented journey is now:
1. `POST /api/auth/login` with username/password.
2. Backend returns short-lived access JWT and sets HttpOnly refresh cookie.
3. Frontend attaches bearer access token to all protected API calls.
4. Frontend sends access token query parameter for protected WebSockets and MJPEG feed.
5. On access expiry, frontend calls `POST /api/auth/refresh`; backend rotates refresh token.
6. On refresh token reuse detection, backend blacklists the entire JWT family and revokes all related tokens.
7. `POST /api/auth/logout` revokes token family and clears refresh cookie.
8. `POST /api/auth/revoke-family` provides immediate manual family revocation for suspected compromise.

## JWT Rotation + Family Blacklisting Strategy
- Access token: stateless, short TTL.
- Refresh token: one-time-use with strict rotation.
- Family model:
  - Each login creates a `family_id`.
  - Every refresh token carries `jti` + `family_id`.
  - On refresh, previous token is marked `used`; a new token is minted.
  - If a non-active refresh token is presented again, family is blacklisted (compromise signal).
- Family blacklist enforcement:
  - Access token validation denies requests when `family_id` is blacklisted.
  - Refresh attempts on blacklisted family are denied.

## Implemented Hardening
1. Brute-force protection/rate limiting implemented on:
   - `/api/auth/login`
   - `/api/auth/refresh`
2. Managed provisioning flow added:
   - `python3 -m API.provision_user ...`
   - bootstrap auth account can be disabled with `AUTH_BOOTSTRAP_ENABLED=false` (default in production).
3. Cookie policy hardened:
   - secure cookies forced in `APP_ENV=production`
   - `SameSite=None` allowed only in explicit cross-site mode (`AUTH_COOKIE_CROSS_SITE=true`).
4. Audit logging added for auth lifecycle:
   - login success/failure
   - refresh success/failure
   - token family blacklist events
   - logout and manual revoke events.
5. Integration tests added:
   - login -> refresh rotation -> logout
   - refresh reuse compromise path -> family denial
   - WS auth rejection/acceptance
   - login brute-force rate limit block.
6. Periodic auth-data cleanup/retention added:
   - background housekeeping loop in API startup
   - retention cleanup for `auth_audit_events` and stale `auth_rate_limits`.
7. Lockout alerting/monitoring hooks added:
   - repeated compromise detection with cooldown
   - CloudWatch metric hook (`AUTH_ALERT_CLOUDWATCH_ENABLED=true`)
   - Prometheus-style metrics endpoint at `GET /metrics/auth`.
8. CI automation added:
   - GitHub Actions workflow to run auth integration tests on push/PR.

## Residual Risks / Next Steps
1. Scope `/metrics/auth` exposure behind internal network/reverse-proxy auth if internet-facing.
2. Route alert outputs to your pager/incident channel (SNS/Slack/PagerDuty) for operational response.
3. For multi-instance EC2 scaling, move auth state/rate-limit storage to shared DB/Redis.
