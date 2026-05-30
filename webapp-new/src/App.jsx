import { useState, useEffect, useRef } from 'react';
import { BrowserRouter, Routes, Route, useLocation } from 'react-router-dom';
import { AnimatePresence, motion } from 'framer-motion';
import { ToastProvider } from './components/Toast';
import BottomNav from './components/BottomNav';
import SwipeScreen from './screens/SwipeScreen';
import LikedScreen from './screens/LikedScreen';
import CompareScreen from './screens/CompareScreen';
import ProfileScreen from './screens/ProfileScreen';
import ConfigScreen from './screens/ConfigScreen';
import LoginScreen from './screens/LoginScreen';
import { ping } from './api/client';

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
    <ToastProvider>
      <BrowserRouter>
        <Layout />
      </BrowserRouter>
    </ToastProvider>
  );
}

function OfflineScreen() {
  const [retrying, setRetrying] = useState(false);

  async function retry() {
    setRetrying(true);
    await ping();
    setRetrying(false);
  }

  return (
    <div style={{
      position: 'fixed', inset: 0,
      display: 'flex', alignItems: 'center', justifyContent: 'center',
      background: 'var(--bg)', padding: 24,
    }}>
      <div style={{
        width: '100%', maxWidth: 340,
        background: 'var(--bg-card)',
        border: '1px solid var(--border)',
        borderRadius: 20, padding: '32px 28px',
        display: 'flex', flexDirection: 'column',
        alignItems: 'center', gap: 16, textAlign: 'center',
      }}>
        <div style={{ fontSize: 48 }}>🖥️</div>
        <div style={{ fontFamily: 'Syne', fontWeight: 800, fontSize: 22, color: 'var(--text)', letterSpacing: '-0.5px' }}>
          Server is offline
        </div>
        <div style={{ fontSize: 14, color: 'var(--text-2)', lineHeight: 1.6 }}>
          Start the backend on your PC first:
        </div>
        <div style={{
          background: 'var(--surface)', border: '1px solid var(--border)',
          borderRadius: 10, padding: '10px 16px',
          fontFamily: 'monospace', fontSize: 13, color: 'var(--text)',
          width: '100%', textAlign: 'left',
        }}>
          ./scriptWEB.sh
        </div>
        <div style={{ fontSize: 12, color: 'var(--text-3)', lineHeight: 1.5 }}>
          Then come back here — it'll reconnect automatically.
        </div>
        <button
          onClick={retry}
          disabled={retrying}
          style={{
            marginTop: 4,
            background: 'var(--accent)', color: '#fff',
            border: 'none', borderRadius: 12,
            padding: '12px 28px', fontSize: 14, fontWeight: 600,
            cursor: retrying ? 'default' : 'pointer',
            opacity: retrying ? 0.6 : 1,
            fontFamily: 'inherit',
          }}
        >
          {retrying ? 'Checking…' : 'Retry now'}
        </button>
      </div>
    </div>
  );
}

function Layout() {
  const location = useLocation();

  return (
    <div style={{ display: 'flex', flexDirection: 'column', height: '100%' }}>
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
  );
}
