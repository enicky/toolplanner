# Tool Planner decisions and open questions

The product and initial deployment decisions below have been confirmed by the
product owner. Environment-specific values are supplied by the infrastructure
owner through Helm configuration at deployment time.

## Confirmed decisions

| Area | Confirmed decision | Design consequence |
| --- | --- | --- |
| Scope | First deployment is for one Sanofi site. | No multi-site workflows are required for the initial release. |
| Authentication | There is no identity provider. Admins create users with a username, initial password, and role. | Use application-managed accounts and local login; require a password change on first login. |
| Admin bootstrap | Provide a separate script to be run manually to create the initial admin accounts. | Create at least two admins securely; do not ship default credentials in source or images. |
| Roles | Users and admins are required; all admins can view person-level history and export it. | Enforce user/admin authorization on the server and exports; retain at least two designated admins. |
| Borrower | A typed name is acceptable for checkout. | Keep borrower display name and authenticated account reference distinct if the submitted name differs. |
| Return | Any authenticated user account may return an elevator. | Record the return actor separately from the borrower. |
| Reservation | Immediate borrowing is the default, and future reservations are required. Reservation rules are admin-configurable. Initial minimum notice, maximum duration, cancellation cutoff, and no-show grace period are each seven days. | Configure each value independently in the admin UI. A reservation placed at the seven-day minimum notice cannot be cancelled under the seven-day cutoff. |
| Active-loan reservation | An elevator with an active loan can still be reserved. | If the loan is still active at reservation time, alert the reservation user and suggest alternatives available for the requested period. If none are available, alert that the elevator is not available. |
| Late return | If the elevator is not returned for a future reservation, notify the reservation owner in-app on next login; email may be added later. | Do not silently substitute or cancel the reservation. Show other available elevators when possible. |
| Retention | Retention is three years, checked by an automated task that runs daily. | Delete eligible completed loans/reservations and associated personal data three years after completion/return; delete audit events three years after their event time. Delete disabled-account details after three years disabled if no outstanding custody record or unfulfilled reservation requires them. |
| Backups | Backups may contain older records until their own lifecycle expires. | Run retention cleanup after restore and before normal service access; backup expiry is managed separately. |
| Location | Admins can configure a location as the default. Initial default location is `Geel`. | Keep exactly one current default physical location; default changes do not rewrite history. |
| Department | Initial department is `Sites & Facilities`. | Seed this department; admins can manage department data. |
| Inventory | Seed the first elevator with registration number/name `LIFT-001`. | Use `LIFT-001` as the initial display name until a different name is supplied. |
| Custody | Model active borrower separately from physical location; show "Site" as available custodian. | "Site" is a display/custody label, not a physical location entity or person. |
| Return location | Capture the return location when it differs from default. | Preserve checkout, intended destination, and return locations as distinct history fields. |
| Overdue reporting | Report loan age only until operations sets a threshold. | Do not label or escalate loans as overdue without an approved threshold. |
| Corrections | Append audited corrections and preserve original values, actor, and reason. | No silent edits to loan history. |
| Blocked status | Admins may set and clear a blocked/unavailable status with a reason. If a blocked elevator has an active loan, the loan must be cancelled. | Record an administrative cancellation with actor/time/reason; cancellation is not a physical return. Keep the borrower as custodian until actual return. Alert owners of affected future reservations on next login and suggest alternatives if available. |
| Reporting access | Aggregate by default; all admins may view person-level history and export it. | Reports and person-level details are admin-only; protect exports with the same authorization. |
| Hosting | Infrastructure will be provided by the product owner; do not use the company platform. | Deliver a Dockerfile for image creation and an environment-configurable Helm chart for Kubernetes deployment. |
| Devices/time zone | Support phones and iPads; use Brussels/Europe time. | Use `Europe/Brussels` for display, scheduling, and reports; store instants in UTC. |
| Browser support | Use modern mobile and desktop browsers. | Test current and previous major iOS/iPadOS Safari, Android Chrome, and desktop Chrome/Edge/Safari. |
| Language | Start in English. | English is the initial UI language. |

## Remaining questions

No product requirements remain unresolved at this stage. Cluster-specific
settings such as ingress host/class, namespace, secret references, and
PostgreSQL connection details will be provided through the configurable Helm
values when the deployment environment is prepared.

### Container image release automation

The product owner confirmed GHCR, `vMAJOR.MINOR.PATCH` release tags,
version-specific and commit-specific image tags, digest recording and
digest-pinned deployments, and ARM64 images for the Turing RK1. The repository
does not yet have a Git release tag; the first tag must be created deliberately.

| Area | Confirmed decision | Remaining follow-up |
| --- | --- | --- |
| Registry | Use GitHub Container Registry (GHCR). | Confirm package visibility and deployment-cluster pull access. Private packages need a cluster pull secret and Helm `imagePullSecrets` support. |
| Versioning | Use `vMAJOR.MINOR.PATCH`; publish version and full-commit-SHA tags, record digests, and prefer digest-pinned deployments. | Create the first release tag explicitly. Update Helm templates/values to accept digest references. |
| Platforms | Build `linux/arm64` images for the Turing RK1. | Validate both images on the RK1 and confirm the deployment OS/runtime. |

See [docker-image-ci-proposal.md](docker-image-ci-proposal.md) for the full
analysis and implementation acceptance criteria.

## Decision log

| Date | Decision | Owner | Rationale / follow-up |
| --- | --- | --- | --- |
| 2026-11-15 | Confirmed decisions listed above. | Product owner | Requirements supplied for the analysis; deployment values will be supplied through Helm configuration. |
| 2026-11-20 | Selected GHCR, `vMAJOR.MINOR.PATCH` releases, version and commit-specific tags, digest recording/pinning, and ARM64 images for the Turing RK1. | Product owner | Confirm package visibility and cluster pull access; add digest-aware Helm image references and validate on the target hardware before publishing. |
