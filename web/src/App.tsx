import { FormEvent, useCallback, useEffect, useMemo, useRef, useState, type ReactNode } from 'react'
import {
  Link,
  Navigate,
  NavLink,
  Route,
  Routes,
  useLocation,
} from 'react-router-dom'
import { brusselsTimeToIso } from './time'

type Account = {
  id: string
  username: string
  display_name: string
  department_id: string | null
  role: 'user' | 'admin'
  must_change_password: boolean
}

type ReservationPolicy = {
  minimum_notice_seconds: number
  maximum_duration_seconds: number
  cancellation_cutoff_seconds: number
  no_show_grace_seconds: number
  version: number
}

const reservationTimingFields: Array<
  [keyof Omit<ReservationPolicy, 'version'>, string]
> = [
  ['minimum_notice_seconds', 'Minimum notice'],
  ['maximum_duration_seconds', 'Maximum duration'],
  ['cancellation_cutoff_seconds', 'Cancellation cutoff'],
  ['no_show_grace_seconds', 'No-show grace'],
]

type Elevator = {
  id: string
  name: string
  registration_number: string
  status: string
  qr_url: string
  outstanding_borrower: string | null
}

type ElevatorModalAction = {
  type: 'edit-name' | 'block' | 'unblock' | 'retire' | 'rotate-qr'
  elevator: Pick<Elevator, 'id' | 'name' | 'registration_number'>
}

type SiteConfigAction = {
  type: 'edit-location' | 'delete-location' | 'edit-department' | 'delete-department'
  id: string
  name: string
  details?: string | null
}

type QRStatus = {
  name: string
  registration_number: string
  status: string
  elevator_status: string
  can_return: boolean
  can_borrow: boolean
}

type SelectOption = {
  id: string
  name: string
  is_default?: boolean
  is_active?: boolean
  details?: string | null
  elevator_count?: number
  active_user_count?: number
}

type NotificationItem = {
  id: string
  message: string
  read: boolean
  alternatives: Array<{ id: string; name: string; registration_number: string }>
}

type UserReservation = {
  id: string
  elevator_id: string
  elevator_name: string
  registration_number: string
  qr_token: string
  starts_at: string
  ends_at: string
  status: string
}

type AdminUser = {
  id: string
  username: string
  display_name: string
  department_id: string | null
  role: 'user' | 'admin'
  is_active: boolean
  must_change_password: boolean
}

type AdminReservation = {
  id: string
  elevator: string
  requester: string
  starts_at: string
  ends_at: string
  status: string
}

type UsageRow = {
  registration_number: string
  checkout_count: number
  average_duration_seconds: number | null
}

type AdminLoan = {
  id: string
  elevator_id: string
  registration_number: string
  borrower_name: string
  department: string
  checkout_location: string | null
  destination: string
  checked_out_at: string
  returned_at: string | null
  status: string
}

type AdminOverview = {
  available_count: number
  active_count: number
  outstanding_custody_count: number
  blocked_count: number
  retired_count: number
  at_risk_reservation_count: number
  oldest_custody: Array<{
    registration_number: string
    loan_age_seconds: number
    status: string
  }>
}

type AuditEntry = {
  id: string
  actor: string
  action: string
  entity_type: string
  entity_id: string
  reason: string | null
  occurred_at: string
}

async function api<T>(path: string, init: RequestInit = {}): Promise<T> {
  const headers = new Headers(init.headers)
  if (init.body && !headers.has('Content-Type')) {
    headers.set('Content-Type', 'application/json')
  }
  const method = (init.method ?? 'GET').toUpperCase()
  if (!['GET', 'HEAD', 'OPTIONS'].includes(method)) {
    const csrf = document.cookie
      .split('; ')
      .find((part) => part.startsWith('toolplanner_csrf='))
      ?.split('=')
      .slice(1)
      .join('=')
    if (csrf) headers.set('X-CSRF-Token', decodeURIComponent(csrf))
  }
  const response = await fetch(`/api/v1${path}`, {
    ...init,
    headers,
    credentials: 'include',
  })
  if (!response.ok) {
    const payload = (await response.json().catch(() => null)) as
      | { detail?: string }
      | null
    throw new Error(payload?.detail ?? `Request failed (${response.status}).`)
  }
  if (response.status === 204) return undefined as T
  return (await response.json()) as T
}

function localDefaultTime(days: number, hours = 0): string {
  const date = new Date(Date.now() + days * 86_400_000 + hours * 3_600_000)
  const parts = new Intl.DateTimeFormat('en-CA', {
    timeZone: 'Europe/Brussels',
    year: 'numeric',
    month: '2-digit',
    day: '2-digit',
    hour: '2-digit',
    minute: '2-digit',
    hourCycle: 'h23',
  }).formatToParts(date)
  const values = Object.fromEntries(parts.map((part) => [part.type, part.value]))
  return `${values.year}-${values.month}-${values.day}T${values.hour}:${values.minute}`
}

function formatBrussels(value: string): string {
  return new Intl.DateTimeFormat('en-GB', {
    dateStyle: 'medium',
    timeStyle: 'short',
    timeZone: 'Europe/Brussels',
  }).format(new Date(value))
}

function formatLoanAge(checkedOutAt: string): string {
  const elapsedMinutes = Math.max(0, Math.floor((Date.now() - Date.parse(checkedOutAt)) / 60_000))
  const days = Math.floor(elapsedMinutes / (60 * 24))
  const hours = Math.floor((elapsedMinutes - days * 60 * 24) / 60)
  const minutes = elapsedMinutes % 60
  if (days > 0) return `${days}d ${hours}h`
  if (hours > 0) return `${hours}h ${minutes}m`
  return `${minutes}m`
}

