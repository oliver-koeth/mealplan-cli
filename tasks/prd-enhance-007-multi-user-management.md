# PRD: Enhance-007 Multi-User Management

## 1. Introduction/Overview
Enhancement 007 introduces secure multi-user support for a shared mealplan instance. Today, calendar and food-log data are effectively single-user and API/UI routes are not bearer-auth protected. This PRD defines an end-to-end implementation for CLI, API, web UI, persistence, and tests so that users are isolated by email identity and authenticated by bearer tokens.

This PRD is based on enhancement brief `docs/enhancements/enhance-007-multi-user-management.md` and confirmed scope decisions:
- Full end-to-end scope (CLI + API + UI + tests + docs)
- CLI `--user` must reference a registered user
- Rate limiting applies to all bearer-protected API endpoints
- Set User page includes token-rotation UI now

## 2. Goals
- Enforce bearer-token authentication on all protected API routes.
- Isolate persisted calendar/log data per authenticated user.
- Add a secure Set User workflow for register, attach, logout, and token rotation.
- Keep CLI backward-compatible when `--user` is omitted.
- Add optional CLI `--user` that requires registered user existence.
- Persist only hashed bearer-token verifier data at rest.
- Add deterministic auth error contracts and brute-force protection.

## 3. User Stories (Implementation Backlog)

### US-001: Add users persistence model and store
**Description:** As a developer, I want a dedicated users store so user identity and token verifier data can be persisted safely.

**Acceptance Criteria:**
- [ ] Add `users.json` storage with deterministic schema including `email`, `name`, token hash verifier metadata, and schema version.
- [ ] `users.json` default path is `~/.mealplan/users.json` with env override.
- [ ] Canonical users-store env var is `MEALPLAN_USERS_STORE_PATH`.
- [ ] Store never persists plaintext bearer tokens.
- [ ] Target file mode is `0600`; if weaker permissions are detected, continue and write warning to logger `mealplan.security`.
- [ ] Typecheck passes.
- [ ] Tests pass.

### US-002: Implement token generation, hashing, and verification utilities
**Description:** As a developer, I want hardened token utilities so issued tokens are unguessable and safely verifiable.

**Acceptance Criteria:**
- [ ] Token generation uses `secrets.token_urlsafe(32)` and format `mpu_v1_<token>`.
- [ ] Hashing uses Argon2id with defaults: `memory_cost=65536 KiB`, `time_cost=3`, `parallelism=1`, `hash_len=32`.
- [ ] Hash verifier includes algorithm/version metadata.
- [ ] Verification is constant-time and supports rehash recommendation when stored params are weaker than current defaults.
- [ ] Typecheck passes.
- [ ] Tests pass.

### US-003: Define auth and set-user API contracts
**Description:** As an API consumer, I want explicit request/response contracts so integrations are deterministic.

**Acceptance Criteria:**
- [ ] Add contracts for register user, attach existing token, and exchange token.
- [ ] Route contracts are fixed to: `POST /api/v1/users/register`, `POST /api/v1/users/attach-token`, `POST /api/v1/users/exchange-token`.
- [ ] Add/confirm canonical error envelope usage for auth and user-management failures.
- [ ] Auth error defaults implemented:
  - `401 auth_missing_token`
  - `401 auth_invalid_token`
  - `403 auth_token_email_mismatch`
  - `409 user_already_exists`
  - `429 auth_rate_limited`
- [ ] `429` responses include `Retry-After: 60`.
- [ ] Typecheck passes.
- [ ] Tests pass.

### US-004: Implement email canonicalization and filename mapping
**Description:** As a developer, I want deterministic email normalization and filename mapping so user-partitioned files are filesystem-safe.

**Acceptance Criteria:**
- [ ] Email identity canonicalization order is `trim -> lowercase`.
- [ ] Filename mapping replaces every char not in `[a-zA-Z0-9.]` with `_`.
- [ ] Example mapping holds: `koeth@acm.org -> koeth_acm.org`.
- [ ] File path resolver guarantees resulting files remain inside configured storage directory.
- [ ] Typecheck passes.
- [ ] Tests pass.

### US-005: Implement API bearer-auth middleware/helpers
**Description:** As a user, I want protected APIs to require a valid bearer token so only authorized users can access their data.

**Acceptance Criteria:**
- [ ] Protected routes reject missing/invalid/unknown bearer tokens with canonical auth errors.
- [ ] Token-to-user resolution uses users store verifier lookup.
- [ ] Health endpoint remains public.
- [ ] API endpoints never redirect; they return structured errors.
- [ ] Typecheck passes.
- [ ] Tests pass.

### US-006: Implement brute-force protection for bearer-protected APIs
**Description:** As an operator, I want baseline abuse protection so repeated auth attempts are rate-limited.

