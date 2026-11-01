// Shared helpers: date handling, streaks, contribution levels.
export const TZ = 'Asia/Kolkata';
const DAY = 86_400_000;

const dayFmt = new Intl.DateTimeFormat('en-CA', {
  timeZone: TZ, year: 'numeric', month: '2-digit', day: '2-digit',
});

/** Date | ISO string -> 'YYYY-MM-DD' in Asia/Kolkata. */
export const istDate = (d) => dayFmt.format(d instanceof Date ? d : new Date(d));

const toUTC = (s) => Date.parse(`${s}T00:00:00Z`);
export const shiftDay = (s, n) => new Date(toUTC(s) + n * DAY).toISOString().slice(0, 10);

export const LEVELS = {
  NONE: 0, FIRST_QUARTILE: 1, SECOND_QUARTILE: 2, THIRD_QUARTILE: 3, FOURTH_QUARTILE: 4,
};

/**
 * days: [{ date: 'YYYY-MM-DD', count: number }]
 * today: the last date present in GitHub's own calendar (its notion of "today").
 * Current streak stays alive if today has no contributions yet but yesterday did,
 * which matches how GitHub-style streak counters behave.
 */
export function computeStreaks(days, today) {
  const active = new Set(days.filter((d) => d.count > 0).map((d) => d.date));
  const dates = [...active].sort();

  let longest = { length: 0, start: null, end: null };
  let runStart = null;
  let runLen = 0;
  let prev = null;
  for (const d of dates) {
    if (prev && toUTC(d) - toUTC(prev) === DAY) runLen += 1;
    else { runStart = d; runLen = 1; }
    prev = d;
    if (runLen > longest.length) longest = { length: runLen, start: runStart, end: d };
  }

  let current = { length: 0, start: null, end: null };
  let cursor = active.has(today) ? today : shiftDay(today, -1);
  if (active.has(cursor)) {
    const end = cursor;
    let start = cursor;
    let n = 0;
    while (active.has(cursor)) { n += 1; start = cursor; cursor = shiftDay(cursor, -1); }
    current = { length: n, start, end };
  }
  return { longest, current };
}
