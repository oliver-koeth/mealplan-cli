# Enhancement Brief: enhance-007 Multi-User Management

## Problem statement
The current application is effectively single-user: calendar and food-log data are written to shared files, and local/web API endpoints do not enforce bearer-token authentication or user isolation. This prevents safe multi-user operation on one deployed instance and creates a data-leak risk between users.

This enhancement introduces user registration and authentication using bearer tokens, per-user data-file partitioning, and mandatory token-based identity for web/API usage while preserving current CLI default behavior when no user is specified.

## Goals
- Support multiple users on one app instance with strict data isolation.
- Use email as canonical user identity.
- Add bearer-token authentication for web UI and REST API (Authorization header, Bearer format).
- Add a dedicated Set User flow in the web UI for first-time registration and token onboarding.
- Persist user registry (`users.json`) and per-user data files for calendar/log.
- Keep CLI backward compatible when `--user` is omitted.

## In scope
- Identity and persistence model:
  - Canonical username is `email`.
  - Add a single user registry store file (default `~/.mealplan/users.json`, env-overridable) containing user records with `email`, `name`, and bearer-token verifier data.
  - Bearer token shall be hashed at rest (no plaintext token persistence in `users.json`).
  - Token hashing defaults (best practice):
    - use Argon2id with per-token random salt,
    - store algorithm/version metadata with hash verifier,
    - verify in constant-time,
    - concrete defaults:
      - memory_cost: 65536 KiB,
      - time_cost: 3,
      - parallelism: 1,
      - hash_len: 32 bytes,
    - keep parameters configurable for future hardening and rehash when stored parameters are weaker than current defaults.
  - Partition calendar/log storage per user by filename prefix using email:
    - `calendar.json` -> `<email>-calendar.json`
    - `food-log.json` -> `<email>-food-log.json`
  - Preserve current non-prefixed file behavior when no user context exists (CLI without `--user`).
  - Define canonical email-to-filename normalization/sanitization rules:
    - order: `trim` -> lowercase email -> replace invalid chars,
    - replace every character not in `[a-zA-Z0-9.]` with `_`,
    - example: `koeth@acm.org` -> `koeth_acm.org`,
    - resulting filename must always be resolved inside configured storage directory (no path traversal).
- CLI behavior:
  - Add optional `--user <email>` to `calculate`, `calendar`, `log`, and `log search`.
  - If `--user` is omitted, keep current storage paths and filenames unchanged.
  - If `--user` is provided, resolve storage files to the `<email>-...` prefixed variants.
  - CLI does not require bearer token entry.
- API and web authentication:
  - Require `Authorization: Bearer <token>` for all data API routes except health and user-setup routes.
  - Token parsing must be compatible with GPT Actions bearer format (standard HTTP Bearer auth scheme).
  - Derive authenticated user identity from bearer token and use it to resolve user-partitioned storage files.
  - Reject missing/invalid/unknown bearer token with canonical structured API errors.
  - Standardize set-user endpoint paths:
    - `POST /api/v1/users/register`
    - `POST /api/v1/users/attach-token`
    - `POST /api/v1/users/exchange-token`
  - Add minimal brute-force protection on authentication-sensitive endpoints:
    - apply to all auth-sensitive API endpoints,
    - threshold: 100 requests per minute per IP and endpoint pair,
    - on threshold breach return `429`,
    - include `Retry-After: 60` response header,
    - enforce 1-minute cooldown for the same IP+endpoint key.
  - Provide a token-rotation function where an existing valid bearer token for a user can be exchanged for a newly generated bearer token.
  - Token exchange/rotation must be atomic (single operation that invalidates old token and activates new token without intermediate inconsistent state), with old token invalid immediately after successful exchange.
- Set User page (new web UI route):
  - If no token is present in browser local storage, redirect shell routes client-side to Set User page.
  - New-user registration flow:
    - Input: `email`, `name`.
    - Create user only if email is not already registered; otherwise return error.
    - Generate bearer token during creation and show it exactly once.
    - Show amber warning callout: token is displayed once and must be stored safely.
    - Persist user in `users.json`.
  - Existing-user onboarding flow:
    - Input: `email`, existing bearer token (manual paste).
    - Validate token/email pairing against `users.json` before accepting.
  - Logout flow:
    - Remove token from local storage.
    - Return to a clean Set User page state.
- Settings integration:
  - Persist bearer token in local storage (same persistence style as UI settings).
  - Show bearer token in Settings as read-only and masked by default, with explicit reveal action.
- Token-strength mechanism (proposal):
  - Generate opaque high-entropy tokens from `secrets.token_urlsafe(32)` (>=256 bits entropy).
  - Recommended wire format: `mpu_v1_<random-urlsafe>`.
  - Tokens are unguessable and non-derivable from email.

## Out of scope
- OAuth/OIDC, SSO, password-based auth, MFA, or role-based access control.
- Token revocation lists or multi-token-per-user lifecycle.
- Migration/backfill tooling for assigning legacy shared records to users.
- Distributed locking/consistency for concurrent multi-process writes beyond current local JSON-store model.

