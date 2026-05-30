import { useState, useEffect } from 'react';
import { motion, AnimatePresence } from 'framer-motion';
import { fetchNextItem, rateItem, imageUrl } from '../api/client';
import { useToast } from '../components/Toast';

export default function CompareScreen() {
  const [pair, setPair] = useState([null, null]);
  const [loading, setLoading] = useState(true);
  const [choosing, setChoosing] = useState(null);
  const toast = useToast();

  async function loadPair() {
    setLoading(true);
    try {
      const a = await fetchNextItem('random', 'training');
      const b = await fetchNextItem('random', 'training', a?.id);
      setPair([a, b]);
    } catch {
      setPair([null, null]);
    }
    setLoading(false);
  }

  useEffect(() => { loadPair(); }, []);

  async function pick(winner, loser) {
    setChoosing(winner.id);
    await Promise.all([
      rateItem(winner.id, 1),
      rateItem(loser.id, 0),
    ]).catch(() => toast('Failed to save', 'error'));
    toast('Saved! Next pair...', 'success');
    setTimeout(() => {
      setChoosing(null);
      loadPair();
    }, 400);
  }

  if (loading) {
    return (
      <div style={{ flex: 1, display: 'flex', flexDirection: 'column', paddingBottom: 'var(--content-pb)' }}>
        <div style={{ padding: '16px 20px 20px', flexShrink: 0 }}>
          <span style={{ fontFamily: 'Syne', fontWeight: 800, fontSize: 22, color: 'var(--text)', letterSpacing: '-0.5px' }}>Compare</span>
        </div>
        <div style={{ flex: 1, display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 10, padding: '0 16px' }}>
          <div className="skeleton" style={{ borderRadius: 16, minHeight: 300 }} />
          <div className="skeleton" style={{ borderRadius: 16, minHeight: 300 }} />
        </div>
      </div>
    );
  }

  const [a, b] = pair;
  if (!a || !b) {
    return (
      <div style={{ flex: 1, display: 'flex', alignItems: 'center', justifyContent: 'center', flexDirection: 'column', gap: 12, paddingBottom: 'var(--content-pb)' }}>
        <div style={{ fontSize: 40 }}>🎉</div>
        <div style={{ fontFamily: 'Syne', fontSize: 20, fontWeight: 700 }}>All compared!</div>
        <button onClick={loadPair} style={{ padding: '10px 24px', borderRadius: 20, background: 'var(--accent)', color: '#fff', fontWeight: 600, fontSize: 14 }}>Try again</button>
      </div>
    );
  }

  return (
    <div style={{ flex: 1, display: 'flex', flexDirection: 'column', overflow: 'hidden', paddingBottom: 'var(--content-pb)' }}>
      {/* Header */}
      <div style={{ padding: '16px 20px 12px', flexShrink: 0 }}>
        <span style={{ fontFamily: 'Syne', fontWeight: 800, fontSize: 22, color: 'var(--text)', letterSpacing: '-0.5px' }}>Compare</span>
        <p style={{ fontSize: 13, color: 'var(--text-2)', marginTop: 4 }}>Tap the one you like more</p>
      </div>

      {/* Cards side by side */}
      <div style={{ flex: 1, display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 10, padding: '0 16px', overflow: 'hidden' }}>
        {[a, b].map((item, idx) => (
          <motion.button
            key={item.id}
            onClick={() => pick(item, idx === 0 ? b : a)}
            whileTap={{ scale: 0.96 }}
            animate={choosing === item.id ? { scale: 1.04, boxShadow: '0 0 0 3px var(--like)' } : {}}
            style={{
              borderRadius: 16,
              overflow: 'hidden',
              background: 'var(--bg-card)',
              border: '1px solid var(--border)',
              display: 'flex',
              flexDirection: 'column',
              cursor: 'pointer',
              padding: 0,
              textAlign: 'left',
              transition: 'box-shadow 0.2s',
              minHeight: 0,
            }}
          >
            <div style={{ flex: 1, minHeight: 0, overflow: 'hidden', background: 'var(--surface)' }}>
              <img
                src={imageUrl(item.image_url)}
                alt={item.title}
                style={{ width: '100%', height: '100%', objectFit: 'cover' }}
              />
            </div>
            <div style={{ padding: '8px 10px', flexShrink: 0 }}>
              <div style={{ fontSize: 11, fontWeight: 500, color: 'var(--text)', overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>{item.title}</div>
              {item.price && <div style={{ fontSize: 12, fontWeight: 700, color: 'var(--accent-2)', fontFamily: 'Syne', marginTop: 2 }}>{item.price}</div>}
            </div>
          </motion.button>
        ))}
      </div>

      {/* Skip button */}
      <div style={{ padding: '12px 16px', flexShrink: 0, display: 'flex', justifyContent: 'center' }}>
        <button
          onClick={loadPair}
          style={{ padding: '8px 24px', borderRadius: 20, background: 'var(--surface)', color: 'var(--text-2)', border: '1px solid var(--border)', fontSize: 13, fontWeight: 500 }}
        >
          Skip pair
        </button>
      </div>
    </div>
  );
}
