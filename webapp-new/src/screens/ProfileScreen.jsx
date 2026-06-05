import { useState, useEffect, useRef } from 'react';
import { motion, AnimatePresence } from 'framer-motion';
import { useNavigate } from 'react-router-dom';
import {
  fetchStats, triggerScrape, triggerRetrain, triggerScoreMlp,
  triggerBuildBlocklist, triggerCheckSold, fetchJobStatus,
} from '../api/client';
import { useToast } from '../components/Toast';
import { useLang } from '../i18n';

const TRIGGERS = {
  scrape:    triggerScrape,
  retrain:   triggerRetrain,
  score:     triggerScoreMlp,
  sold:      triggerCheckSold,
  blocklist: triggerBuildBlocklist,
};

export default function ProfileScreen() {
  const [stats, setStats] = useState(null);
  const [loading, setLoading] = useState(true);
  const [running, setRunning] = useState(null);
  const [job, setJob] = useState(null);   // live job status { name, status, label, log[] }
  const pollRef = useRef(null);
  const toast = useToast();
  const { t } = useLang();

  function refreshStats() {
    fetchStats().then(setStats).catch(() => {});
  }

  // On mount: load stats + resume showing any job already running on the server.
  useEffect(() => {
    fetchStats().then(setStats).catch(() => {}).finally(() => setLoading(false));
    fetchJobStatus().then(s => {
      if (s.running && s.current) { setJob(s.current); setRunning(s.current.name); startPolling(); }
    }).catch(() => {});
    return () => clearInterval(pollRef.current);
  }, []);

  function startPolling() {
    clearInterval(pollRef.current);
    pollRef.current = setInterval(async () => {
      try {
        const s = await fetchJobStatus();
        setJob(s.current);
        if (!s.running) {
          clearInterval(pollRef.current);
          setRunning(null);
          if (s.current?.status === 'done') { toast(`${s.current.label} finished`, 'success'); refreshStats(); }
          else if (s.current?.status === 'error') toast(`${s.current.label} failed — see log`, 'error');
        }
      } catch { /* keep polling */ }
    }, 1500);
  }

  async function run(action, label) {
    if (running) return;
    setRunning(action);
    setJob({ name: action, status: 'running', label, log: ['Starting…'] });
    try {
      const res = await TRIGGERS[action]();
      if (res?.status === 'busy') { toast('Another job is already running', 'error'); setRunning(null); return; }
      startPolling();
    } catch {
      toast(`${label} failed to start`, 'error');
      setRunning(null);
    }
  }

  const navigate = useNavigate();
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
    { id: 'scrape',    label: t('act.scrape'),    desc: t('act.scrape.desc'),    icon: '🛍️', color: '#06b6d4' },
    { id: 'retrain',   label: t('act.retrain'),   desc: t('act.retrain.desc'),   icon: '🧠', color: '#7c6cf8' },
    { id: 'score',     label: t('act.score'),     desc: t('act.score.desc'),     icon: '✨', color: '#22c55e' },
    { id: 'sold',      label: t('act.sold'),      desc: t('act.sold.desc'),      icon: '🏷️', color: '#ef4444' },
    { id: 'blocklist', label: t('act.blocklist'), desc: t('act.blocklist.desc'), icon: '🚫', color: '#f59e0b' },
  ];

  return (
    <div style={{ flex: 1, display: 'flex', flexDirection: 'column', overflow: 'hidden', paddingBottom: 'var(--content-pb)' }}>
      <div style={{ flex: 1, overflowY: 'auto' }}>
        {/* Header */}
        <div style={{ padding: '16px 20px 20px', display: 'flex', alignItems: 'center' }}>
          <span style={{ fontFamily: 'Syne', fontWeight: 800, fontSize: 22, color: 'var(--text)', letterSpacing: '-0.5px', flex: 1 }}>{t('profile.title')}</span>
          <button
            onClick={() => navigate('/config')}
            title="Scraper settings"
            style={{ background: 'var(--surface)', border: '1px solid var(--border)', borderRadius: 10, width: 36, height: 36, display: 'flex', alignItems: 'center', justifyContent: 'center', cursor: 'pointer', color: 'var(--text-2)' }}
          >
            <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
              <circle cx="12" cy="12" r="3"/><path d="M19.4 15a1.65 1.65 0 00.33 1.82l.06.06a2 2 0 010 2.83 2 2 0 01-2.83 0l-.06-.06a1.65 1.65 0 00-1.82-.33 1.65 1.65 0 00-1 1.51V21a2 2 0 01-4 0v-.09A1.65 1.65 0 009 19.4a1.65 1.65 0 00-1.82.33l-.06.06a2 2 0 01-2.83-2.83l.06-.06A1.65 1.65 0 004.68 15a1.65 1.65 0 00-1.51-1H3a2 2 0 010-4h.09A1.65 1.65 0 004.6 9a1.65 1.65 0 00-.33-1.82l-.06-.06a2 2 0 012.83-2.83l.06.06A1.65 1.65 0 009 4.68a1.65 1.65 0 001-1.51V3a2 2 0 014 0v.09a1.65 1.65 0 001 1.51 1.65 1.65 0 001.82-.33l.06-.06a2 2 0 012.83 2.83l-.06.06A1.65 1.65 0 0019.4 9a1.65 1.65 0 001.51 1H21a2 2 0 010 4h-.09a1.65 1.65 0 00-1.51 1z"/>
            </svg>
          </button>
        </div>

        {/* Stats grid */}
        <div style={{ padding: '0 16px', marginBottom: 28 }}>
          <div style={{ fontSize: 12, fontWeight: 600, letterSpacing: '0.08em', color: 'var(--text-3)', marginBottom: 10, textTransform: 'uppercase' }}>{t('sec.stats')}</div>
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
            <div style={{ fontSize: 12, fontWeight: 600, letterSpacing: '0.08em', color: 'var(--text-3)', marginBottom: 10, textTransform: 'uppercase' }}>{t('sec.scoredist')}</div>
            <div style={{ background: 'var(--bg-card)', borderRadius: 14, border: '1px solid var(--border)', padding: '16px 12px', display: 'flex', alignItems: 'flex-end', gap: 4, height: 80 }}>
              {stats.score_histogram.map((v, i) => (
                <div key={i} style={{ flex: 1, background: 'var(--accent)', borderRadius: 3, opacity: 0.7, height: `${Math.max(4, v)}%` }} />
              ))}
            </div>
          </div>
        )}

        {/* Pipeline actions */}
        <div style={{ padding: '0 16px 20px' }}>
          <div style={{ fontSize: 12, fontWeight: 600, letterSpacing: '0.08em', color: 'var(--text-3)', marginBottom: 10, textTransform: 'uppercase' }}>{t('sec.pipeline')}</div>

          {/* Live job progress */}
          <AnimatePresence>
            {job && (
              <motion.div
                initial={{ opacity: 0, height: 0 }}
                animate={{ opacity: 1, height: 'auto' }}
                exit={{ opacity: 0, height: 0 }}
                style={{ overflow: 'hidden', marginBottom: 12 }}
              >
                <div style={{ background: 'var(--bg-card)', border: '1px solid var(--border)', borderRadius: 14, padding: '12px 14px' }}>
                  <div style={{ display: 'flex', alignItems: 'center', gap: 10, marginBottom: 8 }}>
                    {job.status === 'running'
                      ? <Spinner />
                      : <span style={{ fontSize: 16 }}>{job.status === 'done' ? '✅' : '⚠️'}</span>}
                    <span style={{ fontSize: 14, fontWeight: 600, color: 'var(--text)', flex: 1 }}>{job.label}</span>
                    <span style={{ fontSize: 11, color: 'var(--text-3)', textTransform: 'uppercase', letterSpacing: '0.06em' }}>{job.status}</span>
                  </div>
                  <div style={{
                    background: 'var(--surface)', borderRadius: 8, padding: '8px 10px',
                    fontFamily: 'monospace', fontSize: 11, lineHeight: 1.5,
                    color: 'var(--text-2)', maxHeight: 120, overflowY: 'auto',
                    whiteSpace: 'pre-wrap', wordBreak: 'break-word',
                  }}>
                    {(job.log || []).slice(-8).join('\n') || '…'}
                  </div>
                </div>
              </motion.div>
            )}
          </AnimatePresence>

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
