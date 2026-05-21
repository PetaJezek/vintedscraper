const BASE = 'http://localhost:8000';
const TOKEN = 'ahoj';

const headers = () => ({
  'Content-Type': 'application/json',
  'Authorization': `Bearer ${TOKEN}`,
});

export async function fetchNextItem(order = 'random', context = 'training') {
  const res = await fetch(`${BASE}/api/next_item?order=${order}&context=${context}`, { headers: headers() });
  if (!res.ok) throw new Error('No items');
  return res.json();
}

export async function triggerCheckSold() {
  const res = await fetch(`${BASE}/api/check_sold`, { method: 'POST', headers: headers() });
  if (!res.ok) throw new Error('Check sold failed');
  return res.json();
}

export async function rateItem(item_id, rating) {
  const res = await fetch(`${BASE}/api/rate`, {
    method: 'POST',
    headers: headers(),
    body: JSON.stringify({ item_id, rating }),
  });
  if (!res.ok) throw new Error('Rate failed');
  return res.json();
}

export async function undoLastSwipe() {
  const res = await fetch(`${BASE}/api/undo`, { method: 'POST', headers: headers() });
  if (!res.ok) throw new Error('Undo failed');
  return res.json();
}

export async function fetchLiked() {
  const res = await fetch(`${BASE}/api/ratings`, { headers: headers() });
  if (!res.ok) throw new Error('Fetch liked failed');
  return res.json();
}

export async function fetchStats() {
  const res = await fetch(`${BASE}/api/stats`, { headers: headers() });
  if (!res.ok) throw new Error('Fetch stats failed');
  return res.json();
}

export async function triggerRetrain() {
  const res = await fetch(`${BASE}/api/retrain`, { method: 'POST', headers: headers() });
  if (!res.ok) throw new Error('Retrain failed');
  return res.json();
}

export async function triggerRescore() {
  const res = await fetch(`${BASE}/api/rescore`, { method: 'POST', headers: headers() });
  if (!res.ok) throw new Error('Rescore failed');
  return res.json();
}

export async function triggerBuildBlocklist() {
  const res = await fetch(`${BASE}/api/build_blocklist`, { method: 'POST', headers: headers() });
  if (!res.ok) throw new Error('Build blocklist failed');
  return res.json();
}

export function imageUrl(path) {
  if (!path) return '';
  if (path.startsWith('http')) return path;
  return `${BASE}${path}`;
}
