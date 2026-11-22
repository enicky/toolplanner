// @vitest-environment jsdom

import { cleanup, render, screen, waitFor, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { MemoryRouter, useLocation } from 'react-router-dom'
import App from './App'

const adminAccount = {
  id: 'admin-1',
  username: 'admin',
  display_name: 'Site Admin',
  department_id: null,
  role: 'admin' as const,
  must_change_password: false,
}

function installApiMock(options: { sessionExpired?: boolean; invalidLogin?: boolean } = {}) {
  let sessionExpired = options.sessionExpired ?? false
  const elevators = [
    {
      id: 'lift-1',
      name: 'LIFT-001',
      registration_number: 'LIFT-001',
      status: 'active',
      qr_url: 'http://127.0.0.1:5173/qr/token-1',
      outstanding_borrower: null,
    },
  ]
  const locations = [
    { id: 'loc-1', name: 'Geel', is_default: true, is_active: true, details: null, elevator_count: 1 },
    { id: 'loc-2', name: 'Annex', is_default: false, is_active: true, details: 'East wing', elevator_count: 0 },
  ]
  const departments = [
    { id: 'dept-1', name: 'Sites & Facilities', is_active: true, active_user_count: 0 },
    { id: 'dept-2', name: 'Research', is_active: true, active_user_count: 0 },
  ]
  const fetchMock = vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
      const path = new URL(String(input), 'http://localhost').pathname
      const method = (init?.method ?? 'GET').toUpperCase()
      if (path === '/api/v1/auth/login' && method === 'POST') {
        if (options.invalidLogin) {
          return new Response(JSON.stringify({ detail: 'Invalid username or password.' }), {
            status: 401,
            headers: { 'Content-Type': 'application/json' },
          })
        }
        sessionExpired = false
        return new Response(JSON.stringify({ user: adminAccount }), {
          status: 200,
          headers: { 'Content-Type': 'application/json' },
        })
      }
      if (path === '/api/v1/me' && sessionExpired) {
        return new Response(JSON.stringify({ detail: 'Sign in is required.' }), {
          status: 401,
          headers: { 'Content-Type': 'application/json' },
        })
      }
      if (path === '/api/v1/admin/reports/dashboard') {
        return new Response(JSON.stringify({
          filters: {
            start_date: '2026-03-01',
            end_date: '2026-03-30',
            bucket: 'day',
            elevator_id: null,
            department_id: null,
            location_id: null,
          },
          summary: {
            checkout_count: 12,
            completed_loan_count: 8,
            average_returned_duration_seconds: 10800,
            previous_checkout_count: 10,
            checkout_change_percent: 20,
          },
          trend: [{ period: '2026-03-30', checkout_count: 2 }],
          elevator_usage: [{ elevator_id: 'lift-1', registration_number: 'LIFT-001', checkout_count: 12 }],
          department_usage: [{ department_id: 'dept-1', department: 'Sites & Facilities', checkout_count: 12 }],
          location_usage: [{ location_id: 'loc-1', location: 'Geel', checkout_count: 12 }],
          duration_bands: [
            { band: 'Under 1 day', count: 8 },
            { band: '1 to 3 days', count: 0 },
            { band: '3 to 7 days', count: 0 },
            { band: '7 days or more', count: 0 },
          ],
          current_custody_count: 1,
          custody_age_bands: [
            { band: 'Under 24 hours', count: 1 },
            { band: '1 to 3 days', count: 0 },
            { band: '3 to 7 days', count: 0 },
            { band: '7 days or more', count: 0 },
          ],
          reservation_outcomes: {
            picked_up: 7,
            no_show: 1,
            cancelled: 2,
            upcoming: 1,
            awaiting_pickup: 0,
            pickup_rate_percent: 87.5,
            resolved_count: 8,
          },
          reservation_note: null,
        }), { status: 200, headers: { 'Content-Type': 'application/json' } })
      }
      if (path === '/api/v1/admin/locations' && method === 'GET') {
        return new Response(JSON.stringify(locations), { status: 200, headers: { 'Content-Type': 'application/json' } })
      }
      if (path === '/api/v1/admin/locations' && method === 'POST') {
        const request = JSON.parse(String(init?.body)) as { name: string; is_default: boolean }
        const record = { id: `loc-${locations.length + 1}`, name: request.name, is_default: request.is_default, is_active: true, details: null, elevator_count: 0 }
        locations.push(record)
        return new Response(JSON.stringify(record), { status: 201, headers: { 'Content-Type': 'application/json' } })
      }
      const locationMatch = path.match(/^\/api\/v1\/admin\/locations\/([^/]+)(?:\/(set-default|restore))?$/)
      if (locationMatch) {
        const record = locations.find((item) => item.id === locationMatch[1])
        if (record && method === 'PATCH') {
          Object.assign(record, JSON.parse(String(init?.body)))
          return new Response(JSON.stringify(record), { status: 200, headers: { 'Content-Type': 'application/json' } })
        }
        if (record && method === 'DELETE') {
          record.is_active = false
          record.is_default = false
          return new Response(JSON.stringify({ id: record.id, is_active: false }), { status: 200, headers: { 'Content-Type': 'application/json' } })
        }
        if (record && locationMatch[2] === 'set-default' && method === 'POST') {
          locations.forEach((item) => { item.is_default = item.id === record.id })
          return new Response(JSON.stringify({ id: record.id, is_default: true }), { status: 200, headers: { 'Content-Type': 'application/json' } })
        }
        if (record && locationMatch[2] === 'restore' && method === 'POST') {
          record.is_active = true
          return new Response(JSON.stringify({ id: record.id, is_active: true }), { status: 200, headers: { 'Content-Type': 'application/json' } })
        }
      }
      if (path === '/api/v1/admin/departments' && method === 'GET') {
        return new Response(JSON.stringify(departments), { status: 200, headers: { 'Content-Type': 'application/json' } })
      }
      if (path === '/api/v1/admin/departments' && method === 'POST') {
        const request = JSON.parse(String(init?.body)) as { name: string }
        const record = { id: `dept-${departments.length + 1}`, name: request.name, is_active: true, active_user_count: 0 }
        departments.push(record)
        return new Response(JSON.stringify(record), { status: 201, headers: { 'Content-Type': 'application/json' } })
      }
      const departmentMatch = path.match(/^\/api\/v1\/admin\/departments\/([^/]+)(?:\/restore)?$/)
      if (departmentMatch) {
        const record = departments.find((item) => item.id === departmentMatch[1])
        if (record && method === 'PATCH') {
          Object.assign(record, JSON.parse(String(init?.body)))
          return new Response(JSON.stringify(record), { status: 200, headers: { 'Content-Type': 'application/json' } })
        }
        if (record && method === 'DELETE') {
          record.is_active = false
          return new Response(JSON.stringify({ id: record.id, is_active: false }), { status: 200, headers: { 'Content-Type': 'application/json' } })
        }
        if (record && path.endsWith('/restore') && method === 'POST') {
          record.is_active = true
          return new Response(JSON.stringify({ id: record.id, is_active: true }), { status: 200, headers: { 'Content-Type': 'application/json' } })
        }
      }
      if (path === '/api/v1/admin/elevators' && init?.method === 'POST') {
        const request = JSON.parse(String(init.body)) as {
          name: string
          registration_number: string
        }
        const elevator = {
          id: 'lift-2',
          name: request.name,
          registration_number: request.registration_number,
          status: 'active',
          qr_url: 'http://127.0.0.1:5173/qr/token-2',
          outstanding_borrower: null,
        }
        elevators.push(elevator)
        return new Response(JSON.stringify(elevator), {
          status: 201,
          headers: { 'Content-Type': 'application/json' },
        })
      }
      if (path === '/api/v1/admin/elevators') {
        return new Response(JSON.stringify(elevators), {
          status: 200,
          headers: { 'Content-Type': 'application/json' },
        })
      }
      if (path === '/api/v1/qr/token-2') {
        return new Response(JSON.stringify({
          name: 'Test Elevator 2',
          registration_number: 'LIFT-002',
          status: 'available',
          elevator_status: 'active',
          can_return: false,
          can_borrow: true,
        }), {
          status: 200,
          headers: { 'Content-Type': 'application/json' },
        })
      }
      if (init?.method && init.method !== 'GET') {
        return new Response('{}', {
          status: 200,
          headers: { 'Content-Type': 'application/json' },
        })
      }
      const payload: Record<string, unknown> = {
        '/api/v1/me': adminAccount,
        '/api/v1/me/notifications': [],
        '/api/v1/locations': locations.filter((item) => item.is_active),
        '/api/v1/departments': departments.filter((item) => item.is_active),
        '/api/v1/admin/reservation-settings': {
          minimum_notice_seconds: 604800,
          maximum_duration_seconds: 604800,
          cancellation_cutoff_seconds: 604800,
          no_show_grace_seconds: 604800,
          version: 1,
        },
        '/api/v1/admin/users': [],
        '/api/v1/admin/overview': {
          available_count: 1,
          active_count: 1,
          outstanding_custody_count: 0,
          blocked_count: 0,
          retired_count: 0,
          at_risk_reservation_count: 0,
          oldest_custody: [],
        },
        '/api/v1/admin/reservations': [],
        '/api/v1/admin/loans': [],
        '/api/v1/admin/audit': [],
      }
      const body = payload[path]
      return new Response(JSON.stringify(body ?? { detail: 'Not found.' }), {
        status: body === undefined ? 404 : 200,
        headers: { 'Content-Type': 'application/json' },
      })
    })
  vi.stubGlobal('fetch', fetchMock)
  return fetchMock
}

