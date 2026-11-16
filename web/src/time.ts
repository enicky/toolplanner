export function brusselsTimeToIso(value: string): string {
  const [date, time] = value.split('T')
  const [year, month, day] = date.split('-').map(Number)
  const [hour, minute] = time.split(':').map(Number)
  const wallTime = Date.UTC(year, month - 1, day, hour, minute)
  const formatter = new Intl.DateTimeFormat('en-GB', {
    timeZone: 'Europe/Brussels',
    year: 'numeric',
    month: '2-digit',
    day: '2-digit',
    hour: '2-digit',
    minute: '2-digit',
    hourCycle: 'h23',
  })
  const matches: number[] = []
  for (let offset = -120; offset <= 180; offset += 15) {
    const candidate = wallTime - offset * 60_000
    const parts = Object.fromEntries(
      formatter.formatToParts(new Date(candidate)).map((part) => [part.type, part.value]),
    )
    if (
      Number(parts.year) === year &&
      Number(parts.month) === month &&
      Number(parts.day) === day &&
      Number(parts.hour) === hour &&
      Number(parts.minute) === minute
    ) {
      matches.push(candidate)
    }
  }
  if (matches.length === 0) {
    throw new Error('That local time does not exist in Brussels because of the clock change.')
  }
  if (matches.length > 1) {
    throw new Error('That local time occurs twice in Brussels. Choose another time.')
  }
  return new Date(matches[0]).toISOString()
}
