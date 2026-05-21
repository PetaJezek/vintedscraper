import { useRef, useState } from 'react';
import CardStack from '../components/CardStack';

export default function SwipeScreen() {
  const [order, setOrder] = useState('random');    // random | best
  const [context, setContext] = useState('training'); // training | buy
  const undoRef = useRef(null);

  return (
    <div style={{
      flex: 1,
      display: 'flex',
      flexDirection: 'column',
      overflow: 'hidden',
      paddingBottom: 'var(--content-pb)',
    }}>
      {/* Header */}
      <div style={{
        padding: '16px 20px 10px',
        display: 'flex',
        alignItems: 'center',
        justifyContent: 'space-between',
        flexShrink: 0,
      }}>
        <span style={{ fontFamily: 'Syne', fontWeight: 800, fontSize: 22, color: 'var(--text)', letterSpacing: '-0.5px' }}>
          Discover
        </span>
        <button
          onClick={() => undoRef.current?.()}
          style={{
            width: 36, height: 36, borderRadius: 12,
            background: 'var(--surface)',
            border: '1px solid var(--border)',
            display: 'flex', alignItems: 'center', justifyContent: 'center',
            color: 'var(--text-2)',
          }}
          title="Undo"
        >
          <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
            <path d="M3 7v6h6"/>
            <path d="M21 17a9 9 0 0 0-9-9 9 9 0 0 0-6 2.3L3 13"/>
          </svg>
        </button>
      </div>

      {/* Toggles row */}
      <div style={{
        display: 'flex',
        gap: 8,
        padding: '0 20px 14px',
        flexShrink: 0,
        alignItems: 'center',
      }}>
        {/* Order toggle */}
        <ToggleGroup
          options={[
            { id: 'random', label: 'Random' },
            { id: 'best', label: 'Best first' },
          ]}
          value={order}
          onChange={setOrder}
        />

        {/* Divider */}
        <div style={{ width: 1, height: 20, background: 'var(--border)', flexShrink: 0 }} />

        {/* Context toggle */}
        <ToggleGroup
          options={[
            { id: 'training', label: '🎯 Train' },
            { id: 'buy', label: '🛍 Buy', accent: true },
          ]}
          value={context}
          onChange={setContext}
          accentActive={context === 'buy'}
        />
      </div>

      {/* Context hint */}
      {context === 'buy' && (
        <div style={{
          margin: '0 20px 10px',
          padding: '7px 12px',
          borderRadius: 10,
          background: 'var(--like-bg)',
          border: '1px solid rgba(34,197,94,0.2)',
          fontSize: 12,
          color: 'var(--like)',
          fontWeight: 500,
          flexShrink: 0,
        }}>
          Showing unsold items only
        </div>
      )}

      {/* Card area */}
      <div style={{
        flex: 1,
        position: 'relative',
        padding: '0 16px',
        overflow: 'hidden',
        minHeight: 0,
      }}>
        <CardStack order={order} context={context} onUndo={undoRef} />
      </div>

      {/* Hint labels */}
      <div style={{
        display: 'flex',
        justifyContent: 'space-between',
        padding: '10px 24px',
        flexShrink: 0,
        pointerEvents: 'none',
      }}>
        <span style={{ fontSize: 11, fontWeight: 600, color: 'var(--dislike)', opacity: 0.5, letterSpacing: '0.05em' }}>← NOPE</span>
        <span style={{ fontSize: 11, fontWeight: 600, color: 'var(--superlike)', opacity: 0.5, letterSpacing: '0.05em' }}>↓ SUPER</span>
        <span style={{ fontSize: 11, fontWeight: 600, color: 'var(--like)', opacity: 0.5, letterSpacing: '0.05em' }}>LIKE →</span>
      </div>
    </div>
  );
}

function ToggleGroup({ options, value, onChange, accentActive }) {
  return (
    <div style={{
      display: 'flex',
      background: 'var(--surface)',
      borderRadius: 20,
      padding: 3,
      gap: 2,
      border: '1px solid var(--border)',
    }}>
      {options.map(opt => {
        const active = value === opt.id;
        return (
          <button
            key={opt.id}
            onClick={() => onChange(opt.id)}
            style={{
              padding: '5px 12px',
              borderRadius: 16,
              fontSize: 12,
              fontWeight: 600,
              background: active
                ? (accentActive && opt.id === 'buy' ? 'var(--like)' : 'var(--bg-card)')
                : 'transparent',
              color: active
                ? (accentActive && opt.id === 'buy' ? '#fff' : 'var(--text)')
                : 'var(--text-3)',
              border: 'none',
              transition: 'all 0.18s',
              boxShadow: active ? '0 1px 4px rgba(0,0,0,0.15)' : 'none',
              whiteSpace: 'nowrap',
            }}
          >
            {opt.label}
          </button>
        );
      })}
    </div>
  );
}