function CurrentLocation() {
  const location = useLocation()
  return <span data-testid="current-location">{`${location.pathname}${location.search}`}</span>
}

afterEach(() => {
  cleanup()
  vi.unstubAllGlobals()
})

beforeEach(() => {
  HTMLDialogElement.prototype.showModal = function showModal() {
    this.setAttribute('open', '')
  }
  HTMLDialogElement.prototype.close = function close() {
    this.removeAttribute('open')
  }
})

describe('admin navigation', () => {
  it('redirects an expired session to login', async () => {
    installApiMock({ sessionExpired: true })
    render(
      <MemoryRouter initialEntries={['/admin/users']}>
        <App />
        <CurrentLocation />
      </MemoryRouter>,
    )

    expect(await screen.findByRole('heading', { name: 'Sign in to continue' })).toBeTruthy()
    await waitFor(() => expect(screen.getByTestId('current-location').textContent).toBe('/login'))
    expect(screen.queryByRole('alert')).toBeNull()
  })

  it('shows invalid credentials on the login page without redirecting again', async () => {
    installApiMock({ sessionExpired: true, invalidLogin: true })
    const user = userEvent.setup()
    render(
      <MemoryRouter initialEntries={['/admin/users']}>
        <App />
        <CurrentLocation />
      </MemoryRouter>,
    )

    expect(await screen.findByRole('heading', { name: 'Sign in to continue' })).toBeTruthy()
    await user.type(screen.getByRole('textbox', { name: 'Username' }), 'admin')
    await user.type(screen.getByLabelText('Password'), 'wrong-password')
    await user.click(screen.getByRole('button', { name: 'Sign in' }))

    expect((await screen.findByRole('alert')).textContent).toContain('Invalid username or password.')
    expect(screen.getByTestId('current-location').textContent).toBe('/login')
  })

  it('opens separate admin destinations through direct routes and sidebar links', async () => {
    installApiMock()
    const user = userEvent.setup()
    render(
      <MemoryRouter initialEntries={['/admin/users']}>
        <App />
      </MemoryRouter>,
    )

    expect(await screen.findByRole('heading', { name: 'Users' })).toBeTruthy()
    await user.click(screen.getByRole('link', { name: 'Inventory' }))
    expect(await screen.findByRole('heading', { name: 'Inventory' })).toBeTruthy()
    expect(screen.getByRole('link', { name: 'Inventory' }).getAttribute('aria-current')).toBe('page')
  })

  it('opens and closes the mobile navigation with accessible state', async () => {
    installApiMock()
    const user = userEvent.setup()
    render(
      <MemoryRouter initialEntries={['/admin/overview']}>
        <App />
      </MemoryRouter>,
    )

    const menuButton = await screen.findByRole('button', { name: 'Open admin navigation' })
    expect(menuButton.getAttribute('aria-expanded')).toBe('false')
    await user.click(menuButton)
    expect(menuButton.getAttribute('aria-expanded')).toBe('true')
    await user.keyboard('{Escape}')
    await waitFor(() => expect(menuButton.getAttribute('aria-expanded')).toBe('false'))
    expect(document.activeElement).toBe(menuButton)
    await user.click(menuButton)
    await user.click(screen.getByRole('link', { name: 'Users' }))
    await waitFor(() => expect(menuButton.getAttribute('aria-expanded')).toBe('false'))
    expect(await screen.findByRole('heading', { name: 'Users' })).toBeTruthy()
  })

  it('traps keyboard focus in the open mobile drawer and wraps at its boundaries', async () => {
    installApiMock()
    const user = userEvent.setup()
    render(
      <MemoryRouter initialEntries={['/admin/overview']}>
        <App />
      </MemoryRouter>,
    )

    await user.click(await screen.findByRole('button', { name: 'Open admin navigation' }))
    const overviewLink = screen.getByRole('link', { name: 'Overview' })
    const auditLink = screen.getByRole('link', { name: 'Audit activity' })
    await waitFor(() => expect(document.activeElement).toBe(overviewLink))

    await user.keyboard('{Shift>}{Tab}{/Shift}')
    expect(document.activeElement).toBe(auditLink)
    await user.keyboard('{Tab}')
    expect(document.activeElement).toBe(overviewLink)
  })

  it('clears the success message when navigating from inventory to a QR page', async () => {
    installApiMock()
    const user = userEvent.setup()
    render(
      <MemoryRouter initialEntries={['/admin/inventory']}>
        <App />
      </MemoryRouter>,
    )

    await user.type(await screen.findByRole('textbox', { name: 'Elevator name' }), 'Test Elevator 2')
    await user.type(screen.getByRole('textbox', { name: 'Registration number' }), 'LIFT-002')
    await user.click(screen.getByRole('button', { name: 'Add elevator' }))
    expect((await screen.findByRole('status')).textContent).toContain('Done.')

    await user.click(screen.getAllByRole('link', { name: 'Open QR page' })[1])
    expect(await screen.findByRole('heading', { name: 'Borrow, reserve or return' })).toBeTruthy()
    expect(screen.queryByText('Done.')).toBeNull()
  })

  it('uses a reason modal instead of a browser prompt for block actions', async () => {
    const fetchMock = installApiMock()
    const prompt = vi.spyOn(window, 'prompt').mockImplementation(() => {
      throw new Error('Browser prompt should not be used.')
    })
    const user = userEvent.setup()
    render(
      <MemoryRouter initialEntries={['/admin/inventory']}>
        <App />
      </MemoryRouter>,
    )

    await user.click(await screen.findByRole('button', { name: 'Block' }))
    const dialog = await screen.findByRole('dialog', { name: 'Block elevator' })
    await user.type(within(dialog).getByRole('textbox', { name: 'Reason' }), 'Inspection required')
    await user.click(within(dialog).getByRole('button', { name: 'Block elevator' }))

    await waitFor(() => expect(screen.queryByRole('dialog')).toBeNull())
    expect(prompt).not.toHaveBeenCalled()
    expect(fetchMock).toHaveBeenCalledWith(
      '/api/v1/admin/elevators/lift-1/block',
      expect.objectContaining({
        method: 'POST',
        body: JSON.stringify({ reason: 'Inspection required' }),
      }),
    )
  })

  it('separates location and department management into tabs and supports edit/archive/restore', async () => {
    installApiMock()
    const user = userEvent.setup()
    render(
      <MemoryRouter initialEntries={['/admin/locations']}>
        <App />
      </MemoryRouter>,
    )

    await screen.findByRole('heading', { level: 1, name: 'Locations & departments' })
    expect(await screen.findByText('Geel', { selector: 'strong' })).toBeTruthy()
    expect(screen.getAllByRole('button', { name: 'Delete' })[0].hasAttribute('disabled')).toBe(true)

    await user.click(screen.getByRole('tab', { name: 'Departments' }))
    expect(await screen.findByText('Research')).toBeTruthy()
    expect(screen.queryByRole('heading', { name: 'Physical locations' })).toBeNull()

    await user.click(screen.getByRole('tab', { name: 'Locations' }))
    const annexRow = screen.getByText('Annex').closest('article')
    await user.click(within(annexRow!).getByRole('button', { name: 'Edit' }))
    const editDialog = await screen.findByRole('dialog', { name: 'Edit location' })
    const nameInput = within(editDialog).getByRole('textbox', { name: 'Location name' })
    await user.clear(nameInput)
    await user.type(nameInput, 'Annex West')
    await user.click(within(editDialog).getByRole('button', { name: 'Save location' }))
    expect(await screen.findByText('Annex West')).toBeTruthy()

    const updatedRow = screen.getByText('Annex West').closest('article')
    await user.click(within(updatedRow!).getByRole('button', { name: 'Delete' }))
    const deleteDialog = await screen.findByRole('dialog', { name: 'Delete location' })
    expect(within(deleteDialog).getByText(/historical records/i)).toBeTruthy()
    await user.click(within(deleteDialog).getByRole('button', { name: 'Delete location' }))
    expect(await screen.findByText('Archived')).toBeTruthy()
    await user.click(screen.getByRole('button', { name: 'Restore' }))
    await waitFor(() => expect(screen.queryByRole('button', { name: 'Restore' })).toBeNull())
    expect(screen.getByText('Annex West')).toBeTruthy()
  })

  it('renders aggregate reports and applies URL-backed filters to export', async () => {
    const fetchMock = installApiMock()
    const user = userEvent.setup()
    render(
      <MemoryRouter initialEntries={['/admin/reports?start_date=2026-03-01&end_date=2026-03-30']}>
        <App />
      </MemoryRouter>,
    )

    const checkoutMetric = (await screen.findByText('Checkouts in range')).parentElement
    expect(await within(checkoutMetric!).findByText('12')).toBeTruthy()
    expect(screen.getByRole('heading', { name: 'Borrowing trend' })).toBeTruthy()
    expect(screen.getByRole('heading', { name: 'By pickup location' })).toBeTruthy()
    expect(screen.getByText('87.5%')).toBeTruthy()
    const exportLink = screen.getByRole('link', { name: 'Export filtered loan history' })
    expect(exportLink.getAttribute('href')).toContain('start_date=2026-03-01')
    expect(exportLink.getAttribute('href')).toContain('end_date=2026-03-30')

    await user.selectOptions(screen.getByLabelText('Department'), 'dept-2')
    await user.click(screen.getByRole('button', { name: 'Apply filters' }))
    await waitFor(() => {
      const request = fetchMock.mock.calls
        .map(([input]) => new URL(String(input), 'http://localhost'))
        .find((url) => url.pathname === '/api/v1/admin/reports/dashboard' &&
          url.searchParams.get('department_id') === 'dept-2')
      expect(request).toBeTruthy()
    })
    expect(screen.getByRole('link', { name: 'Export filtered loan history' }).getAttribute('href'))
      .toContain('department_id=dept-2')
  })
})
