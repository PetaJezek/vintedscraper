import { useState, useEffect, useRef } from 'react';
import { BrowserRouter, Routes, Route, useLocation } from 'react-router-dom';
import { AnimatePresence, motion } from 'framer-motion';
import { ToastProvider } from './components/Toast';
import { LanguageProvider } from './i18n';
import BottomNav from './components/BottomNav';
import Terminal from './components/Terminal';
import SwipeScreen from './screens/SwipeScreen';
import LikedScreen from './screens/LikedScreen';
import CompareScreen from './screens/CompareScreen';
import ProfileScreen from './screens/ProfileScreen';
import ConfigScreen from './screens/ConfigScreen';
import LoginScreen from './screens/LoginScreen';
import { ping } from './api/client';

// Only mount the (animating) ambient terminal on wide screens.
function useWide(min = 1000) {
  const [wide, setWide] = useState(() =>
    typeof window !== 'undefined' && window.matchMedia(`(min-width:${min}px)`).matches);
  useEffect(() => {
    const mq = window.matchMedia(`(min-width:${min}px)`);
    const on = e => setWide(e.matches);
    mq.addEventListener('change', on);
    return () => mq.removeEventListener('change', on);
  }, [min]);
  return wide;
}

export default function App() {
  const [token, setToken] = useState(() => localStorage.getItem('vinted_token'));
  const [serverOnline, setServerOnline] = useState(true);
  const retryRef = useRef(null);

  useEffect(() => {
    const goOnline  = () => { setServerOnline(true);  clearInterval(retryRef.current); };
    const goOffline = () => {
      setServerOnline(false);
      clearInterval(retryRef.current);
      retryRef.current = setInterval(ping, 4000);
    };
    const handleLogout = () => setToken(null);
    window.addEventListener('server:online',  goOnline);
    window.addEventListener('server:offline', goOffline);
    window.addEventListener('auth:logout',    handleLogout);
    return () => {
      window.removeEventListener('server:online',  goOnline);
      window.removeEventListener('server:offline', goOffline);
      window.removeEventListener('auth:logout',    handleLogout);
      clearInterval(retryRef.current);
    };
  }, []);

  if (!serverOnline) return <OfflineScreen />;
  if (!token) return <LoginScreen onLogin={t => setToken(t)} />;

  return (
    <LanguageProvider>
      <ToastProvider>
        <BrowserRouter>
          <Layout />
        </BrowserRouter>
      </ToastProvider>
    </LanguageProvider>
  );
}

function OfflineScreen() {
  const [retrying, setRetrying] = useState(false);
  async function retry() { setRetrying(true); await ping(); setRetrying(false); }

  return (
    <div style={{
      position: 'fixed', inset: 0, zIndex: 1,
      display: 'flex', alignItems: 'center', justifyContent: 'center',
      flexDirection: 'column', gap: 26, padding: 24,
    }}>
      <div style={{ textAlign: 'center' }}>
        <div className="eyebrow" style={{ marginBottom: 10 }}>· connection lost ·</div>
        <div className="display" style={{ fontSize: 34, fontWeight: 500, color: 'var(--text)' }}>
          The atelier is <span style={{ fontStyle: 'italic', color: 'var(--accent)' }}>asleep</span>
        </div>
      </div>
      <div style={{ width: '100%', maxWidth: 440 }}>
        <Terminal
          title="vinted-ai — offline"
          status="error"
          maxLines={6}
          lines={[
            '$ curl http://localhost:8000/api/ping',
            '✗ connection refused',
            '→ the backend is not running on your PC',
            '$ ./vinted-ai.sh    # start it, then return',
          ]}
        />
      </div>
      <button
        onClick={retry}
        disabled={retrying}
        style={{
          background: 'var(--accent)', color: '#1a1206',
          border: 'none', borderRadius: 999,
          padding: '13px 32px', fontSize: 14, fontWeight: 700,
          letterSpacing: '0.01em',
          cursor: retrying ? 'default' : 'pointer',
          opacity: retrying ? 0.6 : 1,
          boxShadow: '0 8px 24px rgba(230,189,118,0.25)',
        }}
      >
        {retrying ? 'Reconnecting…' : 'Reconnect'}
      </button>
    </div>
  );
}

function Layout() {
  const location = useLocation();
  const wide = useWide();

  return (
    <div className="shell">
      <div className="phone">
        <div style={{ flex: 1, minHeight: 0, overflow: 'hidden', position: 'relative' }}>
          <AnimatePresence mode="wait" initial={false}>
            <motion.div
              key={location.pathname}
              initial={{ opacity: 0, y: 6 }}
              animate={{ opacity: 1, y: 0 }}
              exit={{ opacity: 0, y: -6 }}
              transition={{ duration: 0.18, ease: 'easeInOut' }}
              style={{ position: 'absolute', inset: 0, display: 'flex', flexDirection: 'column', overflow: 'hidden' }}
            >
              <Routes location={location}>
                <Route path="/" element={<SwipeScreen />} />
                <Route path="/compare" element={<CompareScreen />} />
                <Route path="/liked" element={<LikedScreen />} />
                <Route path="/profile" element={<ProfileScreen />} />
                <Route path="/config" element={<ConfigScreen />} />
              </Routes>
            </motion.div>
          </AnimatePresence>
        </div>
        <BottomNav />
      </div>

      {wide && (
        <aside className="rail">
          <div>
            <div className="eyebrow" style={{ color: 'var(--accent)', marginBottom: 8 }}>● live · the machine</div>
            <div className="display" style={{ fontSize: 30, fontWeight: 500, color: 'var(--text)', lineHeight: 1.05 }}>
              Always learning<br />your <span style={{ fontStyle: 'italic', color: 'var(--accent)' }}>taste</span>.
            </div>
          </div>
          <Terminal style={{ flex: 1, minHeight: 0, display: 'flex', flexDirection: 'column' }} maxLines={22} />
        </aside>
      )}
    </div>
  );
}