**Acceptance Criteria:**
- [ ] Rate limit applies to all bearer-protected API endpoints.
- [ ] Keying is per `IP + endpoint` pair.
- [ ] Threshold is `100 requests / minute / IP+endpoint`.
- [ ] Breach returns `429 auth_rate_limited` and `Retry-After: 60`.
- [ ] Cooldown is enforced for 1 minute per offending key.
- [ ] Client-IP source defaults to socket remote address; `X-Forwarded-For` is trusted only for configured trusted proxy CIDR(s).
- [ ] Typecheck passes.
- [ ] Tests pass.

### US-007: Add set-user API endpoints (register, attach, exchange)
**Description:** As a web client, I want dedicated user-management endpoints so account bootstrap and token lifecycle are explicit.

**Acceptance Criteria:**
- [ ] `POST /api/v1/users/register` creates user only if email not already registered; duplicate returns `409 user_already_exists`.
- [ ] Register response returns plaintext token once (for immediate display) while persisting only hashed verifier.
- [ ] `POST /api/v1/users/attach-token` validates email/token pairing; mismatch returns `403 auth_token_email_mismatch`.
- [ ] `POST /api/v1/users/exchange-token` validates existing token and returns newly issued token.
- [ ] Exchange operation is atomic and old token becomes invalid immediately after success.
- [ ] User/token mutation writes use safe atomic persistence (`file lock -> temp file write -> fsync -> atomic rename`).
- [ ] Typecheck passes.
- [ ] Tests pass.

### US-008: Wire authenticated user to per-user calendar/log storage in API
**Description:** As an authenticated user, I want all API persistence routed to my own files so data is isolated.

**Acceptance Criteria:**
- [ ] Calendar and food-log API handlers derive user from bearer token and resolve `<user-prefix>-calendar.json` / `<user-prefix>-food-log.json`.
- [ ] Authenticated users cannot read or write another user's files through API calls.
- [ ] Typecheck passes.
- [ ] Tests pass.

### US-009: Add CLI `--user` support with registration enforcement
**Description:** As a CLI user, I want optional explicit user scoping while preserving legacy behavior.

**Acceptance Criteria:**
- [ ] Add optional `--user` to `calculate`, `calendar`, `log`, and `log search`.
- [ ] If `--user` omitted, legacy non-prefixed files are used.
- [ ] If `--user` provided, email is canonicalized and user must exist in `users.json`; unknown user returns deterministic validation/domain error.
- [ ] If `--user` provided and valid, CLI uses per-user prefixed files.
- [ ] Typecheck passes.
- [ ] Tests pass.

### US-010: Create Set User page UI with register and attach flows
**Description:** As a user, I want a dedicated setup page so I can register or attach a token before using the app.

**Acceptance Criteria:**
- [ ] Add `/set-user` page with two flows:
  - register new user (`email`, `name`) and receive one-time token display,
  - attach existing token (`email`, token) with validation feedback.
- [ ] Register success displays amber warning that token is shown once and must be stored safely.
- [ ] Shell routes redirect client-side to Set User when token is absent in local storage.
- [ ] Protected API requests from UI include `Authorization: Bearer <token>`.
- [ ] UI script delivery avoids inline third-party scripts and is compatible with strict CSP (`script-src 'self'`).
- [ ] Typecheck passes.
- [ ] Tests pass.
- [ ] Verify in browser using dev-browser skill.

### US-011: Add logout and token rotation UI
**Description:** As an authenticated user, I want to log out and rotate compromised tokens from the UI.

**Acceptance Criteria:**
- [ ] Set User page includes logout action that removes token from local storage and returns clean setup state.
- [ ] Set User page includes rotate-token action invoking exchange endpoint.
- [ ] On successful rotation, UI updates stored token to new value and old token no longer works.
- [ ] Typecheck passes.
- [ ] Tests pass.
- [ ] Verify in browser using dev-browser skill.

### US-012: Update settings UI token display policy
**Description:** As a user, I want token visibility controls that reduce accidental exposure.

**Acceptance Criteria:**
- [ ] Settings shows bearer token as read-only and masked by default.
- [ ] Explicit reveal action shows token without enabling edits.
- [ ] Typecheck passes.
- [ ] Tests pass.
- [ ] Verify in browser using dev-browser skill.

### US-013: Add comprehensive automated test coverage
**Description:** As a maintainer, I want complete tests so auth and multi-user behavior remain stable.

**Acceptance Criteria:**
- [ ] Add/extend unit tests for users store, token hashing/verification, canonicalization, and auth helpers.
- [ ] Add/extend web API tests for auth required/invalid/unknown/rate-limited paths and set-user endpoints.
- [ ] Add/extend CLI tests for `--user` behavior (omitted/known/unknown).
- [ ] Add UI mode integration coverage for set-user redirect and authenticated flows.
- [ ] Typecheck passes.
- [ ] Tests pass.