export default function App() {
  const location = useLocation()
  const qrToken = useMemo(() => {
    const match = location.pathname.match(/^\/qr\/([^/]+)\/?$/)
    return match?.[1] ? decodeURIComponent(match[1]) : null
  }, [location.pathname])
  const [account, setAccount] = useState<Account | null>(null)
  const [qrStatus, setQrStatus] = useState<QRStatus | null>(null)
  const [locations, setLocations] = useState<SelectOption[]>([])
  const [departments, setDepartments] = useState<SelectOption[]>([])
  const [notifications, setNotifications] = useState<NotificationItem[]>([])
  const [message, setMessage] = useState('')
  const [error, setError] = useState('')
  const [busy, setBusy] = useState(false)
  const adminRoute = account?.role === 'admin' && !qrToken

  const refresh = useCallback(async () => {
    if (qrToken) {
      try {
        setQrStatus(await api<QRStatus>(`/qr/${encodeURIComponent(qrToken)}`))
      } catch (e) {
        setError(e instanceof Error ? e.message : 'Unable to load elevator.')
      }
    }
    try {
      const current = await api<Account>('/me')
      setAccount(current)
      if (!current.must_change_password) {
        setNotifications(await api<NotificationItem[]>('/me/notifications'))
      } else {
        setNotifications([])
      }
    } catch {
      setAccount(null)
      setNotifications([])
    }
    try {
      setLocations(await api<SelectOption[]>('/locations'))
      setDepartments(await api<SelectOption[]>('/departments'))
    } catch {
      setLocations([])
      setDepartments([])
    }
  }, [qrToken])

  useEffect(() => {
    void refresh()
  }, [refresh])

  useEffect(() => {
    setMessage('')
    setError('')
  }, [location.pathname])

  async function runAction(action: () => Promise<unknown>) {
    setBusy(true)
    setError('')
    setMessage('')
    try {
      await action()
      setMessage('Done.')
      await refresh()
    } catch (e) {
      setError(e instanceof Error ? e.message : 'The request could not be completed.')
    } finally {
      setBusy(false)
    }
  }

  async function signOut() {
    await runAction(async () => {
      await api('/auth/logout', { method: 'POST' })
      setAccount(null)
    })
  }

  return (
    <div className="app-shell">
      <header className="topbar">
        {!adminRoute && (
          <Link className="brand" to="/" aria-label="Tool Planner home">
            <span className="brand-mark">T</span>
            <span>Tool Planner</span>
          </Link>
        )}
        <div className="topbar-meta">
          {!adminRoute && <span className="site-pill">Geel</span>}
          {account && <span className="account-name">{account.display_name}</span>}
          {account && (
            <button className="quiet-button" onClick={() => void signOut()} disabled={busy}>
              Sign out
            </button>
          )}
        </div>
      </header>

      <main className={adminRoute ? 'page admin-page' : 'page'}>
        {!adminRoute && (
          <section className="intro">
            <p className="eyebrow">{qrToken ? 'ELEVATOR ACCESS' : 'SITES & FACILITIES'}</p>
            <h1>{qrToken ? 'Borrow, reserve or return' : 'Equipment, ready when you need it.'}</h1>
            <p className="intro-copy">
              {qrToken
                ? 'Scan the label to see the elevator status and manage your checkout.'
                : 'A simple way to find and manage mobile elevators at the Geel site.'}
            </p>
          </section>
        )}

        {error && <div className="alert alert-error" role="alert">{error}</div>}
        {message && <div className="alert alert-success" role="status">{message}</div>}
        {notifications.map((notice) => (
          <div className="alert alert-warning notification" role="status" key={notice.id}>
            <div>
              <strong>{notice.message}</strong>
              {notice.alternatives.length > 0 ? (
                <span> Available alternatives: {notice.alternatives.map((item) => item.registration_number).join(', ')}.</span>
              ) : (
                <span> No alternative elevator is currently available.</span>
              )}
            </div>
            {!notice.read && (
              <button
                className="quiet-button"
                onClick={() => void runAction(() => api(`/me/notifications/${notice.id}/read`, { method: 'POST' }))}
              >
                Mark as read
              </button>
            )}
          </div>
        ))}

        {!account ? (
          <LoginForm
            busy={busy}
            onSubmit={(username, password) =>
              runAction(async () => {
                const result = await api<{ user: Account }>('/auth/login', {
                  method: 'POST',
                  body: JSON.stringify({ username, password }),
                })
                setAccount(result.user)
                await refresh()
              })
            }
          />
        ) : account.must_change_password ? (
          <ChangePasswordForm
            busy={busy}
            onSubmit={(currentPassword, newPassword) =>
              runAction(async () => {
                await api('/auth/change-password', {
                  method: 'POST',
                  body: JSON.stringify({
                    current_password: currentPassword,
                    new_password: newPassword,
                  }),
                })
                await refresh()
              })
            }
          />
        ) : qrToken ? (
          <QRWorkspace
            token={qrToken}
            status={qrStatus}
            account={account}
            locations={locations}
            departments={departments}
            busy={busy}
            runAction={runAction}
          />
        ) : account.role === 'admin' ? (
          <Routes>
            <Route
              path="/admin/*"
              element={
                <AdminWorkspace
                  departments={departments}
                  busy={busy}
                  runAction={runAction}
                  account={account}
                />
              }
            />
            <Route path="*" element={<Navigate to="/admin/overview" replace />} />
          </Routes>
        ) : location.pathname.startsWith('/admin') ? (
          <section className="panel" role="alert">
            <p className="eyebrow">ACCESS RESTRICTED</p>
            <h2>Administrator access is required</h2>
            <p className="muted">Your account does not have permission to view this page.</p>
            <Link className="text-link" to="/">Return to your home page</Link>
          </section>
        ) : (
          <UserHome runAction={runAction} />
        )}
      </main>
      {!adminRoute && (
        <footer className="footer">
          <span>Tool Planner</span>
          <span>Local time zone: Europe/Brussels</span>
        </footer>
      )}
    </div>
  )
}

function LoginForm({
  busy,
  onSubmit,
}: {
  busy: boolean
  onSubmit: (username: string, password: string) => Promise<void>
}) {
  const [username, setUsername] = useState('')
  const [password, setPassword] = useState('')
  return (
    <section className="panel auth-panel">
      <div>
        <p className="eyebrow">YOUR ACCOUNT</p>
        <h2>Sign in to continue</h2>
        <p className="muted">Use the account and password provided by an administrator.</p>
      </div>
      <form
        className="form-grid"
        onSubmit={(event) => {
          event.preventDefault()
          void onSubmit(username, password)
        }}
      >
        <label>
          Username
          <input autoComplete="username" value={username} onChange={(e) => setUsername(e.target.value)} required />
        </label>
        <label>
          Password
          <input
            type="password"
            autoComplete="current-password"
            value={password}
            onChange={(e) => setPassword(e.target.value)}
            required
          />
        </label>
        <button className="primary-button" disabled={busy}>Sign in</button>
      </form>
    </section>
  )
}

function ChangePasswordForm({
  busy,
  onSubmit,
}: {
  busy: boolean
  onSubmit: (current: string, next: string) => Promise<void>
}) {
  const [current, setCurrent] = useState('')
  const [next, setNext] = useState('')
  return (
    <section className="panel narrow-panel">
      <p className="eyebrow">SECURE YOUR ACCOUNT</p>
      <h2>Set a new password</h2>
      <p className="muted">Your administrator-issued password must be changed before continuing.</p>
      <form
        className="form-grid"
        onSubmit={(event) => {
          event.preventDefault()
          void onSubmit(current, next)
        }}
      >
        <label>
          Current password
          <input type="password" autoComplete="current-password" value={current} onChange={(e) => setCurrent(e.target.value)} required />
        </label>
        <label>
          New password
          <input type="password" autoComplete="new-password" minLength={12} value={next} onChange={(e) => setNext(e.target.value)} required />
          <span className="help-text">Use at least 12 characters.</span>
        </label>
        <button className="primary-button" disabled={busy}>Change password</button>
      </form>
    </section>
  )
}

function QRWorkspace({
  token,
  status,
  account,
  locations,
  departments,
  busy,
  runAction,
}: {
  token: string
  status: QRStatus | null
  account: Account
  locations: SelectOption[]
  departments: SelectOption[]
  busy: boolean
  runAction: (action: () => Promise<unknown>) => Promise<void>
}) {
  const [borrowerName, setBorrowerName] = useState(account.display_name)
  const [departmentId, setDepartmentId] = useState(account.department_id ?? departments[0]?.id ?? '')
  const [destination, setDestination] = useState('')
  const [pickupLocationId, setPickupLocationId] = useState(
    locations.find((location) => location.is_default)?.id ?? '',
  )
  const [returnLocationId, setReturnLocationId] = useState('')
  const [startsAt, setStartsAt] = useState(() => localDefaultTime(8))
  const [endsAt, setEndsAt] = useState(() => localDefaultTime(8, 2))
  const [reservation, setReservation] = useState(false)
  const [pickupReservation, setPickupReservation] = useState<UserReservation | null>(null)
  useEffect(() => {
    if (!departmentId && departments.length > 0) setDepartmentId(departments[0].id)
  }, [departmentId, departments])
  useEffect(() => {
    let active = true
    void api<UserReservation[]>('/me/reservations')
      .then((items) => {
        const now = Date.now()
        const current = items.find(
          (item) =>
            item.qr_token === token &&
            item.status === 'confirmed' &&
            Date.parse(item.starts_at) <= now &&
            Date.parse(item.ends_at) > now,
        )
        if (active) setPickupReservation(current ?? null)
      })
      .catch(() => {
        if (active) setPickupReservation(null)
      })
    return () => {
      active = false
    }
  }, [token])

  async function submit(event: FormEvent) {
    event.preventDefault()
    await runAction(async () => {
      if (pickupReservation) {
        await api(`/qr/${encodeURIComponent(token)}/checkout`, {
          method: 'POST',
          body: JSON.stringify({
            borrower_name: borrowerName,
            department_id: departmentId,
            destination,
            checkout_location_id: pickupLocationId || null,
            reservation_id: pickupReservation.id,
          }),
        })
      } else if (reservation) {
        const start = brusselsTimeToIso(startsAt)
        const end = brusselsTimeToIso(endsAt)
        await api(`/qr/${encodeURIComponent(token)}/reservations`, {
          method: 'POST',
          body: JSON.stringify({ borrower_name: borrowerName, starts_at: start, ends_at: end }),
        })
      } else {
        await api(`/qr/${encodeURIComponent(token)}/checkout`, {
          method: 'POST',
          body: JSON.stringify({
            borrower_name: borrowerName,
            department_id: departmentId,
            destination,
            checkout_location_id: pickupLocationId || null,
          }),
        })
      }
    })
  }

  if (!status) return <div className="panel muted">Loading elevator…</div>
  return (
    <div className="content-grid">
      <section className="panel elevator-card">
        <div className="elevator-title">
          <div>
            <p className="eyebrow">REGISTRATION {status.registration_number}</p>
            <h2>{status.name}</h2>
          </div>
          <span className={`status-pill status-${status.status}`}>{status.status.replace('_', ' ')}</span>
        </div>
        {status.can_borrow || pickupReservation ? (
          <form className="form-grid" onSubmit={(event) => void submit(event)}>
            <div className="segmented">
              <button type="button" className={!reservation ? 'selected' : ''} onClick={() => setReservation(false)}>Borrow now</button>
              <button type="button" className={reservation ? 'selected' : ''} onClick={() => setReservation(true)}>Reserve future time</button>
            </div>
            {pickupReservation && (
              <p className="notice">
                You have a reservation for this elevator now. Submitting will pick it up and start the loan.
              </p>
            )}
            <label>
              Borrower name
              <input value={borrowerName} onChange={(e) => setBorrowerName(e.target.value)} required maxLength={160} />
            </label>
            {!reservation && (
              <>
                <label>
                  Department
                  <select value={departmentId} onChange={(e) => setDepartmentId(e.target.value)} required>
                    <option value="">Choose a department</option>
                    {departments.map((department) => <option value={department.id} key={department.id}>{department.name}</option>)}
                  </select>
                </label>
                <label>
                  Pickup location
                  <select value={pickupLocationId} onChange={(e) => setPickupLocationId(e.target.value)}>
                    <option value="">Use default location</option>
                    {locations.map((location) => <option value={location.id} key={location.id}>{location.name}</option>)}
                  </select>
                </label>
                <label>
                  Destination / current location
                  <input value={destination} onChange={(e) => setDestination(e.target.value)} required maxLength={240} placeholder="Building, floor or area" />
                </label>
              </>
            )}
            {reservation && (
              <>
                <div className="two-columns">
                  <label>
                    Start (Brussels time)
                    <input type="datetime-local" value={startsAt} onChange={(e) => setStartsAt(e.target.value)} required />
                  </label>
                  <label>
                    End (Brussels time)
                    <input type="datetime-local" value={endsAt} onChange={(e) => setEndsAt(e.target.value)} required />
                  </label>
                </div>
                <p className="notice">
                  Minimum notice, maximum duration, cancellation cutoff and no-show grace are currently seven days each.
                </p>
              </>
            )}
            <button className="primary-button" disabled={busy || (reservation ? false : !departmentId)}>
              {pickupReservation ? 'Pick up reservation' : reservation ? 'Confirm reservation' : 'Borrow elevator'}
            </button>
          </form>
        ) : status.can_return ? (
          <form
            className="form-grid"
            onSubmit={(event) => {
              event.preventDefault()
              void runAction(() =>
                api(`/qr/${encodeURIComponent(token)}/return`, {
                  method: 'POST',
                  body: JSON.stringify({ return_location_id: returnLocationId || null }),
                }),
              )
            }}
          >
            <p className="muted">Any signed-in user can record the actual return.</p>
            <label>
              Return location
              <select value={returnLocationId} onChange={(e) => setReturnLocationId(e.target.value)}>
                <option value="">Default location (Geel)</option>
                {locations.map((location) => <option value={location.id} key={location.id}>{location.name}</option>)}
              </select>
            </label>
            <button className="primary-button" disabled={busy}>Return elevator</button>
          </form>
        ) : (
          <p className="muted">This elevator cannot be borrowed right now. Please contact an administrator.</p>
        )}
      </section>
      <aside className="panel info-card">
        <p className="eyebrow">HOW IT WORKS</p>
        <h3>One QR code, simple handover</h3>
        <ol>
          <li>Check the status and sign in.</li>
          <li>Borrow now or reserve a future time.</li>
          <li>Scan this code again when returning it.</li>
        </ol>
        <p className="help-text">Reservations may be affected if an earlier loan is not returned on time.</p>
      </aside>
    </div>
  )
}

