import { FormEvent, useCallback, useEffect, useMemo, useState } from 'react'
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

type QRStatus = {
  name: string
  registration_number: string
  status: string
  elevator_status: string
  can_return: boolean
  can_borrow: boolean
}

type SelectOption = { id: string; name: string; is_default?: boolean }

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

export default function App() {
  const qrToken = useMemo(() => {
    const match = window.location.pathname.match(/^\/qr\/([^/]+)\/?$/)
    return match?.[1] ? decodeURIComponent(match[1]) : null
  }, [])
  const [account, setAccount] = useState<Account | null>(null)
  const [qrStatus, setQrStatus] = useState<QRStatus | null>(null)
  const [locations, setLocations] = useState<SelectOption[]>([])
  const [departments, setDepartments] = useState<SelectOption[]>([])
  const [notifications, setNotifications] = useState<NotificationItem[]>([])
  const [message, setMessage] = useState('')
  const [error, setError] = useState('')
  const [busy, setBusy] = useState(false)

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
        <a className="brand" href="/" aria-label="Tool Planner home">
          <span className="brand-mark">T</span>
          <span>Tool Planner</span>
        </a>
        <div className="topbar-meta">
          <span className="site-pill">Geel</span>
          {account && <span className="account-name">{account.display_name}</span>}
          {account && (
            <button className="quiet-button" onClick={() => void signOut()} disabled={busy}>
              Sign out
            </button>
          )}
        </div>
      </header>

      <main className="page">
        <section className="intro">
          <p className="eyebrow">{qrToken ? 'ELEVATOR ACCESS' : 'SITES & FACILITIES'}</p>
          <h1>{qrToken ? 'Borrow, reserve or return' : 'Equipment, ready when you need it.'}</h1>
          <p className="intro-copy">
            {qrToken
              ? 'Scan the label to see the elevator status and manage your checkout.'
              : 'A simple way to find and manage mobile elevators at the Geel site.'}
          </p>
        </section>

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
          <AdminWorkspace
            locations={locations}
            departments={departments}
            busy={busy}
            runAction={runAction}
          />
        ) : (
          <UserHome runAction={runAction} />
        )}
      </main>
      <footer className="footer">
        <span>Tool Planner</span>
        <span>Local time zone: Europe/Brussels</span>
      </footer>
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
  locations,
  departments,
  busy,
  runAction,
}: {
  locations: SelectOption[]
  departments: SelectOption[]
  busy: boolean
  runAction: (action: () => Promise<unknown>) => Promise<void>
}) {
  const [elevators, setElevators] = useState<Elevator[]>([])
  const [users, setUsers] = useState<AdminUser[]>([])
  const [adminReservations, setAdminReservations] = useState<AdminReservation[]>([])
  const [usage, setUsage] = useState<UsageRow[]>([])
  const [reservationSettings, setReservationSettings] = useState<ReservationPolicy>({
    minimum_notice_seconds: 604800,
    maximum_duration_seconds: 604800,
    cancellation_cutoff_seconds: 604800,
    no_show_grace_seconds: 604800,
    version: 1,
  })
  const [newName, setNewName] = useState('')
  const [registration, setRegistration] = useState('')
  const [newUser, setNewUser] = useState({ username: '', password: '', name: '', department_id: departments[0]?.id ?? '', role: 'user' as 'user' | 'admin' })
  const [resetTarget, setResetTarget] = useState<string | null>(null)
  const [resetPassword, setResetPassword] = useState('')
  const [newLocationName, setNewLocationName] = useState('')
  const [newDepartmentName, setNewDepartmentName] = useState('')
  const [adminError, setAdminError] = useState('')

  const loadAdminData = useCallback(async () => {
    try {
      setElevators(await api<Elevator[]>('/admin/elevators'))
      setReservationSettings(await api<ReservationPolicy>('/admin/reservation-settings'))
      setUsers(await api<AdminUser[]>('/admin/users'))
      setAdminReservations(await api<AdminReservation[]>('/admin/reservations'))
      setUsage(await api<UsageRow[]>('/admin/reports/usage'))
    } catch (e) {
      setAdminError(e instanceof Error ? e.message : 'Could not load admin data.')
    }
  }, [])
  useEffect(() => { void loadAdminData() }, [loadAdminData])
  useEffect(() => {
    if (!newUser.department_id && departments.length > 0) {
      setNewUser((current) => ({ ...current, department_id: departments[0].id }))
    }
  }, [departments, newUser.department_id])

  return (
    <div className="admin-layout">
      <section className="panel">
        <div className="section-heading">
          <div><p className="eyebrow">INVENTORY</p><h2>Elevators</h2></div>
          <span className="count-badge">{elevators.length}</span>
        </div>
        {adminError && <p className="alert alert-error">{adminError}</p>}
        <form
          className="inline-form"
          onSubmit={(event) => {
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
          }}
        >
          <input aria-label="Elevator name" placeholder="Elevator name" value={newName} onChange={(e) => setNewName(e.target.value)} required />
          <input aria-label="Registration number" placeholder="Registration number" value={registration} onChange={(e) => setRegistration(e.target.value)} required />
          <button className="primary-button" disabled={busy}>Add elevator</button>
        </form>
        <div className="elevator-list">
          {elevators.map((elevator) => (
            <article className="elevator-row" key={elevator.id}>
              <div>
                <strong>{elevator.name}</strong>
                <span className="muted">{elevator.registration_number} · {elevator.status}</span>
                {elevator.outstanding_borrower && <span className="muted">Custodian: {elevator.outstanding_borrower}</span>}
              </div>
              <div className="row-actions">
                <a className="text-link" href={elevator.qr_url} target="_blank" rel="noreferrer">Open QR page</a>
                <a className="text-link" href={`/api/v1/admin/elevators/${elevator.id}/qr-code`} target="_blank" rel="noreferrer">Print QR</a>
                <button className="quiet-button" onClick={() => {
                  const name = window.prompt('Elevator display name:', elevator.name)
                  if (name?.trim()) void runAction(async () => {
                    await api(`/admin/elevators/${elevator.id}`, {
                      method: 'PATCH',
                      body: JSON.stringify({ name }),
                    })
                    await loadAdminData()
                  })
                }}>Edit name</button>
                <button className="quiet-button" onClick={() => {
                  if (window.confirm(`Rotate the QR link for ${elevator.registration_number}? Existing printed codes will stop working.`)) {
                    void runAction(async () => {
                      await api(`/admin/elevators/${elevator.id}/rotate-qr`, { method: 'POST' })
                      await loadAdminData()
                    })
                  }
                }}>Rotate QR</button>
                {elevator.status === 'active' ? (
                  <button
                    className="danger-button"
                    onClick={() => {
                      const reason = window.prompt('Reason for blocking this elevator:')
                      if (reason?.trim()) {
                        void runAction(async () => {
                          await api(`/admin/elevators/${elevator.id}/block`, { method: 'POST', body: JSON.stringify({ reason }) })
                          await loadAdminData()
                        })
                      }
                    }}
                  >
                    Block
                  </button>
                ) : elevator.status === 'blocked' ? (
                  <button className="quiet-button" onClick={() => {
                    const reason = window.prompt('Reason for unblocking this elevator:')
                    if (reason?.trim()) void runAction(async () => {
                      await api(`/admin/elevators/${elevator.id}/unblock`, { method: 'POST', body: JSON.stringify({ reason }) })
                      await loadAdminData()
                    })
                  }}>Unblock</button>
                ) : null}
              </div>
            </article>
          ))}
        </div>
      </section>
      <section className="panel">
        <p className="eyebrow">PEOPLE</p>
        <h2>Create a user</h2>
        <form
          className="form-grid"
          onSubmit={(event) => {
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
          }}
        >
          <label>Username<input value={newUser.username} onChange={(e) => setNewUser({ ...newUser, username: e.target.value })} minLength={3} required /></label>
          <label>Display name<input value={newUser.name} onChange={(e) => setNewUser({ ...newUser, name: e.target.value })} required /></label>
          <label>Initial password<input type="password" value={newUser.password} onChange={(e) => setNewUser({ ...newUser, password: e.target.value })} minLength={12} required /></label>
          <label>Role<select value={newUser.role} onChange={(e) => setNewUser({ ...newUser, role: e.target.value as 'user' | 'admin' })}>
            <option value="user">User</option><option value="admin">Admin</option>
          </select></label>
          <label>Department<select value={newUser.department_id} onChange={(e) => setNewUser({ ...newUser, department_id: e.target.value })}>
            {departments.map((department) => <option value={department.id} key={department.id}>{department.name}</option>)}
          </select></label>
          <button className="primary-button" disabled={busy}>Create user (password reset required)</button>
        </form>
        <div className="elevator-list">
          {users.map((user) => (
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
      <section className="panel">
        <p className="eyebrow">SITE CONFIGURATION</p>
        <h2>Locations and departments</h2>
        <p className="muted">Default location: {locations.find((location) => location.is_default)?.name ?? 'Not set'}</p>
        <div className="two-columns">
          <form className="form-grid" onSubmit={(event) => {
            event.preventDefault()
            void runAction(async () => {
              await api('/admin/locations', {
                method: 'POST',
                body: JSON.stringify({ name: newLocationName, is_default: locations.length === 0 }),
              })
              setNewLocationName('')
            })
          }}>
            <label>Add location<input value={newLocationName} onChange={(e) => setNewLocationName(e.target.value)} required /></label>
            <button className="quiet-button">Add location</button>
          </form>
          <form className="form-grid" onSubmit={(event) => {
            event.preventDefault()
            void runAction(async () => {
              await api('/admin/departments', {
                method: 'POST',
                body: JSON.stringify({ name: newDepartmentName }),
              })
              setNewDepartmentName('')
            })
          }}>
            <label>Add department<input value={newDepartmentName} onChange={(e) => setNewDepartmentName(e.target.value)} required /></label>
            <button className="quiet-button">Add department</button>
          </form>
        </div>
      </section>
      <section className="panel">
        <p className="eyebrow">RESERVATION POLICY</p>
        <h2>Timing settings</h2>
        <p className="muted">Values are stored in seconds. The initial setting for each is seven days.</p>
        <form
          className="form-grid"
          onSubmit={(event) => {
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
          }}
        >
          {reservationTimingFields.map(([key, label]) => (
            <label key={key}>{label} (days)
              <input
                type="number"
                min={0}
                step={1}
                value={Math.round((reservationSettings[key] ?? 604800) / 86400)}
                onChange={(e) => setReservationSettings({ ...reservationSettings, [key]: Number(e.target.value) * 86400 })}
              />
            </label>
          ))}
          <button className="primary-button" disabled={busy}>Save timing settings</button>
        </form>
      </section>
      <section className="panel">
        <div className="section-heading">
          <div><p className="eyebrow">REPORTING</p><h2>Elevator usage</h2></div>
          <a className="primary-button text-button" href="/api/v1/admin/reports/loans.csv">Export loan history CSV</a>
        </div>
        <div className="elevator-list">
          {usage.map((row) => (
            <article className="elevator-row" key={row.registration_number}>
              <strong>{row.registration_number}</strong>
              <span className="muted">{row.checkout_count} checkouts · average returned-loan duration {row.average_duration_seconds === null ? 'not available' : `${Math.round(row.average_duration_seconds / 3600)} hours`}</span>
            </article>
          ))}
          {adminReservations.length > 0 && (
            <>
              <h3>Upcoming reservations</h3>
              {adminReservations.filter((item) => item.status === 'confirmed').slice(0, 20).map((item) => (
                <article className="elevator-row" key={item.id}>
                  <strong>{item.elevator}</strong>
                  <span className="muted">
                    {item.requester} · {new Intl.DateTimeFormat('en-GB', { dateStyle: 'medium', timeStyle: 'short', timeZone: 'Europe/Brussels' }).format(new Date(item.starts_at))}
                    {' – '}{new Intl.DateTimeFormat('en-GB', { dateStyle: 'short', timeStyle: 'short', timeZone: 'Europe/Brussels' }).format(new Date(item.ends_at))}
                  </span>
                </article>
              ))}
            </>
          )}
        </div>
      </section>
      <section className="panel">
        <p className="eyebrow">SITE SETTINGS</p>
        <h2>Default location</h2>
        <p className="muted">Current default: {locations.find((location) => location.is_default)?.name ?? 'Not set'}</p>
        <div className="inline-form">
          <select id="default-location">
            {locations.map((location) => <option value={location.id} key={location.id}>{location.name}</option>)}
          </select>
          <button
            className="quiet-button"
            onClick={() => {
              const id = (document.getElementById('default-location') as HTMLSelectElement).value
              void runAction(() => api(`/admin/locations/${id}/set-default`, { method: 'POST' }))
            }}
          >
            Set default
          </button>
        </div>
      </section>
    </div>
  )
}
