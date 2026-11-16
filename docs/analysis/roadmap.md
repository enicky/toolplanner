# Tool Planner delivery roadmap

**Overall status:** Phase 0 approved; Phase 1 design baseline accepted; Phase 2–5 implementation in progress
**Tracking:** Check a task only when its completion evidence exists. Add a short
note or link to a PR/test/deployment record when completing a phase.

## Phase 0 — Product decisions and requirements

Status: **Complete — approved by product owner**

- [x] Record initial product goals, roles, data, architecture, reporting ideas,
  and release criteria in [README.md](README.md).
- [x] List decisions requiring business or IT input in
  [open-questions.md](open-questions.md).
- [x] Confirm a single Sanofi site for the first deployment.
- [x] Confirm local username/password/role accounts, typed borrower names, and that
  any authenticated account can return.
- [x] Confirm three-year retention, configurable default location, separate borrower/location,
  and capture of a different return location.
- [x] Confirm admin-configurable reservation rules, reservations during active
  loans, late-loan alerts and alternative suggestions, and three-year daily cleanup.
- [x] Confirm admins manage users, locations/default, reservation settings, and
  blocked status; all admins may view/export person-level history.
- [x] Confirm English, phones/iPads, Europe/Brussels, and Dockerfile + Helm
  deployment outside the company platform.
- [x] Confirm initial default location Geel, department Sites & Facilities,
  admin-provided infrastructure, and initial-password reset on first login.
- [x] Confirm a daily automated deletion job for eligible records after three
  years; preserve active loans and unfulfilled reservations.
- [x] Set initial reservation minimum notice, maximum duration, cancellation
  cutoff, and no-show grace period to seven days each.
- [x] Confirm backup contents may persist until backup lifecycle expiry and
  that restored databases must run cleanup before normal access.
- [x] Recommend a modern browser/device matrix: current and previous major
  iOS/iPadOS Safari, Android Chrome, and desktop Chrome/Edge/Safari.
- [x] Confirm manual bootstrap script for at least two admins, environment-
  configurable Helm values, initial elevator `LIFT-001`, and cancellation of an
  active loan when its elevator is blocked.
- [x] Approve Phase 0 requirements and first-release analysis.

**Exit:** Product owner approved Phase 0 on 2026-11-15.

## Phase 1 — Solution design

Status: **Design baseline accepted; implementation underway**

- [x] Define immediate checkout/return and future-reservation state machines,
  including pickup conversion, admin-configurable policies, and non-overlapping
  time windows even when an elevator has an active loan.
- [x] Review relational schema, constraints, indexes, and history correction
  strategy.
- [x] Define API contract, error responses, pagination, filtering, and versioning.
- [x] Define local account fields, password hashing/reset, user/admin authorization,
  admin account bootstrap, forced first-login password change, and typed
  borrower-name/account-actor handling.
- [x] Specify the manually run script for creating at least two initial admin
  accounts without shipping default credentials.
- [x] Produce mobile QR, borrow, return, and admin-page interaction designs.
- [x] Define report semantics, Europe/Brussels time zone, filters, and the
  all-admin person-level history/CSV export policy.
- [x] Review threat model, privacy impact, and accessibility requirements.
- [x] Define Helm values/contracts for the product-owner-provided cluster,
  ingress, secrets, PostgreSQL connection, and backup/restore integration.

**Exit:** Phase 1 design accepted as the implementation baseline on 2026-11-15.

## Phase 2 — Repository and developer foundation

Status: **Foundation scaffold implemented; CI and checks remain**

- [x] Create the Python API project structure and dependency management.
- [x] Create the React/TypeScript frontend and API integration.
- [x] Add PostgreSQL local development configuration and environment template
  containing placeholders only.
- [ ] Add formatting, linting, type checking, and test commands to CI.
- [x] Add local developer setup documentation and health checks.
- [x] Add safe initial seed data for local development.

**Exit:** A developer can start the app and database locally and run the
automated checks from documented commands.

## Phase 3 — Backend domain and persistence

Status: **Core flows implemented; concurrency, correction, and broader coverage remain**

- [x] Implement user, elevator, location, department, loan, reservation/settings,
  and audit models.
- [x] Seed default location `Geel`, department `Sites & Facilities`, and
  elevator `LIFT-001`.
- [x] Implement the manually run initial-admin bootstrap script with secure
  password entry, at least two admins, and forced password reset.
- [x] Add Alembic initial migration, constraints, and indexes.
- [x] Implement transactional checkout and return services.
- [x] Implement reservation persistence and time-window conflict rules, including
  the approved behavior when an elevator has an active loan.
- [x] Implement audited administrative cancellation of an active loan when its
  elevator is blocked; retain borrower custody until actual return and prevent
  another checkout until custody is closed.