function UserHome({
  runAction,
}: {
  runAction: (action: () => Promise<unknown>) => Promise<void>
}) {
  const [reservations, setReservations] = useState<UserReservation[]>([])
  const [loadError, setLoadError] = useState('')
  const refresh = useCallback(async () => {
    try {
      setReservations(await api<UserReservation[]>('/me/reservations'))
    } catch (e) {
      setLoadError(e instanceof Error ? e.message : 'Could not load reservations.')
    }
  }, [])
  useEffect(() => { void refresh() }, [refresh])
  return (
    <div className="admin-layout">
      <section className="panel">
        <p className="eyebrow">WELCOME</p>
        <h2>Scan an elevator QR code to get started</h2>
        <p className="muted">You can return an elevator even if someone else borrowed it.</p>
      </section>
      <section className="panel">
        <p className="eyebrow">YOUR BOOKINGS</p>
        <h2>Reservations</h2>
        {loadError && <p className="alert alert-error">{loadError}</p>}
        {reservations.length === 0 ? (
          <p className="muted">You have no reservations yet.</p>
        ) : (
          <div className="elevator-list">
            {reservations.map((item) => (
              <article className="elevator-row" key={item.id}>
                <div>
                  <strong>{item.elevator_name} · {item.registration_number}</strong>
                  <span className="muted">
                    {new Intl.DateTimeFormat('en-GB', { dateStyle: 'medium', timeStyle: 'short', timeZone: 'Europe/Brussels' }).format(new Date(item.starts_at))}
                    {' – '}
                    {new Intl.DateTimeFormat('en-GB', { dateStyle: 'medium', timeStyle: 'short', timeZone: 'Europe/Brussels' }).format(new Date(item.ends_at))}
                    {' · '}{item.status}
                  </span>
                </div>
                <div className="row-actions">
                  {item.status === 'confirmed' && (
                    <>
                      <a className="text-link" href={`/qr/${encodeURIComponent(item.qr_token)}`}>Open elevator</a>
                      <button className="quiet-button" onClick={() => void runAction(async () => {
                        await api(`/reservations/${item.id}/cancel`, { method: 'POST' })
                        await refresh()
                      })}>Cancel reservation</button>
                    </>
                  )}
                </div>
              </article>
            ))}
          </div>
        )}
      </section>
    </div>
  )
}

