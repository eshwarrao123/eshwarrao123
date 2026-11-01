// Fetches real contribution data via GitHub GraphQL and writes data/contributions.json.
// Auth: GITHUB_TOKEN (built-in Actions token is enough for public data).
import { mkdir, writeFile } from 'node:fs/promises';
import { computeStreaks, istDate, LEVELS } from './lib.mjs';

const token = process.env.GITHUB_TOKEN;
const login = process.env.GH_LOGIN || process.env.GITHUB_REPOSITORY_OWNER;
if (!token) throw new Error('GITHUB_TOKEN is not set');
if (!login) throw new Error('Set GH_LOGIN (or run inside Actions so GITHUB_REPOSITORY_OWNER exists)');

async function gql(query, variables = {}, attempt = 1) {
  const res = await fetch('https://api.github.com/graphql', {
    method: 'POST',
    headers: { Authorization: `bearer ${token}`, 'Content-Type': 'application/json', 'User-Agent': 'profile-readme-updater' },
    body: JSON.stringify({ query, variables }),
  });
  if (res.status >= 500 && attempt < 4) {
    await new Promise((r) => setTimeout(r, attempt * 2000));
    return gql(query, variables, attempt + 1);
  }
  const json = await res.json();
  if (!res.ok || json.errors) throw new Error(`GraphQL error (${res.status}): ${JSON.stringify(json.errors ?? json)}`);
  return json.data;
}

const CAL = `contributionCalendar { totalContributions weeks { contributionDays { date contributionCount contributionLevel weekday } } }`;
const flatten = (cal) => cal.weeks.flatMap((w) => w.contributionDays.map((d) => ({ date: d.date, count: d.contributionCount })));
const now = new Date();
const nowIso = now.toISOString();

// 1) Which years have activity?
const { user: u0 } = await gql(
  `query($login:String!){ user(login:$login){ contributionsCollection { contributionYears } } }`, { login });
const years = [...u0.contributionsCollection.contributionYears].sort();

// 2) Full daily history, one calendar-year request per year (API limit: 1 year per window).
const allDays = new Map();
for (const y of years) {
  const from = `${y}-01-01T00:00:00Z`;
  const to = y === now.getUTCFullYear() ? nowIso : `${y}-12-31T23:59:59Z`;
  const { user } = await gql(
    `query($login:String!,$from:DateTime!,$to:DateTime!){ user(login:$login){ contributionsCollection(from:$from,to:$to){ ${CAL} } } }`,
    { login, from, to });
  for (const d of flatten(user.contributionsCollection.contributionCalendar)) allDays.set(d.date, d.count);
}
const history = [...allDays].map(([date, count]) => ({ date, count })).sort((a, b) => a.date.localeCompare(b.date));

// 3) Trailing-year calendar with GitHub's own levels (this drives the ring).
const { user: u2 } = await gql(
  `query($login:String!){ user(login:$login){ contributionsCollection { ${CAL} } } }`, { login });
const recentCal = u2.contributionsCollection.contributionCalendar;
const weeks = recentCal.weeks.map((w) => w.contributionDays.map((d) => ({
  date: d.date, count: d.contributionCount, level: LEVELS[d.contributionLevel] ?? 0, weekday: d.weekday,
})));
const lastDate = weeks.at(-1).at(-1).date;

// 4) Streaks (all-time longest, current).
const streaks = computeStreaks(history, lastDate);

// 5) Commit-only best day: CreatedCommitContribution.commitCount summed per IST date.
//    Month-sized windows keep every connection under its page limit (<=31 days, <=100 repos).
let exact = true;
const commitsByDay = new Map();
const lastYear = years.at(-1);
for (const y of years) {
  let parts = '';
  for (let m = 1; m <= 12; m += 1) {
    const mm = String(m).padStart(2, '0');
    const from = `${y}-${mm}-01T00:00:00Z`;
    if (Date.parse(from) > now.getTime()) break;
    const lastDay = new Date(Date.UTC(y, m, 0)).getUTCDate();
    let to = `${y}-${mm}-${lastDay}T23:59:59Z`;
    if (Date.parse(to) > now.getTime()) to = nowIso;
    parts += `m${m}: contributionsCollection(from:"${from}", to:"${to}") {
      commitContributionsByRepository(maxRepositories: 100) {
        contributions(first: 31) { nodes { commitCount occurredAt } pageInfo { hasNextPage } }
      } }\n`;
  }
  if (!parts) continue;
  const { user } = await gql(`query($login:String!){ user(login:$login){ ${parts} } }`, { login });
  for (const col of Object.values(user)) {
    const repos = col.commitContributionsByRepository;
    if (repos.length >= 100) exact = false;
    for (const r of repos) {
      if (r.contributions.pageInfo.hasNextPage) exact = false;
      for (const n of r.contributions.nodes) {
        const k = istDate(n.occurredAt);
        commitsByDay.set(k, (commitsByDay.get(k) ?? 0) + n.commitCount);
      }
    }
  }
}
let bestCommit = { commits: 0, date: null };
for (const [date, commits] of [...commitsByDay].sort(([a], [b]) => a.localeCompare(b))) {
  if (commits > bestCommit.commits) bestCommit = { commits, date };
}
let bestContribution = { count: 0, date: null };
for (const d of history) if (d.count > bestContribution.count) bestContribution = { count: d.count, date: d.date };

const out = {
  source: 'github-graphql',
  login,
  timezone: 'Asia/Kolkata',
  totalLastYear: recentCal.totalContributions,
  range: { from: weeks[0][0].date, to: lastDate },
  streaks,
  bestCommitDay: { ...bestCommit, exact },   // commit-only, aggregated per IST calendar day
  bestContributionDay: bestContribution,     // fallback label: includes PRs/issues/reviews
  weeks,
};

await mkdir(new URL('../data/', import.meta.url), { recursive: true });
await writeFile(new URL('../data/contributions.json', import.meta.url), `${JSON.stringify(out)}\n`);
console.log(JSON.stringify({ login, years, total: out.totalLastYear, streaks, bestCommitDay: out.bestCommitDay, bestContributionDay: bestContribution }, null, 2));
