import { useState, useEffect } from 'react';
import { motion } from 'framer-motion';
import { fetchStats, triggerRetrain, triggerRescore, triggerScoreMlp, triggerBuildBlocklist, triggerCheckSold } from '../api/client';
import { useToast } from '../components/Toast';

export default function ProfileScreen() {
  const [stats, setStats] = useState(null);
  const [loading, setLoading] = useState(true);
  const [running, setRunning] = useState(null);
  const toast = useToast();

  useEffect(() => {
    fetchStats()
      .then(setStats)
      .catch(() => {})
      .finally(() => setLoading(false));
  }, []);

  async function run(action, label) {
    setRunning(action);
    try {
      if (action === 'retrain') await triggerRetrain();
      else if (action === 'rescore') await triggerRescore();
      else if (action === 'score_mlp') await triggerScoreMlp();
      else if (action === 'blocklist') await triggerBuildBlocklist();
      else if (action === 'sold') await triggerCheckSold();
      toast(`${label} started!`, 'success');
    } catch {
      toast(`${label} failed`, 'error');
    }
    setRunning(null);
  }

  const s = stats || {};

  const statItems = [
    { label: 'Total items', value: s.total ?? '—', icon: '📦' },
    { label: 'Rated', value: s.rated ?? '—', icon: '🏷️' },
    { label: 'Liked', value: s.liked ?? '—', icon: '❤️' },
    { label: 'Disliked', value: s.disliked ?? '—', icon: '👎' },
    { label: 'Super liked', value: s.super_liked ?? '—', icon: '⭐' },
    { label: 'Model age', value: s.model_age ?? '—', icon: '🤖' },
  ];

  const actions = [
    { id: 'score_mlp', label: 'Score with MLP', desc: 'Re-rank using your trained model', icon: '🤖', color: '#7c6cf8' },
    { id: 'retrain',   label: 'Retrain model',  desc: 'Train on accumulated ratings',  icon: '🧠', color: '#9b8fff' },
    { id: 'rescore',   label: 'Rescore (legacy)', desc: 'Similarity-based fallback',   icon: '🔄', color: '#22c55e' },
    { id: 'sold',      label: 'Check sold',      desc: 'Mark unavailable items',        icon: '🏷️', color: '#ef4444' },
    { id: 'blocklist', label: 'Build blocklist', desc: 'Update Polish filter',          icon: '🚫', color: '#f59e0b' },
  ];

  return (
    <div style={{ flex: 1, display: 'flex', flexDirection: 'column', overflow: 'hidden', paddingBottom: 'var(--content-pb)' }}>
      <div style={{ flex: 1, overflowY: 'auto' }}>
        {/* Header */}
        <div style={{ padding: '16px 20px 20px' }}>
          <span style={{ fontFamily: 'Syne', fontWeight: 800, fontSize: 22, color: 'var(--text)', letterSpacing: '-0.5px' }}>Profile</span>
        </div>

        {/* Stats grid */}
        <div style={{ padding: '0 16px', marginBottom: 28 }}>
          <div style={{ fontSize: 12, fontWeight: 600, letterSpacing: '0.08em', color: 'var(--text-3)', marginBottom: 10, textTransform: 'uppercase' }}>Stats</div>
          <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr 1fr', gap: 8 }}>
            {statItems.map((s, i) => (
              <motion.div
                key={s.label}
                initial={{ opacity: 0, y: 8 }}
                animate={{ opacity: 1, y: 0 }}
                transition={{ delay: i * 0.06 }}
                style={{
                  background: 'var(--bg-card)',
                  border: '1px solid var(--border)',
                  borderRadius: 14,
                  padding: '12px 10px',
                  textAlign: 'center',
                }}
              >
                <div style={{ fontSize: 20, marginBottom: 4 }}>{s.icon}</div>
                <div style={{
                  fontFamily: 'Syne', fontWeight: 800, fontSize: 20,
                  color: loading ? 'transparent' : 'var(--text)',
                  background: loading ? 'var(--surface)' : 'none',
                  borderRadius: loading ? 6 : 0,
                  minHeight: 28,
                }}>
                  {loading ? '' : s.value}
                </div>
                <div style={{ fontSize: 10, color: 'var(--text-3)', marginTop: 2, lineHeight: 1.2 }}>{s.label}</div>
              </motion.div>
            ))}
          </div>
        </div>

        {/* Score histogram placeholder */}
        {stats?.score_histogram && (
          <div style={{ padding: '0 16px', marginBottom: 28 }}>
            <div style={{ fontSize: 12, fontWeight: 600, letterSpacing: '0.08em', color: 'var(--text-3)', marginBottom: 10, textTransform: 'uppercase' }}>Score distribution</div>
            <div style={{ background: 'var(--bg-card)', borderRadius: 14, border: '1px solid var(--border)', padding: '16px 12px', display: 'flex', alignItems: 'flex-end', gap: 4, height: 80 }}>
              {stats.score_histogram.map((v, i) => (
                <div key={i} style={{ flex: 1, background: 'var(--accent)', borderRadius: 3, opacity: 0.7, height: `${Math.max(4, v)}%` }} />
              ))}
            </div>
          </div>
        )}

        {/* Pipeline actions */}
        <div style={{ padding: '0 16px 20px' }}>
          <div style={{ fontSize: 12, fontWeight: 600, letterSpacing: '0.08em', color: 'var(--text-3)', marginBottom: 10, textTransform: 'uppercase' }}>Pipeline</div>
          <div style={{ display: 'flex', flexDirection: 'column', gap: 10 }}>
            {actions.map((a, i) => (
              <motion.button
                key={a.id}
                initial={{ opacity: 0, x: -8 }}
                animate={{ opacity: 1, x: 0 }}
                transition={{ delay: 0.15 + i * 0.07 }}
                onClick={() => run(a.id, a.label)}
                disabled={running !== null}
                style={{
                  background: 'var(--bg-card)',
                  border: `1px solid ${running === a.id ? a.color + '88' : 'var(--border)'}`,
                  borderRadius: 14,
                  padding: '14px 16px',
                  display: 'flex',
                  alignItems: 'center',
                  gap: 14,
                  cursor: running !== null ? 'not-allowed' : 'pointer',
                  opacity: running !== null && running !== a.id ? 0.5 : 1,
                  transition: 'all 0.2s',
                  textAlign: 'left',
                }}
              >
                <div style={{
                  width: 42, height: 42, borderRadius: 12,
                  background: `${a.color}18`,
                  border: `1px solid ${a.color}33`,
                  display: 'flex', alignItems: 'center', justifyContent: 'center',
                  fontSize: 20, flexShrink: 0,
                }}>
                  {running === a.id ? <Spinner /> : a.icon}
                </div>
                <div>
                  <div style={{ fontSize: 14, fontWeight: 600, color: 'var(--text)' }}>{a.label}</div>
                  <div style={{ fontSize: 12, color: 'var(--text-2)', marginTop: 2 }}>{a.desc}</div>
                </div>
                <div style={{ marginLeft: 'auto', color: 'var(--text-3)' }}>
                  <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
                    <path d="M5 12h14M12 5l7 7-7 7"/>
                  </svg>
                </div>
              </motion.button>
            ))}
          </div>
        </div>

        {/* App info */}
        <div style={{ padding: '0 16px 24px', textAlign: 'center', color: 'var(--text-3)', fontSize: 12 }}>
          <div style={{ fontFamily: 'Syne', fontWeight: 700, fontSize: 14, color: 'var(--text-2)', marginBottom: 4 }}>Vinted AI</div>
          <div>Fashion recommendation engine</div>
          {stats?.top_categories && (
            <div style={{ marginTop: 8, display: 'flex', gap: 6, flexWrap: 'wrap', justifyContent: 'center' }}>
              {stats.top_categories.map(c => (
                <span key={c} style={{ background: 'var(--surface)', borderRadius: 20, padding: '3px 10px', fontSize: 11 }}>{c}</span>
              ))}
            </div>
          )}
        </div>
      </div>
    </div>
  );
}

function Spinner() {
  return (
    <motion.div
      animate={{ rotate: 360 }}
      transition={{ duration: 0.8, repeat: Infinity, ease: 'linear' }}
      style={{ width: 18, height: 18, borderRadius: '50%', border: '2px solid rgba(255,255,255,0.2)', borderTopColor: '#fff' }}
    />
  );
}