function AdminWorkspace({
  departments,
  busy,
  runAction,
  account,
}: {
  departments: SelectOption[]
  busy: boolean
  runAction: (action: () => Promise<unknown>) => Promise<void>
  account: Account
}) {
  const location = useLocation()
  const currentPage = location.pathname.split('/')[2] || 'overview'
  const [drawerOpen, setDrawerOpen] = useState(false)
  const [elevators, setElevators] = useState<Elevator[]>([])
  const [adminLocations, setAdminLocations] = useState<SelectOption[]>([])
  const [adminDepartments, setAdminDepartments] = useState<SelectOption[]>([])
  const [users, setUsers] = useState<AdminUser[]>([])
  const [loans, setLoans] = useState<AdminLoan[]>([])
  const [adminReservations, setAdminReservations] = useState<AdminReservation[]>([])
  const [auditEntries, setAuditEntries] = useState<AuditEntry[]>([])
  const [usage, setUsage] = useState<UsageRow[]>([])
  const [overview, setOverview] = useState<AdminOverview | null>(null)
  const [reservationSettings, setReservationSettings] = useState<ReservationPolicy>({
    minimum_notice_seconds: 604800,
    maximum_duration_seconds: 604800,
    cancellation_cutoff_seconds: 604800,
    no_show_grace_seconds: 604800,
    version: 1,
  })
  const [newName, setNewName] = useState('')
  const [registration, setRegistration] = useState('')
  const [inventorySearch, setInventorySearch] = useState('')
  const [inventoryStatus, setInventoryStatus] = useState('all')
  const [userSearch, setUserSearch] = useState('')
  const [newUser, setNewUser] = useState({ username: '', password: '', name: '', department_id: departments[0]?.id ?? '', role: 'user' as 'user' | 'admin' })
  const [resetTarget, setResetTarget] = useState<string | null>(null)
  const [resetPassword, setResetPassword] = useState('')
  const [newLocationName, setNewLocationName] = useState('')
  const [newDepartmentName, setNewDepartmentName] = useState('')
  const [locationsTab, setLocationsTab] = useState<'locations' | 'departments'>('locations')
  const [adminError, setAdminError] = useState('')
  const [adminLoading, setAdminLoading] = useState(false)
  const [modalAction, setModalAction] = useState<ElevatorModalAction | null>(null)
  const [modalBusy, setModalBusy] = useState(false)
  const [siteConfigAction, setSiteConfigAction] = useState<SiteConfigAction | null>(null)
  const [siteModalBusy, setSiteModalBusy] = useState(false)
  const locationTabRef = useRef<HTMLButtonElement>(null)
  const departmentTabRef = useRef<HTMLButtonElement>(null)
  const menuButtonRef = useRef<HTMLButtonElement>(null)
  const firstNavLinkRef = useRef<HTMLAnchorElement>(null)
  const sidebarRef = useRef<HTMLElement>(null)
  const pageHeadingRef = useRef<HTMLHeadingElement>(null)

  const loadAdminData = useCallback(async () => {
    setAdminLoading(true)
    try {
      setAdminError('')
      setOverview(null)
      setElevators([])
      setLoans([])
      setAdminReservations([])
      setUsers([])
      setUsage([])
      setAuditEntries([])
      switch (currentPage) {
        case 'overview':
          {
            const [nextOverview, nextLoans, nextReservations] = await Promise.all([
              api<AdminOverview>('/admin/overview'),
              api<AdminLoan[]>('/admin/loans'),
              api<AdminReservation[]>('/admin/reservations'),
            ])
            setOverview(nextOverview)
            setLoans(nextLoans)
            setAdminReservations(nextReservations)
          }
          break
        case 'inventory':
          setElevators(await api<Elevator[]>('/admin/elevators'))
          break
        case 'locations':
          {
            const [nextLocations, nextDepartments] = await Promise.all([
              api<SelectOption[]>('/admin/locations'),
              api<SelectOption[]>('/admin/departments'),
            ])
            setAdminLocations(nextLocations)
            setAdminDepartments(nextDepartments)
          }
          break
        case 'current-loans':
          setLoans(await api<AdminLoan[]>('/admin/loans'))
          break
        case 'reservations':
          setAdminReservations(await api<AdminReservation[]>('/admin/reservations'))
          break
        case 'users':
          setUsers(await api<AdminUser[]>('/admin/users'))
          break
        case 'reservation-rules':
          setReservationSettings(await api<ReservationPolicy>('/admin/reservation-settings'))
          break
        case 'reports':
          setUsage(await api<UsageRow[]>('/admin/reports/usage'))
          break
        case 'audit':
          setAuditEntries(await api<AuditEntry[]>('/admin/audit'))
          break
      }
    } catch (e) {
      setAdminError(e instanceof Error ? e.message : 'Could not load admin data.')
    } finally {
      setAdminLoading(false)
    }
  }, [currentPage])

  useEffect(() => { void loadAdminData() }, [loadAdminData])
  useEffect(() => {
    if (!newUser.department_id && departments.length > 0) {
      setNewUser((current) => ({ ...current, department_id: departments[0].id }))
    }
  }, [departments, newUser.department_id])
  const closeDrawer = useCallback((restoreFocus = false) => {
    setDrawerOpen(false)
    if (restoreFocus) window.requestAnimationFrame(() => menuButtonRef.current?.focus())
  }, [])
  const handleNavSelect = useCallback(() => {
    setDrawerOpen(false)
    window.requestAnimationFrame(() => pageHeadingRef.current?.focus())
  }, [])

  useEffect(() => {
    if (!drawerOpen) return
    window.requestAnimationFrame(() => firstNavLinkRef.current?.focus())
    const handleKeyDown = (event: KeyboardEvent) => {
      if (event.key === 'Escape') closeDrawer(true)
      if (event.key === 'Tab') {
        const focusable = sidebarRef.current?.querySelectorAll<HTMLElement>(
          'a[href], button:not([disabled])',
        )
        if (!focusable?.length) return
        const first = focusable[0]
        const last = focusable[focusable.length - 1]
        if (event.shiftKey && document.activeElement === first) {
          event.preventDefault()
          last.focus()
        } else if (!event.shiftKey && document.activeElement === last) {
          event.preventDefault()
          first.focus()
        }
      }
    }
    window.addEventListener('keydown', handleKeyDown)
    return () => window.removeEventListener('keydown', handleKeyDown)
  }, [closeDrawer, drawerOpen])

  const navGroups = [
    { label: 'Operations', items: [
      { path: 'inventory', label: 'Inventory' },
      { path: 'current-loans', label: 'Current loans' },
      { path: 'reservations', label: 'Reservations' },
    ] },
    { label: 'Administration', items: [
      { path: 'users', label: 'Users' },
      { path: 'locations', label: 'Locations & departments' },
      { path: 'reservation-rules', label: 'Reservation rules' },
    ] },
    { label: 'Insights', items: [
      { path: 'reports', label: 'Reports' },
      { path: 'audit', label: 'Audit activity' },
    ] },
  ]
  const routePages = [
    { path: 'overview', label: 'Overview', description: 'A concise view of equipment availability and reservation risk.' },
    { path: 'inventory', label: 'Inventory', description: 'Find elevators, manage QR labels, and control availability.' },
    { path: 'current-loans', label: 'Current loans', description: 'Review outstanding custody, including administratively cancelled loans.' },
    { path: 'reservations', label: 'Reservations', description: 'Review future bookings and reservations that may be at risk.' },
    { path: 'users', label: 'Users', description: 'Manage application accounts, roles, and initial passwords.' },
    { path: 'locations', label: 'Locations & departments', description: 'Maintain site configuration and the default physical location.' },
    { path: 'reservation-rules', label: 'Reservation rules', description: 'Configure the booking and cancellation time limits.' },
    { path: 'reports', label: 'Reports', description: 'Review aggregate usage and export authorized history.' },
    { path: 'audit', label: 'Audit activity', description: 'Inspect administrative and system events.' },
  ]
  const pageMetadata = routePages.find((page) => page.path === currentPage) ?? routePages[0]
  const currentLoans = loans.filter((loan) => loan.returned_at === null)

  async function submitElevatorAction(action: ElevatorModalAction, value: string): Promise<string | null> {
    setModalBusy(true)
    setAdminError('')
    try {
      switch (action.type) {
        case 'edit-name':
          await api(`/admin/elevators/${action.elevator.id}`, {
            method: 'PATCH',
            body: JSON.stringify({ name: value.trim() }),
          })
          break
        case 'block':
          await api(`/admin/elevators/${action.elevator.id}/block`, {
            method: 'POST',
            body: JSON.stringify({ reason: value.trim() }),
          })
          break
        case 'unblock':
          await api(`/admin/elevators/${action.elevator.id}/unblock`, {
            method: 'POST',
            body: JSON.stringify({ reason: value.trim() }),
          })
          break
        case 'retire':
          await api(`/admin/elevators/${action.elevator.id}/retire`, {
            method: 'POST',
            body: JSON.stringify({ reason: value.trim() }),
          })
          break
        case 'rotate-qr':
          await api(`/admin/elevators/${action.elevator.id}/rotate-qr`, { method: 'POST' })
          break
      }
      setModalAction(null)
      await loadAdminData()
      return null
    } catch (e) {
      return e instanceof Error ? e.message : 'The elevator update could not be completed.'
    } finally {
      setModalBusy(false)
    }
  }

  async function submitSiteConfigAction(
    action: SiteConfigAction,
    value: { name: string; details: string },
  ): Promise<string | null> {
    setSiteModalBusy(true)
    setAdminError('')
    try {
      if (action.type === 'edit-location') {
        await api(`/admin/locations/${action.id}`, {
          method: 'PATCH',
          body: JSON.stringify({ name: value.name, details: value.details || null }),
        })
      } else if (action.type === 'delete-location') {
        await api(`/admin/locations/${action.id}`, { method: 'DELETE' })
      } else if (action.type === 'edit-department') {
        await api(`/admin/departments/${action.id}`, {
          method: 'PATCH',
          body: JSON.stringify({ name: value.name }),
        })
      } else {
        await api(`/admin/departments/${action.id}`, { method: 'DELETE' })
      }
      setSiteConfigAction(null)
      await loadAdminData()
      return null
    } catch (e) {
      return e instanceof Error ? e.message : 'The site configuration update could not be completed.'
    } finally {
      setSiteModalBusy(false)
    }
  }

  function handleLocationsTabKey(event: React.KeyboardEvent<HTMLButtonElement>) {
    if (event.key !== 'ArrowLeft' && event.key !== 'ArrowRight' && event.key !== 'Home' && event.key !== 'End') return
    event.preventDefault()
    const nextTab = event.key === 'Home'
      ? 'locations'
      : event.key === 'End'
        ? 'departments'
        : locationsTab === 'locations'
          ? 'departments'
          : 'locations'
    setLocationsTab(nextTab)
    window.requestAnimationFrame(() => {
      (nextTab === 'locations' ? locationTabRef : departmentTabRef).current?.focus()
    })
  }

  const inventoryPage = (
    <section className="panel">
      <div className="section-heading">
        <div><p className="eyebrow">INVENTORY</p><h2>Elevators</h2></div>
        <span className="count-badge">{elevators.length}</span>
      </div>
      <form className="form-grid" onSubmit={(event) => {
        event.preventDefault()
        void runAction(async () => {
          await api('/admin/elevators', {
            method: 'POST',
            body: JSON.stringify({ name: newName, registration_number: registration }),
          })
          setNewName('')
          setRegistration('')
          await loadAdminData()
        })
      }}>
        <div className="inline-form">
          <input aria-label="Elevator name" placeholder="Elevator name" value={newName} onChange={(e) => setNewName(e.target.value)} required />
          <input aria-label="Registration number" placeholder="Registration number" value={registration} onChange={(e) => setRegistration(e.target.value)} required />
          <button className="primary-button" disabled={busy}>Add elevator</button>
        </div>
      </form>
      <div className="filters-row">
        <label className="filter-search">Search elevators
          <input value={inventorySearch} onChange={(event) => setInventorySearch(event.target.value)} placeholder="Name or registration" />
        </label>
        <label className="filter-status">Status
          <select value={inventoryStatus} onChange={(event) => setInventoryStatus(event.target.value)}>
            <option value="all">All statuses</option>
            <option value="active">Active</option>
            <option value="blocked">Blocked</option>
            <option value="retired">Retired</option>
          </select>
        </label>
      </div>
      <div className="elevator-list">
        {elevators
          .filter((elevator) => `${elevator.name} ${elevator.registration_number}`.toLowerCase().includes(inventorySearch.toLowerCase()))
          .filter((elevator) => inventoryStatus === 'all' || elevator.status === inventoryStatus)
          .map((elevator) => (
            <article className="elevator-row" key={elevator.id}>
              <div>
                <strong>{elevator.name}</strong>
                <span className="muted">{elevator.registration_number} · {elevator.status}</span>
                {elevator.outstanding_borrower && <span className="muted">Custodian: {elevator.outstanding_borrower}</span>}
              </div>
              <div className="row-actions">
                <Link className="text-link" to={`/qr/${encodeURIComponent(elevator.qr_url.split('/').pop() ?? '')}`}>Open QR page</Link>
                <a className="text-link" href={`/api/v1/admin/elevators/${elevator.id}/qr-code`} target="_blank" rel="noreferrer">Print QR</a>
                <button className="quiet-button" onClick={() => setModalAction({
                  type: 'edit-name',
                  elevator: { id: elevator.id, name: elevator.name, registration_number: elevator.registration_number },
                })}>Edit name</button>
                <button className="quiet-button" onClick={() => setModalAction({
                  type: 'rotate-qr',
                  elevator: { id: elevator.id, name: elevator.name, registration_number: elevator.registration_number },
                })}>Rotate QR</button>
                {elevator.status === 'active' ? (
                  <button className="danger-button" onClick={() => setModalAction({
                    type: 'block',
                    elevator: { id: elevator.id, name: elevator.name, registration_number: elevator.registration_number },
                  })}>Block</button>
                ) : elevator.status === 'blocked' ? (
                  <button className="quiet-button" onClick={() => setModalAction({
                    type: 'unblock',
                    elevator: { id: elevator.id, name: elevator.name, registration_number: elevator.registration_number },
                  })}>Unblock</button>
                ) : null}
                {elevator.status !== 'retired' && (
                  <button className="danger-button" onClick={() => setModalAction({
                    type: 'retire',
                    elevator: { id: elevator.id, name: elevator.name, registration_number: elevator.registration_number },
                  })}>Retire</button>
                )}
              </div>
            </article>
          ))}
      </div>
    </section>
  )

  const usersPage = (
    <section className="panel">
      <p className="eyebrow">ACCOUNTS</p>
      <h2>User management</h2>
      <form className="form-grid" onSubmit={(event) => {
        event.preventDefault()
        void runAction(async () => {
          await api('/admin/users', {
            method: 'POST',
            body: JSON.stringify({
              username: newUser.username,
              initial_password: newUser.password,
              display_name: newUser.name,
              department_id: newUser.department_id || null,
              role: newUser.role,
            }),
          })
          setNewUser({ username: '', password: '', name: '', department_id: departments[0]?.id ?? '', role: 'user' })
          await loadAdminData()
        })
      }}>
        <div className="two-columns">
          <label>Username<input value={newUser.username} onChange={(e) => setNewUser({ ...newUser, username: e.target.value })} minLength={3} required /></label>
          <label>Display name<input value={newUser.name} onChange={(e) => setNewUser({ ...newUser, name: e.target.value })} required /></label>
          <label>Initial password<input type="password" value={newUser.password} onChange={(e) => setNewUser({ ...newUser, password: e.target.value })} minLength={12} required /></label>
          <label>Role<select value={newUser.role} onChange={(e) => setNewUser({ ...newUser, role: e.target.value as 'user' | 'admin' })}>
            <option value="user">User</option><option value="admin">Admin</option>
          </select></label>
          <label>Department<select value={newUser.department_id} onChange={(e) => setNewUser({ ...newUser, department_id: e.target.value })}>
            {departments.map((department) => <option value={department.id} key={department.id}>{department.name}</option>)}
          </select></label>
        </div>
        <button className="primary-button" disabled={busy}>Create account (password reset required)</button>
      </form>
      <div className="filters-row">
        <label className="filter-search">Search accounts
          <input value={userSearch} onChange={(event) => setUserSearch(event.target.value)} placeholder="Name or username" />
        </label>
      </div>
      <div className="elevator-list">
        {users.filter((user) => `${user.display_name} ${user.username}`.toLowerCase().includes(userSearch.toLowerCase())).map((user) => (
          <article className="elevator-row" key={user.id}>
            <div>
              <strong>{user.display_name} <span className="muted">@{user.username}</span></strong>
              <span className="muted">{user.role}{user.is_active ? '' : ' · disabled'}{user.must_change_password ? ' · password reset required' : ''}</span>
            </div>
            <div className="row-actions">
              <button className="quiet-button" onClick={() => {
                setResetTarget(resetTarget === user.id ? null : user.id)
                setResetPassword('')
              }}>Reset password</button>
              <button className="quiet-button" onClick={() => {
                const role = user.role === 'admin' ? 'user' : 'admin'
                void runAction(async () => {
                  await api(`/admin/users/${user.id}`, { method: 'PATCH', body: JSON.stringify({ role }) })
                  await loadAdminData()
                })
              }}>Make {user.role === 'admin' ? 'user' : 'admin'}</button>
              <button className="danger-button" onClick={() => void runAction(async () => {
                await api(`/admin/users/${user.id}`, { method: 'PATCH', body: JSON.stringify({ is_active: !user.is_active }) })
                await loadAdminData()
              })}>{user.is_active ? 'Disable' : 'Enable'}</button>
            </div>
            {resetTarget === user.id && (
              <form className="reset-password-form" onSubmit={(event) => {
                event.preventDefault()
                void runAction(async () => {
                  await api(`/admin/users/${user.id}/reset-password`, {
                    method: 'POST',
                    body: JSON.stringify({ initial_password: resetPassword }),
                  })
                  setResetTarget(null)
                  setResetPassword('')
                  await loadAdminData()
                })
              }}>
                <label>New initial password for {user.username}
                  <input type="password" autoComplete="new-password" minLength={12} value={resetPassword} onChange={(e) => setResetPassword(e.target.value)} required />
                </label>
                <button className="quiet-button" disabled={busy}>Assign password</button>
              </form>
            )}
          </article>
        ))}
      </div>
    </section>
  )

  const locationsPage = (
    <section className="panel">
      <p className="eyebrow">SITE CONFIGURATION</p>
      <h2>Locations &amp; departments</h2>
      <div className="site-tabs" role="tablist" aria-label="Site configuration">
        <button ref={locationTabRef} type="button" role="tab" id="locations-tab" aria-controls="locations-panel"
          aria-selected={locationsTab === 'locations'} tabIndex={locationsTab === 'locations' ? 0 : -1}
          className={`site-tab${locationsTab === 'locations' ? ' active' : ''}`}
          onKeyDown={handleLocationsTabKey} onClick={() => setLocationsTab('locations')}>Locations</button>
        <button ref={departmentTabRef} type="button" role="tab" id="departments-tab" aria-controls="departments-panel"
          aria-selected={locationsTab === 'departments'} tabIndex={locationsTab === 'departments' ? 0 : -1}
          className={`site-tab${locationsTab === 'departments' ? ' active' : ''}`}
          onKeyDown={handleLocationsTabKey} onClick={() => setLocationsTab('departments')}>Departments</button>
      </div>
      {locationsTab === 'locations' ? (
        <section id="locations-panel" role="tabpanel" aria-labelledby="locations-tab" className="site-tab-panel">
          <div className="site-panel-intro">
            <div>
              <h3>Physical locations</h3>
              <p className="muted">The default location is used when no different return location is selected.</p>
            </div>
            <span className="count-badge">{adminLocations.filter((item) => item.is_active).length} active</span>
          </div>
          <form className="inline-form" onSubmit={(event) => {
            event.preventDefault()
            void runAction(async () => {
              await api('/admin/locations', {
                method: 'POST',
                body: JSON.stringify({ name: newLocationName, is_default: adminLocations.every((item) => !item.is_active) }),
              })
              setNewLocationName('')
              await loadAdminData()
            })
          }}>
            <label className="site-create-field">New location name<input value={newLocationName} onChange={(e) => setNewLocationName(e.target.value)} required /></label>
            <button className="primary-button">Add location</button>
          </form>
          <div className="site-config-list">
            {adminLocations.length === 0 && <p className="muted">No locations configured yet.</p>}
            {adminLocations.map((item) => (
              <article className="elevator-row site-config-row" key={item.id}>
                <div>
                  <strong>{item.name}</strong>
                  <div className="site-config-meta">
                    <span className={`table-status${item.is_active ? '' : ' archived-status'}`}>{item.is_active ? item.is_default ? 'Default' : 'Active' : 'Archived'}</span>
                    <span className="muted">{item.elevator_count ?? 0} non-retired elevators assigned</span>
                    {item.details && <span className="muted">{item.details}</span>}
                  </div>
                </div>
                <div className="row-actions">
                  {item.is_active && !item.is_default && <button className="quiet-button" onClick={() => void runAction(async () => {
                    await api(`/admin/locations/${item.id}/set-default`, { method: 'POST' })
                    await loadAdminData()
                  })}>Set as default</button>}
                  {item.is_active ? (
                    <>
                      <button className="quiet-button" onClick={() => setSiteConfigAction({ type: 'edit-location', id: item.id, name: item.name, details: item.details })}>Edit</button>
                      <button className="danger-button" disabled={item.is_default || (item.elevator_count ?? 0) > 0}
                        title={item.is_default ? 'Set another default location before deleting this one.' : (item.elevator_count ?? 0) > 0 ? 'Move non-retired elevators to another location first.' : undefined}
                        onClick={() => setSiteConfigAction({ type: 'delete-location', id: item.id, name: item.name, details: item.details })}>Delete</button>
                    </>
                  ) : (
                    <button className="quiet-button" onClick={() => void runAction(async () => {
                      await api(`/admin/locations/${item.id}/restore`, { method: 'POST' })
                      await loadAdminData()
                    })}>Restore</button>
                  )}
                </div>
              </article>
            ))}
          </div>
          <p className="help-text">Delete archives a location instead of removing references from historical loans. Change the default before deleting its current location.</p>
        </section>
      ) : (
        <section id="departments-panel" role="tabpanel" aria-labelledby="departments-tab" className="site-tab-panel">
          <div className="site-panel-intro">
            <div>
              <h3>Departments</h3>
              <p className="muted">Departments are captured in loan history as snapshots.</p>
            </div>
            <span className="count-badge">{adminDepartments.filter((item) => item.is_active).length} active</span>
          </div>
          <form className="inline-form" onSubmit={(event) => {
            event.preventDefault()
            void runAction(async () => {
              await api('/admin/departments', { method: 'POST', body: JSON.stringify({ name: newDepartmentName }) })
              setNewDepartmentName('')
              await loadAdminData()
            })
          }}>
            <label className="site-create-field">New department name<input value={newDepartmentName} onChange={(e) => setNewDepartmentName(e.target.value)} required /></label>
            <button className="primary-button">Add department</button>
          </form>
          <div className="site-config-list">
            {adminDepartments.length === 0 && <p className="muted">No departments configured yet.</p>}
            {adminDepartments.map((department) => (
              <article className="elevator-row site-config-row" key={department.id}>
                <div>
                  <strong>{department.name}</strong>
                  <span className={`table-status${department.is_active ? '' : ' archived-status'}`}>{department.is_active ? 'Active' : 'Archived'}</span>
                  <span className="muted">{department.active_user_count ?? 0} active users assigned</span>
                </div>
                <div className="row-actions">
                  {department.is_active ? (
                    <>
                      <button className="quiet-button" onClick={() => setSiteConfigAction({ type: 'edit-department', id: department.id, name: department.name })}>Edit</button>
                      <button className="danger-button" disabled={(department.active_user_count ?? 0) > 0}
                        title={(department.active_user_count ?? 0) > 0 ? 'Reassign active users to another department first.' : undefined}
                        onClick={() => setSiteConfigAction({ type: 'delete-department', id: department.id, name: department.name })}>Delete</button>
                    </>
                  ) : (
                    <button className="quiet-button" onClick={() => void runAction(async () => {
                      await api(`/admin/departments/${department.id}/restore`, { method: 'POST' })
                      await loadAdminData()
                    })}>Restore</button>
                  )}
                </div>
              </article>
            ))}
          </div>
          <p className="help-text">Deleting archives the department. Existing user accounts and historical loans keep their department reference.</p>
        </section>
      )}
    </section>
  )

  const reservationRulesPage = (
    <section className="panel narrow-panel">
      <p className="eyebrow">RESERVATION POLICY</p>
      <h2>Timing rules</h2>
      <p className="muted">Each value is configurable independently. Initial values are seven days.</p>
      <form className="form-grid" onSubmit={(event) => {
        event.preventDefault()
        void runAction(async () => {
          await api('/admin/reservation-settings', {
            method: 'PATCH',
            body: JSON.stringify({
              minimum_notice_seconds: reservationSettings.minimum_notice_seconds,
              maximum_duration_seconds: reservationSettings.maximum_duration_seconds,
              cancellation_cutoff_seconds: reservationSettings.cancellation_cutoff_seconds,
              no_show_grace_seconds: reservationSettings.no_show_grace_seconds,
            }),
          })
          await loadAdminData()
        })
      }}>
        {reservationTimingFields.map(([key, label]) => (
          <label key={key}>{label} (days)
            <input type="number" min={0} step={1} value={Math.round(reservationSettings[key] / 86400)}
              onChange={(e) => setReservationSettings({ ...reservationSettings, [key]: Number(e.target.value) * 86400 })} />
          </label>
        ))}
        <div className="notice">A reservation made exactly at the minimum notice cannot be cancelled when the cancellation cutoff is also seven days.</div>
        <button className="primary-button" disabled={busy}>Save reservation rules</button>
      </form>
    </section>
  )

  const reportsPage = (
    <div className="admin-page-stack">
      <section className="panel">
        <div className="section-heading">
          <div><p className="eyebrow">AGGREGATE USAGE</p><h2>Elevator usage</h2></div>
          <a className="primary-button text-button" href="/api/v1/admin/reports/loans.csv">Export loan history CSV</a>
        </div>
        {usage.length === 0 ? <p className="muted">No checkout history is available yet.</p> : (
          <div className="elevator-list">
            {usage.map((row) => (
              <article className="elevator-row" key={row.registration_number}>
                <strong>{row.registration_number}</strong>
                <span className="muted">{row.checkout_count} checkouts · average returned-loan duration {row.average_duration_seconds === null ? 'not available' : `${Math.round(row.average_duration_seconds / 3600)} hours`}</span>
              </article>
            ))}
          </div>
        )}
        <p className="help-text">Loan age is shown without an overdue label until operations configures a threshold.</p>
      </section>
    </div>
  )

  const overviewPage = (
    <div className="admin-page-stack">
      <section className="metrics-grid">
        <MetricCard label="Available elevators" value={overview?.available_count ?? 0} detail={`${overview?.active_count ?? 0} active · ${overview?.blocked_count ?? 0} blocked · ${overview?.retired_count ?? 0} retired`} />
        <MetricCard label="Outstanding custody" value={overview?.outstanding_custody_count ?? 0} detail="Includes cancelled loans not physically returned" />
        <MetricCard label="Reservations at risk" value={overview?.at_risk_reservation_count ?? 0} detail="Reservation start has arrived but may not be fulfilled" />
      </section>
      <div className="dashboard-grid">
        <section className="panel dashboard-loans">
          <div className="section-heading">
            <div><p className="eyebrow">LIVE CUSTODY</p><h2>Currently loaned</h2></div>
            <NavLink className="text-link" to="/admin/current-loans">View all loans</NavLink>
          </div>
          {currentLoans.length === 0 ? <p className="muted">No elevators are currently in custody.</p> : (
            <div className="data-table-wrap">
              <table className="data-table">
                <thead><tr><th>Elevator</th><th>Borrower</th><th>Location / destination</th><th>Checked out</th><th>Loan age</th></tr></thead>
                <tbody>
                  {[...currentLoans]
                    .sort((a, b) => Date.parse(a.checked_out_at) - Date.parse(b.checked_out_at))
                    .slice(0, 8)
                    .map((loan) => (
                      <tr key={loan.id}>
                        <td><strong>{loan.registration_number}</strong></td>
                        <td>{loan.borrower_name}</td>
                        <td>{loan.destination}{loan.checkout_location ? <span className="table-subtext">From {loan.checkout_location}</span> : null}</td>
                        <td>{formatBrussels(loan.checked_out_at)}</td>
                        <td>{formatLoanAge(loan.checked_out_at)}<span className="table-subtext">{loan.status}</span></td>
                      </tr>
                    ))}
                </tbody>
              </table>
            </div>
          )}
          <p className="help-text">Loan age is not classified as overdue unless operations configures a threshold.</p>
        </section>
        <div className="dashboard-side">
          <section className="panel">
            <div className="section-heading">
              <div><p className="eyebrow">PICKUP RISK</p><h2>At-risk reservations</h2></div>
              <NavLink className="text-link" to="/admin/reservations">View reservations</NavLink>
            </div>
            {(overview?.at_risk_reservation_count ?? 0) === 0
              ? <p className="muted">No reservation pickups are currently at risk.</p>
              : <p className="risk-count"><strong>{overview?.at_risk_reservation_count}</strong> reservation pickups need attention.</p>}
            <p className="help-text">Owners receive an in-app alert at next login. Email is not enabled.</p>
          </section>
          <section className="panel">
            <div className="section-heading">
              <div><p className="eyebrow">COMING UP</p><h2>Next reservations</h2></div>
              <NavLink className="text-link" to="/admin/reservations">See all</NavLink>
            </div>
            {adminReservations.filter((item) => item.status === 'confirmed' && Date.parse(item.ends_at) >= Date.now()).length === 0 ? (
              <p className="muted">No upcoming reservations.</p>
            ) : (
              <div className="elevator-list">
                {adminReservations
                  .filter((item) => item.status === 'confirmed' && Date.parse(item.ends_at) >= Date.now())
                  .sort((a, b) => Date.parse(a.starts_at) - Date.parse(b.starts_at))
                  .slice(0, 5)
                  .map((item) => (
                    <article className="elevator-row" key={item.id}>
                      <div><strong>{item.elevator}</strong><span className="muted">{item.requester}</span></div>
                      <span className="muted">{formatBrussels(item.starts_at)}</span>
                    </article>
                  ))}
              </div>
            )}
          </section>
        </div>
      </div>
    </div>
  )

  const currentLoansPage = (
    <section className="panel">
      <p className="eyebrow">CUSTODY</p>
      <h2>Current loans</h2>
      <p className="muted">Cancelled loans remain outstanding until an actual physical return is recorded.</p>
      {currentLoans.length === 0 ? <p className="muted">No elevators are in custody.</p> : (
        <div className="data-table-wrap">
          <table className="data-table">
            <thead><tr><th>Elevator</th><th>Borrower</th><th>Department</th><th>Checked out</th><th>Age</th><th>Status</th></tr></thead>
            <tbody>{currentLoans.map((loan) => (
              <tr key={loan.id}>
                <td>{loan.registration_number}</td>
                <td>{loan.borrower_name}</td><td>{loan.department}</td>
                <td>{formatBrussels(loan.checked_out_at)}</td><td>{formatLoanAge(loan.checked_out_at)}</td>
                <td><span className="table-status">{loan.status}</span></td>
              </tr>
            ))}</tbody>
          </table>
        </div>
      )}
    </section>
  )

  const reservationsPage = (
    <section className="panel">
      <p className="eyebrow">SCHEDULING</p>
      <h2>Reservations</h2>
      {adminReservations.length === 0 ? <p className="muted">No reservations have been created.</p> : (
        <div className="data-table-wrap">
          <table className="data-table">
            <thead><tr><th>Elevator</th><th>Requester</th><th>Starts (Brussels)</th><th>Ends (Brussels)</th><th>Status</th></tr></thead>
            <tbody>{adminReservations.map((reservation) => (
              <tr key={reservation.id}>
                <td>{reservation.elevator}</td><td>{reservation.requester}</td>
                <td>{formatBrussels(reservation.starts_at)}</td><td>{formatBrussels(reservation.ends_at)}</td>
                <td><span className="table-status">{reservation.status}</span></td>
              </tr>
            ))}</tbody>
          </table>
        </div>
      )}
    </section>
  )

  const auditPage = (
    <section className="panel">
      <p className="eyebrow">ACCOUNTABILITY</p>
      <h2>Audit activity</h2>
      {auditEntries.length === 0 ? <p className="muted">No audit activity has been recorded.</p> : (
        <div className="data-table-wrap">
          <table className="data-table">
            <thead><tr><th>When (Brussels)</th><th>Actor</th><th>Action</th><th>Record</th><th>Reason</th></tr></thead>
            <tbody>{auditEntries.map((item) => (
              <tr key={item.id}>
                <td>{formatBrussels(item.occurred_at)}</td><td>{item.actor}</td>
                <td>{item.action.replaceAll('_', ' ')}</td><td>{item.entity_type} · {item.entity_id}</td>
                <td>{item.reason ?? '—'}</td>
              </tr>
            ))}</tbody>
          </table>
        </div>
      )}
    </section>
  )

  const pages: Record<string, ReactNode> = {
    overview: overviewPage,
    inventory: inventoryPage,
    'current-loans': currentLoansPage,
    reservations: reservationsPage,
    users: usersPage,
    locations: locationsPage,
    'reservation-rules': reservationRulesPage,
    reports: reportsPage,
    audit: auditPage,
  }

  return (
    <div className="admin-shell">
      {drawerOpen && (
        <button className="admin-nav-backdrop" aria-label="Close admin navigation" onClick={() => closeDrawer(true)} />
      )}
      <aside
        ref={sidebarRef}
        className={`admin-sidebar${drawerOpen ? ' is-open' : ''}`}
        aria-label="Administrator navigation"
        aria-modal={drawerOpen ? true : undefined}
        id="admin-navigation"
        role={drawerOpen ? 'dialog' : undefined}
      >
        <div className="admin-sidebar-brand">
          <span className="brand-mark" aria-hidden="true">T</span>
          <span><strong>Tool Planner</strong><small>Geel site</small></span>
        </div>
        <nav className="admin-nav">
          <NavLink
            ref={firstNavLinkRef}
            to="/admin/overview"
            end
            className={({ isActive }) => `admin-nav-link${isActive ? ' active' : ''}`}
            onClick={handleNavSelect}
          >
            <span className="nav-indicator" aria-hidden="true" />Overview
          </NavLink>
          {navGroups.map((group) => (
            <section className="admin-nav-group" key={group.label} aria-label={group.label}>
              <h2>{group.label}</h2>
              {group.items.map((item) => (
                <NavLink
                  key={item.path}
                  to={`/admin/${item.path}`}
                  className={({ isActive }) => `admin-nav-link${isActive ? ' active' : ''}`}
                  onClick={handleNavSelect}
                >
                  <span className="nav-indicator" aria-hidden="true" />{item.label}
                </NavLink>
              ))}
            </section>
          ))}
          <div className="admin-sidebar-account">
            <span className="account-avatar" aria-hidden="true">{account.display_name.slice(0, 1).toUpperCase()}</span>
            <span><strong>{account.display_name}</strong><small>Administrator</small></span>
          </div>
        </nav>
      </aside>
      <section className="admin-main">
        <div className="admin-mobile-bar">
          <button
            ref={menuButtonRef}
            className="admin-menu-toggle"
            aria-label="Open admin navigation"
            aria-expanded={drawerOpen}
            aria-controls="admin-navigation"
            onClick={() => setDrawerOpen(true)}
          >
            <span aria-hidden="true">☰</span>
          </button>
          <span>Administration</span>
          <span className="site-pill">Geel</span>
        </div>
        <header className="admin-page-heading">
          <p className="eyebrow">ADMINISTRATION / {pageMetadata.label.toUpperCase()}</p>
          <h1 ref={pageHeadingRef} tabIndex={-1}>{pageMetadata.label}</h1>
          <p className="muted">{pageMetadata.description}</p>
        </header>
        {adminError && <div className="alert alert-error" role="alert">{adminError}</div>}
        {adminLoading && <div className="admin-loading" role="status">Loading {pageMetadata.label.toLowerCase()}…</div>}
        <Routes>
          <Route index element={<Navigate to="/admin/overview" replace />} />
          <Route path="overview" element={pages.overview} />
          <Route path="inventory" element={pages.inventory} />
          <Route path="current-loans" element={pages['current-loans']} />
          <Route path="reservations" element={pages.reservations} />
          <Route path="users" element={pages.users} />
          <Route path="locations" element={pages.locations} />
          <Route path="reservation-rules" element={pages['reservation-rules']} />
          <Route path="reports" element={pages.reports} />
          <Route path="audit" element={pages.audit} />
          <Route path="*" element={<Navigate to="/admin/overview" replace />} />
        </Routes>
      </section>
      <ElevatorActionModal
        action={modalAction}
        busy={modalBusy}
        onClose={() => setModalAction(null)}
        onConfirm={(value) => modalAction ? submitElevatorAction(modalAction, value) : Promise.resolve(null)}
      />
      <SiteConfigModal
        action={siteConfigAction}
        busy={siteModalBusy}
        onClose={() => setSiteConfigAction(null)}
        onConfirm={(value) => siteConfigAction ? submitSiteConfigAction(siteConfigAction, value) : Promise.resolve(null)}
      />
    </div>
  )
}

