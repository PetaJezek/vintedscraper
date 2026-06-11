import { NavLink } from 'react-router-dom';
import { motion } from 'framer-motion';
import { useLang } from '../i18n';

const tabs = [
  { to: '/', key: 'nav.swipe', icon: SwipeIcon },
  { to: '/compare', key: 'nav.compare', icon: CompareIcon },
  { to: '/liked', key: 'nav.liked', icon: HeartIcon },
  { to: '/profile', key: 'nav.profile', icon: ProfileIcon },
  { to: '/config', key: 'nav.setup', icon: GearIcon },
];

export default function BottomNav() {
  const { t } = useLang();
  return (
    <nav style={{
      flexShrink: 0,
      width: '100%',
      height: 'calc(var(--nav-h) + env(safe-area-inset-bottom, 0px))',
      paddingBottom: 'env(safe-area-inset-bottom, 0px)',
      background: 'color-mix(in srgb, var(--bg) 78%, transparent)',
      backdropFilter: 'blur(22px) saturate(1.4)',
      WebkitBackdropFilter: 'blur(22px) saturate(1.4)',
      borderTop: '1px solid var(--border)',
      display: 'flex',
      zIndex: 100,
    }}>
      {tabs.map(({ to, key, icon: Icon }) => (
        <NavLink
          key={to}
          to={to}
          end={to === '/'}
          style={{ flex: 1, display: 'flex', flexDirection: 'column', alignItems: 'center', justifyContent: 'center', gap: 4, position: 'relative' }}
        >
          {({ isActive }) => (
            <>
              {isActive && (
                <motion.div
                  layoutId="nav-pill"
                  style={{
                    position: 'absolute', top: 0, left: '50%', transform: 'translateX(-50%)',
                    width: 32, height: 2, borderRadius: 2,
                    background: 'var(--accent-2)',
                    boxShadow: '0 0 10px var(--accent)',
                  }}
                  transition={{ type: 'spring', stiffness: 500, damping: 35 }}
                />
              )}
              <Icon active={isActive} />
              <span style={{
                fontSize: 10, fontWeight: 500, letterSpacing: '0.04em',
                color: isActive ? 'var(--accent-2)' : 'var(--text-3)',
                transition: 'color 0.2s',
              }}>
                {t(key)}
              </span>
            </>
          )}
        </NavLink>
      ))}
    </nav>
  );
}

function SwipeIcon({ active }) {
  return (
    <svg width="22" height="22" viewBox="0 0 24 24" fill="none" stroke={active ? 'var(--accent-2)' : 'var(--text-3)'} strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round" style={{ transition: 'stroke 0.2s' }}>
      <path d="M19 14c1.49-1.46 3-3.21 3-5.5A5.5 5.5 0 0 0 16.5 3c-1.76 0-3 .5-4.5 2-1.5-1.5-2.74-2-4.5-2A5.5 5.5 0 0 0 2 8.5c0 2.3 1.5 4.05 3 5.5l7 7Z"/>
    </svg>
  );
}

function CompareIcon({ active }) {
  return (
    <svg width="22" height="22" viewBox="0 0 24 24" fill="none" stroke={active ? 'var(--accent-2)' : 'var(--text-3)'} strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round" style={{ transition: 'stroke 0.2s' }}>
      <rect x="2" y="3" width="9" height="18" rx="2"/>
      <rect x="13" y="3" width="9" height="18" rx="2"/>
    </svg>
  );
}

function HeartIcon({ active }) {
  return (
    <svg width="22" height="22" viewBox="0 0 24 24" fill={active ? 'var(--accent-2)' : 'none'} stroke={active ? 'var(--accent-2)' : 'var(--text-3)'} strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round" style={{ transition: 'all 0.2s' }}>
      <path d="M20.84 4.61a5.5 5.5 0 0 0-7.78 0L12 5.67l-1.06-1.06a5.5 5.5 0 0 0-7.78 7.78l1.06 1.06L12 21.23l7.78-7.78 1.06-1.06a5.5 5.5 0 0 0 0-7.78z"/>
    </svg>
  );
}

function ProfileIcon({ active }) {
  return (
    <svg width="22" height="22" viewBox="0 0 24 24" fill="none" stroke={active ? 'var(--accent-2)' : 'var(--text-3)'} strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round" style={{ transition: 'stroke 0.2s' }}>
      <circle cx="12" cy="8" r="4"/>
      <path d="M4 20c0-4 3.6-7 8-7s8 3 8 7"/>
    </svg>
  );
}

function GearIcon({ active }) {
  return (
    <svg width="22" height="22" viewBox="0 0 24 24" fill="none" stroke={active ? 'var(--accent-2)' : 'var(--text-3)'} strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round" style={{ transition: 'stroke 0.2s' }}>
      <circle cx="12" cy="12" r="3"/>
      <path d="M19.4 15a1.65 1.65 0 00.33 1.82l.06.06a2 2 0 010 2.83 2 2 0 01-2.83 0l-.06-.06a1.65 1.65 0 00-1.82-.33 1.65 1.65 0 00-1 1.51V21a2 2 0 01-4 0v-.09A1.65 1.65 0 009 19.4a1.65 1.65 0 00-1.82.33l-.06.06a2 2 0 01-2.83-2.83l.06-.06A1.65 1.65 0 004.68 15a1.65 1.65 0 00-1.51-1H3a2 2 0 010-4h.09A1.65 1.65 0 004.6 9a1.65 1.65 0 00-.33-1.82l-.06-.06a2 2 0 012.83-2.83l.06.06A1.65 1.65 0 009 4.68a1.65 1.65 0 001-1.51V3a2 2 0 014 0v.09a1.65 1.65 0 001 1.51 1.65 1.65 0 001.82-.33l.06-.06a2 2 0 012.83 2.83l-.06.06A1.65 1.65 0 0019.4 9a1.65 1.65 0 001.51 1H21a2 2 0 010 4h-.09a1.65 1.65 0 00-1.51 1z"/>
    </svg>
  );
}