## Constraints and assumptions
- Email identity is case-insensitive for lookup uniqueness; persist canonical normalized form (lowercase).
- Bearer token is an opaque credential; user identity is resolved via `users.json` lookup.
- For this enhancement scope, `users.json` stores only hashed token verifier data and never plaintext bearer tokens.
- `users.json` target file mode shall be `0600`; if weaker permissions are detected, continue safely and write a warning to system log.
- Users-store env var default name is `MEALPLAN_USERS_STORE_PATH`.
- System-log warning default target is logger name `mealplan.security`.
- Health endpoint (`GET /api/v1/health`) remains unauthenticated.
- Local UI runs on loopback by default; token is still mandatory for data routes and persisted per browser in local storage.
- Because bearer tokens are stored in `localStorage`, they are vulnerable to XSS; UI delivery must enforce a strict CSP and avoid inline third-party scripts.
- CSP default policy baseline:
  - `default-src 'self'`
  - `script-src 'self'` (no inline script; move inline JS to same-origin static asset)
  - `style-src 'self' 'unsafe-inline'` (until CSS is externalized)
  - `object-src 'none'`
  - `base-uri 'none'`
  - `frame-ancestors 'none'`
  - `form-action 'self'`
- Rate-limit client-IP extraction default:
  - use socket remote address by default,
  - trust `X-Forwarded-For` only when request comes from configured trusted proxy CIDR(s); otherwise ignore forwarded headers.
- Existing API error envelope format remains canonical and is extended with auth-specific defaults:
  - `401` + `auth_missing_token` for missing Authorization header,
  - `401` + `auth_invalid_token` for malformed/unknown token,
  - `403` + `auth_token_email_mismatch` for attach-token email/token mismatch,
  - `409` + `user_already_exists` for duplicate email registration,
  - `429` + `auth_rate_limited` for brute-force threshold violations.
  - `429` responses include `Retry-After: 60`.
- Redirect behavior is client-only for shell UX; API endpoints do not redirect and instead return canonical auth error responses.

## Implementation impact analysis (current code amendment map)
- CLI command surface and storage resolution:
  - `src/mealplan/cli/main.py`
  - Amend command options to include optional `--user` on date/log-related commands.
  - Refactor `_calendar_store_path()` and `_food_log_store_path()` to accept optional user context and return prefixed filenames when set.
  - Update help text/examples for `--user` behavior.
- Web API auth and route protection:
  - `src/mealplan/web/ui_server.py`
  - Add bearer-token extraction/validation from `Authorization` header.
  - Add authenticated user context resolution used by all protected handlers.
  - Guard `POST /api/v1/calculate`, `PUT/GET /api/v1/calendar/{date}`, `POST/PUT /api/v1/log`, `GET /api/v1/log/search`.
  - Keep `GET /api/v1/health` public.
  - Add user-management API contract and endpoints (using existing API contract/error-envelope patterns) for:
    - register new user (`email`, `name`) and return one-time plaintext bearer token response,
    - attach existing token for email validation,
    - exchange an existing valid token for a newly generated token.
  - Ensure API auth failures return error codes (no redirects).
  - Use safe atomic file updates for user/token mutations: file lock + write temp file + fsync + atomic rename.
- Web shell routing and local-storage behavior:
  - `src/mealplan/web/ui_server.py` (inline HTML/CSS/JS shell + `_PAGE_CONTENT` + route handler)
  - Add new `/set-user` page and nav/redirect logic.
  - Add local-storage key(s) for auth token and selected email.
  - Inject Authorization bearer header in all fetch calls to protected API routes.
  - Add logout action and token clear flow.
  - Extend `/settings` UI with read-only token display.
- Persistence infrastructure:
  - `src/mealplan/infrastructure/`
  - Add new `JsonUsersStore` (or equivalent) for `users.json` CRUD/lookup constraints.
  - Keep existing `JsonCalendarStore` and `JsonFoodLogStore` payload contracts; user isolation is applied via path selection.
  - Update `src/mealplan/infrastructure/__init__.py` exports.
- Contracts and validation:
  - `src/mealplan/application/contracts.py`
  - Add boundary contracts for set-user/register, token-attach, and token-exchange requests/responses.
  - Enforce email normalization and validation rules.
- Test coverage updates required:
  - `tests/unit/test_web_ui_server.py`: auth-required route tests, token parsing, unauthorized/forbidden responses, set-user page redirects, user endpoints.
  - `tests/cli/test_calendar.py`, `tests/cli/test_log.py`, `tests/cli/test_calculate.py`: `--user` option behavior and path partitioning.
  - New unit tests for users store under `tests/unit/`.
  - UI mode integration tests in `tests/cli/test_ui_mode.py` for redirect-to-set-user and authenticated calls.
- Documentation updates required after implementation:
  - `README.md`, `docs/REQUIREMENTS.md`, `docs/ARCHITECTURE.md`, and privacy content in `src/mealplan/web/ui_server.py` must be updated to reflect mandatory bearer auth and multi-user data handling.

## Definition of done
- Enhancement brief requirements are implemented with tests green.
- Web/API protected routes reject requests without valid bearer token.
- Authenticated requests are strictly scoped to user-partitioned calendar/log files.
- Set User page supports:
  - new user registration with one-time token display + amber warning,
  - existing token onboarding for email,
  - logout clearing local token and returning to clean setup state.
- Settings page shows bearer token read-only, masked by default, with reveal option.
- CLI supports optional `--user` and retains legacy behavior when omitted.
- User registry persistence exists in one `users.json` file with uniqueness enforcement on email.
- User-management APIs use canonical paths (`/api/v1/users/register`, `/api/v1/users/attach-token`, `/api/v1/users/exchange-token`).
- User/token mutation writes are atomic via lock + temp file + fsync + atomic rename.
- Docs and help text reflect final auth and multi-user behavior.

## Open questions
- None for current enhancement scope.