function ElevatorActionModal({
  action,
  busy,
  onClose,
  onConfirm,
}: {
  action: ElevatorModalAction | null
  busy: boolean
  onClose: () => void
  onConfirm: (value: string) => Promise<string | null>
}) {
  const dialogRef = useRef<HTMLDialogElement>(null)
  const [value, setValue] = useState('')
  const [error, setError] = useState('')

  useEffect(() => {
    const dialog = dialogRef.current
    if (!dialog) return
    setError('')
    if (action) {
      setValue(action.type === 'edit-name' ? action.elevator.name : '')
      if (!dialog.open) dialog.showModal()
    } else if (dialog.open) {
      dialog.close()
    }
    return () => {
      if (dialog.open) dialog.close()
    }
  }, [action])

  if (!action) return <dialog ref={dialogRef} className="admin-modal-dialog" />

  const isReasonRequired = action.type === 'block' || action.type === 'unblock' || action.type === 'retire'
  const isNameEdit = action.type === 'edit-name'
  const title = {
    'edit-name': 'Edit elevator name',
    block: 'Block elevator',
    unblock: 'Unblock elevator',
    retire: 'Retire elevator',
    'rotate-qr': 'Rotate QR code',
  }[action.type]
  const confirmLabel = {
    'edit-name': 'Save name',
    block: 'Block elevator',
    unblock: 'Unblock elevator',
    retire: 'Retire elevator',
    'rotate-qr': 'Rotate QR code',
  }[action.type]

  async function submit(event: FormEvent) {
    event.preventDefault()
    if ((isReasonRequired || isNameEdit) && !value.trim()) return
    setError('')
    const result = await onConfirm(value)
    if (result) setError(result)
  }

  return (
    <dialog
      ref={dialogRef}
      className="admin-modal-dialog"
      aria-labelledby="elevator-modal-title"
      aria-describedby="elevator-modal-description"
      onCancel={(event) => {
        event.preventDefault()
        onClose()
      }}
      onClick={(event) => {
        if (event.target === event.currentTarget && !busy) onClose()
      }}
    >
      <div className="admin-modal-card">
        <header className="admin-modal-header">
          <div>
            <p className="eyebrow">{action.elevator.registration_number}</p>
            <h2 id="elevator-modal-title">{title}</h2>
          </div>
          <button type="button" className="modal-close" aria-label="Close dialog" disabled={busy} onClick={onClose}>×</button>
        </header>
        <form className="admin-modal-form" onSubmit={(event) => void submit(event)}>
          <div className="admin-modal-body">
            <p id="elevator-modal-description">
              {action.type === 'block' && 'New checkouts and reservations will be prevented. Any outstanding loan will be administratively cancelled, but custody remains with the borrower until actual return.'}
              {action.type === 'retire' && 'This elevator will be removed from active use. It cannot be retired until all outstanding custody has been physically returned.'}
              {action.type === 'unblock' && 'The elevator will become available for new operations after it is unblocked. Any outstanding custody still needs an actual return.'}
              {action.type === 'rotate-qr' && 'Rotating this QR code immediately invalidates the existing printed label. Print and replace the old label after confirming.'}
              {action.type === 'edit-name' && `Update the display name for ${action.elevator.registration_number}.`}
            </p>
            {isNameEdit && (
              <label>
                Elevator name
                <input autoFocus value={value} onChange={(event) => setValue(event.target.value)} maxLength={160} required />
              </label>
            )}
            {isReasonRequired && (
              <label>
                Reason
                <textarea autoFocus value={value} onChange={(event) => setValue(event.target.value)} maxLength={1000} rows={3} required />
              </label>
            )}
            {error && <div className="alert alert-error modal-error" role="alert">{error}</div>}
          </div>
          <footer className="admin-modal-footer">
            <button type="button" className="quiet-button" disabled={busy} onClick={onClose}>Cancel</button>
            <button
              type="submit"
              className={action.type === 'block' || action.type === 'retire' ? 'danger-button' : 'primary-button'}
              disabled={busy || ((isReasonRequired || isNameEdit) && !value.trim())}
            >
              {busy ? 'Saving…' : confirmLabel}
            </button>
          </footer>
        </form>
      </div>
    </dialog>
  )
}