- [x] Link reservation pickup to a loan and implement cancellation, expiry, and no-show
  behavior against approved rules.
- [x] Alert affected reservation owners after an admin blocks an elevator and
  suggest alternatives; show an unavailable alert if none are available.
- [x] Implement QR-token creation, lookup, rendering, and rotation.
- [x] Add inventory and loan APIs with input validation and explicit errors.
- [x] Add authorization and audit behavior for management operations.
- [x] Add admin APIs for user/password/role management, default location,
  reservation settings, and blocked/unblocked status.
- [x] Add focused unit/API tests for checkout, return, reservation rules,
  password changes, retention, and blocked-loan custody.
- [ ] Add PostgreSQL concurrency tests, auditable correction endpoints, and
  broader admin CRUD/report tests.
- [ ] Expand coverage for retries, invalid returns, blocked elevators, and
  retired elevators against PostgreSQL.

**Exit:** API tests currently pass on SQLite. PostgreSQL-specific concurrency
tests are still required before claiming the concurrency invariant verified.

## Phase 4 — User-facing application

Status: **Core flows implemented; admin navigation redesign proposed for review**

- [x] Analyze the current all-in-one admin workspace and propose a sidebar with
  separate management routes in [phase-4-admin-ia.md](phase-4-admin-ia.md).
- [ ] Review and approve the admin navigation, page grouping, and overview/report
  defaults before implementing the redesign.

- [x] Implement mobile elevator status and borrow pages.
- [x] Make immediate checkout the default and implement the future reservation
  flow with clear availability and conflict outcomes.
- [x] Implement return flow and conflict/validation messages.
- [x] Alert a reservation user when the loan is late at reservation time and
  suggest other elevators available for the requested period.
- [x] Implement user login and protected route behavior.
- [x] Implement admin user management, configurable reservation rules, and
  blocked-status controls; restrict person-level history/exports to admins.
- [x] Require newly issued initial passwords to be changed at first login.
- [ ] Complete inventory edit/retire/search flows and location editing.
- [x] Implement QR preview, download/print, and documented token rotation.
- [ ] Complete active-loan and history reports with approved filters/export.
- [ ] Enforce aggregate-by-default access and report age without an overdue
  label until an operations threshold is approved.
- [ ] Add frontend tests for success, validation, unavailable, stale, and
  unauthorized states.
- [ ] Validate responsive behavior and accessibility with keyboard and assistive
  technology checks.

**Exit:** End-to-end user and manager flows meet the approved acceptance
criteria on supported mobile and desktop browsers.

## Phase 5 — Security, deployment, and operations

Status: **Docker and Helm implemented and locally validated; production operations remain**

- [x] Add Dockerfile(s) and build API/frontend images with non-root
  defaults.
- [x] Create a Helm chart for Deployments, Services, Ingress, configuration,
  secrets, resource limits, probes, migrations, and the daily retention task.
- [x] Define configurable secret references and TLS/ingress settings in Helm.
- [x] Add a controlled database migration job.
- [x] Implement and test the daily deletion job for completed loans,
  reservations, and personal data older than three years and audit events older
  than three years; remove disabled-account details after three years where no
  active loan or unfulfilled reservation requires them.
- [x] Implement scheduled reservation no-show maintenance and late alerts.
- [ ] Add rollback/recovery guidance and production secret provisioning.
- [ ] Configure logs, metrics, alerting, rate limits, and operational dashboards.
- [ ] Document backup schedule, restore test, disaster recovery, and backup
  retention; verify restored data is cleaned before application access.
- [ ] Test deployment in a representative staging Kubernetes environment.

**Exit:** Staging deployment passes security and operations review, and restore
and health-check procedures are exercised.

## Phase 6 — Pilot and release

Status: **Not started**

- [ ] Load a reviewed elevator/location/department inventory.
- [ ] Print and physically verify QR labels on a small pilot set.
- [ ] Train managers and communicate the borrow/return process.
- [ ] Run acceptance tests with real operational users and collect feedback.
- [ ] Resolve pilot blockers; confirm support ownership and escalation path.
- [ ] Approve production rollout and monitor the first release.

**Exit:** Product owner accepts the pilot, support is ready, and production
rollout has an approved go/no-go.

## Phase 7 — Data-informed improvements

Status: **Not started**

- [ ] Review usage and overdue trends after a meaningful data collection period.
- [ ] Validate data completeness and report interpretations with operations.
- [ ] Consider overdue reminders, maintenance tracking, or integrations only
  when an owner and operational need are identified.
- [ ] Revisit retention, access, and reporting risks as data volume grows.

**Exit:** Follow-up work is prioritized using observed demand and approved
business outcomes, rather than assumptions.
