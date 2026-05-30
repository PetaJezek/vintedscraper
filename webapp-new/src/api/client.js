// In dev (Vite on :5173) proxy forwards /api and /images to :8000.
// In prod the app is served from :8000 directly — relative paths work.
const BASE = import.meta.env.DEV ? 'http://localhost:8000' : '';

const getToken = () => localStorage.getItem('vinted_token') || '';

const headers = () => ({
  'Content-Type': 'application/json',
  'Authorization': `Bearer ${getToken()}`,
});

async function apiFetch(url, options) {
  try {
    const res = await fetch(url, options);
    window.dispatchEvent(new Event('server:online'));
    return res;
  } catch {
    window.dispatchEvent(new Event('server:offline'));
    throw new Error('SERVER_OFFLINE');
  }
}

async function handle(res) {
  if (res.status === 401) {
    localStorage.removeItem('vinted_token');
    window.dispatchEvent(new Event('auth:logout'));
    throw new Error('UNAUTHORIZED');
  }
  if (!res.ok) throw new Error(`HTTP ${res.status}`);
  return res.json();
}

export async function login(password) {
  const res = await apiFetch(`${BASE}/api/login`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ password }),
  });
  if (res.status === 401) throw new Error('Wrong password');
  if (!res.ok) throw new Error('Login failed');
  const data = await res.json();
  localStorage.setItem('vinted_token', data.access_token);
  return data.access_token;
}

export function logout() {
  localStorage.removeItem('vinted_token');
  window.dispatchEvent(new Event('auth:logout'));
}

export async function fetchNextItem(order = 'random', context = 'training', excludeId = null) {
  const params = new URLSearchParams({ order, context });
  if (excludeId) params.set('exclude', excludeId);
  return handle(await apiFetch(`${BASE}/api/next_item?${params}`, { headers: headers() }));
}

export async function triggerCheckSold() {
  return handle(await apiFetch(`${BASE}/api/check_sold`, { method: 'POST', headers: headers() }));
}

export async function rateItem(item_id, rating) {
  return handle(await apiFetch(`${BASE}/api/rate`, {
    method: 'POST',
    headers: headers(),
    body: JSON.stringify({ item_id, rating }),
  }));
}

export async function undoLastSwipe() {
  return handle(await apiFetch(`${BASE}/api/undo`, { method: 'POST', headers: headers() }));
}

export async function fetchLiked() {
  return handle(await apiFetch(`${BASE}/api/ratings`, { headers: headers() }));
}

export async function fetchStats() {
  return handle(await apiFetch(`${BASE}/api/stats`, { headers: headers() }));
}

export async function triggerRetrain() {
  return handle(await apiFetch(`${BASE}/api/retrain`, { method: 'POST', headers: headers() }));
}

export async function triggerRescore() {
  return handle(await apiFetch(`${BASE}/api/rescore`, { method: 'POST', headers: headers() }));
}

export async function triggerBuildBlocklist() {
  return handle(await apiFetch(`${BASE}/api/build_blocklist`, { method: 'POST', headers: headers() }));
}

export async function ping() {
  try {
    await fetch(`${BASE}/api/stats`, { headers: headers() });
    window.dispatchEvent(new Event('server:online'));
    return true;
  } catch {
    return false;
  }
}

export function imageUrl(path) {
  if (!path) return '';
  if (path.startsWith('http')) return path;
  return `${BASE}${path}`;
}