function SiteConfigModal({
  action,
  busy,
  onClose,
  onConfirm,
}: {
  action: SiteConfigAction | null
  busy: boolean
  onClose: () => void
  onConfirm: (value: { name: string; details: string }) => Promise<string | null>
}) {
  const dialogRef = useRef<HTMLDialogElement>(null)
  const [name, setName] = useState('')
  const [details, setDetails] = useState('')
  const [error, setError] = useState('')
  const isEdit = action?.type === 'edit-location' || action?.type === 'edit-department'
  const isLocation = action?.type === 'edit-location' || action?.type === 'delete-location'

  useEffect(() => {
    const dialog = dialogRef.current
    if (!dialog) return
    setError('')
    if (action) {
      setName(action.name)
      setDetails(action.details ?? '')
      if (!dialog.open) dialog.showModal()
    } else if (dialog.open) {
      dialog.close()
    }
    return () => {
      if (dialog.open) dialog.close()
    }
  }, [action])

  if (!action) return <dialog ref={dialogRef} className="admin-modal-dialog" />

  const subject = isLocation ? 'location' : 'department'
  const title = isEdit ? `Edit ${subject}` : `Delete ${subject}`
  const confirmLabel = isEdit ? `Save ${subject}` : `Delete ${subject}`

  async function submit(event: FormEvent) {
    event.preventDefault()
    if (isEdit && !name.trim()) return
    setError('')
    const result = await onConfirm({ name, details })
    if (result) setError(result)
  }

  return (
    <dialog
      ref={dialogRef}
      className="admin-modal-dialog"
      aria-labelledby="site-config-modal-title"
      aria-describedby="site-config-modal-description"
      onCancel={(event) => {
        event.preventDefault()
        onClose()
      }}
      onClick={(event) => {
        if (event.target === event.currentTarget && !busy) onClose()
      }}
    >
      <div className="admin-modal-card">
        <header className="admin-modal-header">
          <div>
            <p className="eyebrow">SITE CONFIGURATION</p>
            <h2 id="site-config-modal-title">{title}</h2>
          </div>
          <button type="button" className="modal-close" aria-label="Close dialog" disabled={busy} onClick={onClose}>×</button>
        </header>
        <form className="admin-modal-form" onSubmit={(event) => void submit(event)}>
          <div className="admin-modal-body">
            <p id="site-config-modal-description">
              {isEdit
                ? `Update this ${subject}'s name${isLocation ? ' and details' : ''}. Historical records keep their saved snapshots.`
                : `This will remove the ${subject} from active selections. Existing accounts, elevators, and historical records keep their references; you can restore it later.`}
            </p>
            {isEdit && (
              <>
                <label>{subject === 'location' ? 'Location name' : 'Department name'}
                  <input autoFocus value={name} onChange={(event) => setName(event.target.value)} maxLength={120} required />
                </label>
                {isLocation && <label>Details (optional)
                  <input value={details} onChange={(event) => setDetails(event.target.value)} maxLength={240} />
                </label>}
              </>
            )}
            {error && <div className="alert alert-error modal-error" role="alert">{error}</div>}
          </div>
          <footer className="admin-modal-footer">
            <button type="button" className="quiet-button" disabled={busy} onClick={onClose}>Cancel</button>
            <button type="submit" className={isEdit ? 'primary-button' : 'danger-button'} disabled={busy || (isEdit && !name.trim())}>
              {busy ? 'Saving…' : confirmLabel}
            </button>
          </footer>
        </form>
      </div>
    </dialog>
  )
}

function MetricCard({ label, value, detail }: { label: string; value: number; detail: string }) {
  return (
    <article className="metric-card">
      <div className="metric-value">{value}</div>
      <div className="metric-label">{label}</div>
      <div className="metric-detail">{detail}</div>
    </article>
  )
}
