---
name: tool-planner-development
description: Analyze, design, implement, test, and deploy the internal Tool Planner application for elevator checkout and return. Use for feature work, bug fixes, architecture, and release tasks in this repository.
---

# Tool Planner development workflow

## Required sequence

1. **Analyze first.** Read `docs/analysis/README.md`, `docs/analysis/roadmap.md`,
   and `docs/analysis/open-questions.md`. Inspect relevant code, tests, project
   instructions, and current git changes before proposing or editing.
2. **Check assumptions.** Apply confirmed requirements in
   `docs/analysis/open-questions.md`. If an unresolved decision changes account
   security, access, retention enforcement, reservation behavior, or deployment
   materially, ask before locking in the choice. Otherwise use a documented
   default and state it.
3. **Plan narrowly.** Identify affected components, invariants, data migration
   needs, tests, and documentation. Make the smallest complete change.
   When documenting a schema or architecture, create a polished, accessible
   image diagram (prefer SVG) and embed it in the relevant documentation; do
   not use ASCII-art diagrams.
4. **Set the branch.** Before implementing a phase or feature, check the current
   Git branch. If on `main`, create a dedicated feature branch first. If already
   on a feature branch, keep using it; do not create another branch for each
   feature or phase. Do not create a feature branch from another non-feature
   branch; ask before switching or branching from that state.
5. **Implement.** Use Python for backend code and PostgreSQL for persistent
   application data. Follow existing project patterns; keep HTTP handling,
   domain rules, persistence, and UI responsibilities clear.
6. **Test every behavior change.** Add or update focused automated tests for
   success, validation, authorization, conflict/concurrency, and relevant edge
   cases. Run the narrowest applicable tests, then lint/type checks or builds
   affected by the change. Never claim checks passed unless they ran.
7. **Update documentation and tracking.** Update directly related setup/API/
   operational docs. Mark roadmap items complete only with implementation and
   verification evidence; do not treat a plan as completed work.
8. **Report.** Summarize changed behavior, decisions/assumptions, tests run and
   results, and remaining risks or follow-up work.

## Domain invariants

- An elevator may have no more than one outstanding custody record. An
  administratively cancelled loan remains outstanding until actual return.
- Checkout and return are server-authoritative, transactional state changes.
- Retrying or racing requests must not create duplicate outstanding custody
  records or silently overwrite another user's action.
- A returned loan retains its checkout and return timestamps and historical
  borrower/department/location snapshots.
- Any authenticated user account may return an outstanding custody record;
  record the return actor separately from the borrower. A typed borrower name
  is not proof of identity.
- There is no external identity provider. Admins create local username/password/
  role accounts; store strong password hashes and enforce roles server-side.
- Sign-in is required for borrowing, returning, and management actions. Keep the
  authenticated account actor distinct from a typed borrower display name.
- Admin-assigned initial passwords must be changed at first login. Never store
  or reveal plaintext passwords.
- Provide a separate manually run bootstrap script for the first two or more
  admin accounts; do not ship default admin credentials.
- All admins may access person-level history and exports; user-role access must
  not expose those details.
- Keep current borrower separate from physical location. A configured location
  is the default physical return location; "Site" is the available custodian
  label.
- Retiring or blocking an elevator does not delete its history.
- A QR token is an unguessable locator, not authorization. Admin operations
  require server-side authorization regardless of UI visibility.
- Keep admin corrections auditable; do not silently rewrite history.
- Immediate checkout is the default; future reservations are required and
  remain distinct from active loans. Admins configure duration, cancellation,
  expiry, and no-show rules; the initial minimum notice, maximum duration,
  cancellation cutoff, and no-show grace are seven days each. Reservations may
  be made while an elevator is on loan; if it is late at reservation time,
  alert the reservation user and suggest other available elevators.
- Admins may set/clear blocked status. Require a reason, audit transitions, and
  prevent new checkout/reservations while blocked.
- Blocking an elevator with an active loan administratively cancels the loan,
  but does not mean the elevator was returned. Keep the borrower as custodian
  and permit the actual return to close the cancelled loan. Do not allow another
  checkout until custody is closed.
- When blocking affects future reservations, alert owners on next login and
  suggest alternatives; if none are available, clearly state that the elevator
  is unavailable. Email notification is not part of the initial requirement.
- Run a daily job that deletes eligible completed loans/reservations and
  associated personal data after three years and audit events after three
  years; delete disabled-account details after three years when no active loan
  or unfulfilled reservation requires them. Retain active loans and unfulfilled
  reservations. Run cleanup after restoring backups before resuming service.
- Do not label a loan overdue until operations approves a threshold.

## Engineering expectations

- Prefer typed Python APIs, validation, explicit errors, and database-enforced
  constraints over client-side assumptions.
- Store instants in UTC; use the configured site time zone for display and
  report grouping.
- Keep secrets out of source, logs, images, and committed environment files.
- Collect only approved personal data and avoid exposing borrower details on a
  public QR page.
- Preserve accessible, mobile-first interactions and clear error/conflict
  states.
- Keep Docker/Kubernetes changes reproducible and use non-root, least-privilege
  defaults.
- Provide Dockerfile-based image builds and a Helm chart for a clean Kubernetes
  deployment independent of the company's existing platform.
- Seed the initial location as `Geel`, department as `Sites & Facilities`, and
  elevator as `LIFT-001`; use `Europe/Brussels` for application time-zone
  display and scheduling.
- Do not add a framework, dependency, abstraction, or scope that is not needed
  for the requested behavior.

## Before finishing

- Confirm the exact requirement is met and existing behavior remains intact.
- Run the relevant tests and checks and report failures honestly.
- Update the relevant roadmap status and docs if work was completed.
- Mention any unresolved product/security/privacy decision that blocks safe
  release.