### US-014: Update canonical documentation
**Description:** As a developer/operator, I want docs aligned with security behavior so usage and deployment are correct.

**Acceptance Criteria:**
- [ ] Update README, REQUIREMENTS, ARCHITECTURE, and privacy policy copy for bearer auth and multi-user storage.
- [ ] Document localStorage/XSS risk and strict CSP/no inline third-party scripts requirement.
- [ ] Document auth error defaults and rate-limit behavior.
- [ ] Typecheck passes.
- [ ] Tests pass.

## 4. Functional Requirements
- FR-1: System must represent users by canonical email (`trim -> lowercase`) and store them in `users.json`.
- FR-2: System must persist only hashed bearer-token verifier data; plaintext token persistence is forbidden.
- FR-3: Token hashing must use Argon2id defaults (`memory_cost=65536 KiB`, `time_cost=3`, `parallelism=1`, `hash_len=32`) with per-token salt and verifier metadata.
- FR-4: API must require `Authorization: Bearer <token>` on all protected routes and return structured auth errors for failures.
- FR-5: Health route remains unauthenticated.
- FR-6: API must enforce rate limit `100 requests/minute` per `IP+endpoint` on all bearer-protected endpoints.
- FR-7: Rate-limit breaches must return `429 auth_rate_limited` and header `Retry-After: 60`.
- FR-8: Calendar/log file path mapping for user context must use sanitized user prefix with invalid chars replaced by `_` and must remain within configured storage root.
- FR-9: API persistence for calendar/log must be scoped by authenticated user-derived prefix.
- FR-10: CLI commands (`calculate`, `calendar`, `log`, `log search`) must support optional `--user`.
- FR-11: CLI with `--user` must reject unknown users; CLI without `--user` must keep legacy non-prefixed behavior.
- FR-12: Set-user APIs must support register, attach, and exchange operations with deterministic statuses/error codes.
- FR-12a: Set-user API routes are fixed as `POST /api/v1/users/register`, `POST /api/v1/users/attach-token`, and `POST /api/v1/users/exchange-token`.
- FR-13: Register must reject duplicate email with `409 user_already_exists`.
- FR-14: Attach must reject token/email mismatch with `403 auth_token_email_mismatch`.
- FR-15: Token exchange must be atomic and old token invalid immediately after successful exchange.
- FR-16: UI must provide `/set-user` with register, attach, logout, and token-rotation flows.
- FR-17: UI must redirect client-side to `/set-user` when token missing.
- FR-18: UI API requests must include bearer token header when calling protected endpoints.
- FR-19: Settings token display must be read-only, masked by default, with explicit reveal.
- FR-20: `users.json` target mode must be `0600` and weaker permission detection must produce system log warning.
- FR-21: Canonical users-store env var is `MEALPLAN_USERS_STORE_PATH`.
- FR-22: Token/user mutation persistence must be atomic via file lock, temp write, fsync, and atomic rename.
- FR-23: IP source for rate limiting defaults to socket remote address and may use `X-Forwarded-For` only for trusted proxy CIDR(s).
- FR-24: CSP baseline must include `default-src 'self'`, `script-src 'self'`, `style-src 'self' 'unsafe-inline'`, `object-src 'none'`, `base-uri 'none'`, `frame-ancestors 'none'`, and `form-action 'self'`.

## 5. Non-Goals (Out of Scope)
- OAuth/OIDC, SSO, MFA, password auth, RBAC.
- Token revocation lists and multi-token-per-user lifecycle.
- Data migration/backfill assigning legacy shared data to users.
- Distributed cross-process coordination beyond local JSON persistence behavior.

## 6. Design Considerations
- Preserve existing visual language in current UI shell.
- Add Set User page as first-class route with clear, low-friction setup flow.
- Use amber warning styling for one-time token display.
- Keep Settings token control simple: masked display + reveal toggle + no edit.

## 7. Technical Considerations
- Existing web server is in-process `http.server` style adapter in `src/mealplan/web/ui_server.py`.
- Existing persistence stores are path-based; user isolation should be introduced through deterministic path resolution.
- API contract and error envelope patterns already exist and should be reused for new user-management routes.
- Token exchange atomicity in file storage should use safe write semantics (temp file + atomic rename) to avoid inconsistent verifier state.

## 8. Success Metrics
- 100% of protected API calls without valid bearer token return canonical auth errors.
- Cross-user data leakage incidents: 0 in automated tests.
- All user-management flows (register, attach, rotate, logout) executable through UI and covered by tests.
- CLI legacy mode (no `--user`) remains backward compatible.
- CI passes with new multi-user/auth coverage.

## 9. Open Questions
- None for current scope.
