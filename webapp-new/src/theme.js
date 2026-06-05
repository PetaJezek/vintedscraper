// Tiny theme helper. Stores 'light' | 'dark' in localStorage and reflects it on
// <html data-theme>. If nothing is stored, no attribute is set and the CSS falls
// back to the OS preference (prefers-color-scheme).

const KEY = 'vinted_theme';

export function getTheme() {
  return localStorage.getItem(KEY) || 'dark';
}

export function applyTheme(theme) {
  if (theme === 'light' || theme === 'dark') {
    document.documentElement.setAttribute('data-theme', theme);
    localStorage.setItem(KEY, theme);
  } else {
    document.documentElement.removeAttribute('data-theme');
    localStorage.removeItem(KEY);
  }
}

// Apply the stored theme as early as possible (called from main.jsx on load).
export function initTheme() {
  const stored = localStorage.getItem(KEY);
  if (stored) document.documentElement.setAttribute('data-theme', stored);
}
