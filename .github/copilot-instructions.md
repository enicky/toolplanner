# Tool Planner repository instructions

- For Tool Planner work, follow
  [the Tool Planner development skill](skills/tool-planner-development/SKILL.md):
  analyze the existing behavior and requirements first, implement narrowly, and
  add/run tests for behavior changes.
- The backend is to be implemented in Python and use PostgreSQL as its
  persistent datastore. The planned frontend is React with TypeScript unless an
  approved decision changes that choice.
- Treat `docs/analysis/README.md` as the product/architecture proposal,
  `docs/analysis/open-questions.md` as the decision register, and
  `docs/analysis/roadmap.md` as the implementation progress tracker.
- When creating or revising schemas or architecture, include a polished,
  accessible image diagram (prefer SVG) in the repository and embed it in the
  relevant documentation. Do not use ASCII-art diagrams.
- Before implementing a phase or feature, check the current Git branch. If on
  `main`, create a dedicated feature branch first. If already on a feature
  branch, continue there rather than creating another branch. Do not create a
  feature branch from another non-feature branch; ask before switching or
  branching from that state.
- Preserve the invariant that an elevator has at most one outstanding custody
  record, including an administratively cancelled loan that has not physically
  returned. Enforce state changes and authorization on the server and in the
  database where appropriate; the QR code is not an authorization credential.
- Preserve historical loan records. Record auditable corrections rather than
  silently rewriting past activity.
- Respect the confirmed scope: one site, app-managed username/password/role
  accounts, typed borrower names, three-year daily cleanup, English UI for
  phones/iPads, `Europe/Brussels`, and a clean Docker/Helm Kubernetes deployment
  outside the company platform. See the decision register for rollout details.
- There is no identity provider. Admins create and manage users; enforce `user`
  and `admin` roles server-side. All admins can view person-level history and
  export it. Sign-in is required for borrow/return. Record the authenticated
  account separately from any typed borrower name. Force a password change on
  first login after an admin assigns an initial password. Provide a separate,
  manually run script to bootstrap at least two admins without default
  credentials in source or images.
- Immediate checkout is the default, and future reservations are a required
  capability. Admins configure reservation rules; initial minimum notice,
  maximum duration, cancellation cutoff, and no-show grace are seven days each.
  Reservations may overlap an active loan; if it is late at reservation time,
  alert the reservation user and suggest other available elevators.
- Admins can set/clear blocked status; require a reason, audit each change, and
  prevent new checkout/reservations while blocked.
- Blocking an elevator with an active loan cancels that loan administratively;
  cancellation is not a physical return. Keep the borrower as custodian and
  allow the actual return to close the cancelled loan; do not allow new checkout
  until the outstanding custody record is returned.
- When a blocked elevator has future reservations, alert each reservation owner
  in-app on next login; suggest alternatives or show that the elevator is not
  available. Email alerts are a possible later enhancement.
- Run a daily job that deletes eligible completed loans/reservations and
  associated personal data after three years, and audit events after three
  years; delete disabled-account details after three years if no active loan or
  unfulfilled reservation requires them. Preserve active loans and unfulfilled
  reservations. Backups may retain older data until expiry; run cleanup after
  restore before reopening normal access.
- Seed the default location as `Geel` and the initial department as
  `Sites & Facilities`, and seed elevator `LIFT-001`. Use `Europe/Brussels`;
  test modern phone/iPad browsers and desktop admin browsers as specified in
  the analysis.
- The product owner provides infrastructure. Deliver a Dockerfile and
  configurable Helm chart; do not assume company-hosted platform services.
- Keep changes surgical, document directly related behavior, and report which
  tests/checks actually ran.
