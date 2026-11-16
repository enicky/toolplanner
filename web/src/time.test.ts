import { describe, expect, it } from 'vitest'
import { brusselsTimeToIso } from './time'

describe('brusselsTimeToIso', () => {
  it('converts winter local times to UTC', () => {
    expect(brusselsTimeToIso('2026-01-15T12:30')).toBe('2026-01-15T11:30:00.000Z')
  })

  it('converts summer local times to UTC', () => {
    expect(brusselsTimeToIso('2026-07-15T12:30')).toBe('2026-07-15T10:30:00.000Z')
  })

  it('rejects local times skipped by the spring clock change', () => {
    expect(() => brusselsTimeToIso('2026-03-29T02:30')).toThrow('does not exist')
  })

  it('rejects ambiguous local times during the autumn clock change', () => {
    expect(() => brusselsTimeToIso('2026-10-25T02:30')).toThrow('occurs twice')
  })
})
