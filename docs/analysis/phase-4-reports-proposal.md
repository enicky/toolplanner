# Phase 4 — Reports and dashboard proposal

**Status:** Proposed for product-owner review; no report-page implementation is
included in this document change.

The current Reports page lists lifetime checkout totals and average completed
loan duration by elevator. The proposal below turns that page into an
aggregate-first operational dashboard while keeping person-level history in the
separate, admin-only export.

## Visual previews

These are illustrative desktop mockups, not screenshots of live data. Sample
values are for layout review only.

### Reports overview

![Proposed reports overview with filters, summary cards, checkout trend, usage ranking, custody age, and reservation outcomes](./assets/reports-overview-mockup.svg)

### Usage breakdowns

![Proposed reports breakdowns for elevator use, departments, checkout locations, and completed-loan duration](./assets/reports-breakdowns-mockup.svg)

## Recommended dashboard

### 1. Shared filters

- Default to the last 30 days, with daily buckets. Use weekly buckets for longer
  ranges and monthly buckets for multi-year views; allow an explicit day/week
  switch where it remains readable. The mockup uses a weekly bucket selection
  to keep the trend legible.
- Offer a custom start/end date and optional elevator, department, and checkout
  location filters.
- Keep selected filters in URL query parameters so an admin can bookmark or
  return to a view. Do not put borrower names or other person-level data in the
  URL.
- Interpret date boundaries and chart labels in `Europe/Brussels`; convert the
  selected local range to UTC for database queries, including daylight-saving
  transitions.
- Make the data basis clear: checkout activity is based on checkout time,
  completed-loan duration uses loans checked out in the selected period, and
  reservation outcomes use reservation start time. A live custody snapshot is
  explicitly labelled as "now" and is not constrained by the date range.

### 2. At-a-glance values

| Value | Definition |
| --- | --- |
| Checkouts in range | Loans with `checked_out_at` in the selected interval. A checkout is counted once, whether or not it has since been returned. |
| Average returned-loan duration | Average `returned_at - checked_out_at` for returned loans checked out in the selected interval. Exclude still-outstanding loans and show the completed-loan count alongside the average. |
| Currently in custody | Live count of all loans without a physical return, including administratively cancelled loans. Do not call these loans overdue. |
| Reservation pickup rate | Picked-up reservations divided by picked-up plus expired no-show reservations whose `starts_at` is in the selected interval. Exclude cancelled and not-yet-resolved reservations from this denominator. If the denominator is zero, show that there is not enough completed reservation data. |

Show a prior-period comparison only when both periods have enough data. A
comparison is secondary context, not a performance target.

### 3. Useful overview panels

1. **Checkout trend:** daily or weekly checkout counts. This helps identify
   changing demand and busy periods without counting QR scans as loans.
2. **Elevator use:** checkout counts by elevator for the selected period. It
   can identify demand concentration or low observed use; it must not imply
   equipment quality or employee performance.
3. **Current custody age:** counts in descriptive bands such as under 24 hours,
   1–3 days, 3–7 days, and 7 or more days. Include cancelled-but-unreturned
   loans. These are age bands only; no band is labelled or treated as overdue
   without an operations-approved threshold.
4. **Reservation outcomes:** picked up, expired as no-show, cancelled, and
   upcoming confirmed reservations. Keep upcoming reservations separate from
   the completed-outcome pickup-rate denominator.
5. **Checkout location and department:** aggregate loan counts by the physical
   pickup location and the department snapshot recorded at checkout. Do not
   break down by free-text destination in the first version.
6. **Completed-loan duration ranges:** returned loans grouped into broad
   duration bands, complementing the average with a distribution.

## Data and privacy boundaries

- The authenticated Reports route and all report APIs remain admin-only.
- Dashboard cards, trends, and breakdowns are aggregate by default. Do not show
  borrower names, usernames, reservation owners, or individual loan rows in
  the dashboard.
- Individual history remains available only through the separately labelled
  admin CSV export, with export auditing and spreadsheet-safe values.
- Apply all supported filters consistently to displayed aggregates and the
  filtered export. Keep the existing unrestricted history export clearly
  labelled if it remains available.
- Use `department_snapshot` for department breakdowns; it records the
  department name at checkout instead of reading the account's current
  department. The current schema stores checkout/return locations only by
  location ID; renaming a location can therefore change its displayed label in
  historical reports. Before implementing a location breakdown, either add and
  backfill immutable location-name snapshots or explicitly approve grouping
  history under the location's current name.
- Reservation records do not currently store department or location. Do not
  imply reservation breakdowns by those dimensions unless a reservation is
  linked to a completed loan and the chart explicitly reports loan data.
- Data remains subject to the approved three-year cleanup. Reports must not
  reconstruct or expose data after its retention eligibility.

## Implementation outline after approval

1. Add a filtered aggregate-report API with validated date and dimension
   filters; aggregate in the database rather than loading a capped list of
   individual loans into application memory.
2. Add the filter bar, KPI cards, and accessible charts/tables. Prefer chart
   forms that retain readable labels and do not rely on color alone.
3. Align the CSV export with the selected filters, preserve admin authorization,
   and audit exports.
4. Add API and frontend tests for role restrictions, empty data, date
   inclusivity and Brussels daylight-saving boundaries, each filter, cancelled
   outstanding custody, the reservation-rate denominator, and CSV/filter
   agreement.

No schema change appears necessary for checkout trends, elevator use,
department breakdowns, custody age, reservation outcomes, or loan-duration
bands. A trustworthy historical location label does require a snapshot
decision (and likely a schema migration). A database index or query-plan
adjustment may also be needed after measuring real data volume. The existing
usage endpoint currently reads a limited list of loan rows and returns
lifetime per-elevator totals; it should not be treated as the final
filtered-report API.

## Review requested

Please review the two visual previews and confirm whether this is the right
first release:

- Keep the last 30 days as the default date range.
- Include all six overview panels above, or identify any that should be
  deferred.
- Keep the live custody snapshot and descriptive age bands, without an overdue
  label.
- Keep person-level details exclusively in the separately labelled admin
  export.
- For historical location breakdowns, prefer immutable location-name snapshots
  over showing the current name for past checkouts.

The existing Phase 4 roadmap items for report filters, dashboards, and tests
remain open until the proposal is approved and implemented.
