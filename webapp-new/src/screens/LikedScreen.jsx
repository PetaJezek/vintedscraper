import { useState, useEffect } from 'react';
import { motion } from 'framer-motion';
import { fetchLiked, imageUrl } from '../api/client';

export default function LikedScreen() {
  const [items, setItems] = useState([]);
  const [loading, setLoading] = useState(true);
  const [filter, setFilter] = useState('all'); // all | liked | superliked

  useEffect(() => {
    fetchLiked()
      .then(data => {
        setItems(Array.isArray(data) ? data : data.items ?? []);
      })
      .catch(() => setItems([]))
      .finally(() => setLoading(false));
  }, []);

  const filtered = items.filter(i => {
    if (filter === 'liked') return i.rating === 1;
    if (filter === 'superliked') return i.rating === 2;
    return i.rating >= 1;
  });

  return (
    <div style={{ flex: 1, display: 'flex', flexDirection: 'column', overflow: 'hidden', paddingBottom: 'var(--content-pb)' }}>
      {/* Header */}
      <div style={{ padding: '16px 20px 12px', flexShrink: 0 }}>
        <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between' }}>
          <span style={{ fontFamily: 'Syne', fontWeight: 800, fontSize: 22, color: 'var(--text)', letterSpacing: '-0.5px' }}>
            Liked
          </span>
          <span style={{ fontSize: 13, color: 'var(--text-3)' }}>{filtered.length} items</span>
        </div>

        {/* Filter chips */}
        <div style={{ display: 'flex', gap: 8, marginTop: 12 }}>
          {[['all', 'All'], ['liked', '❤️ Liked'], ['superliked', '⭐ Super']].map(([val, label]) => (
            <button
              key={val}
              onClick={() => setFilter(val)}
              style={{
                padding: '5px 12px', borderRadius: 20, fontSize: 12, fontWeight: 600,
                background: filter === val ? 'var(--accent)' : 'var(--surface)',
                color: filter === val ? '#fff' : 'var(--text-2)',
                border: filter === val ? '1px solid var(--accent)' : '1px solid var(--border)',
                transition: 'all 0.2s',
              }}
            >
              {label}
            </button>
          ))}
        </div>
      </div>

      {/* Grid */}
      <div style={{ flex: 1, overflowY: 'auto', padding: '0 16px 16px' }}>
        {loading ? (
          <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 10 }}>
            {Array.from({ length: 6 }).map((_, i) => (
              <div key={i} className="skeleton" style={{ aspectRatio: '0.75', borderRadius: 12 }} />
            ))}
          </div>
        ) : filtered.length === 0 ? (
          <div style={{
            display: 'flex', flexDirection: 'column', alignItems: 'center', justifyContent: 'center',
            height: '60vh', gap: 12, color: 'var(--text-2)',
          }}>
            <div style={{ fontSize: 40 }}>💔</div>
            <div style={{ fontFamily: 'Syne', fontSize: 18, fontWeight: 700, color: 'var(--text)' }}>Nothing here yet</div>
            <div style={{ fontSize: 13 }}>Go swipe some items!</div>
          </div>
        ) : (
          <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 10 }}>
            {filtered.map((item, i) => (
              <motion.a
                key={item.id}
                href={item.url || `https://www.vinted.cz/items/${item.id}`}
                target="_blank"
                rel="noopener noreferrer"
                initial={{ opacity: 0, y: 12 }}
                animate={{ opacity: 1, y: 0 }}
                transition={{ delay: i * 0.04, duration: 0.25 }}
                style={{
                  borderRadius: 12,
                  overflow: 'hidden',
                  background: 'var(--bg-card)',
                  border: '1px solid var(--border)',
                  display: 'flex',
                  flexDirection: 'column',
                  textDecoration: 'none',
                  position: 'relative',
                }}
              >
                {/* Rating badge */}
                <div style={{
                  position: 'absolute', top: 8, right: 8, zIndex: 2,
                  fontSize: 14,
                }}>
                  {item.rating === 2 ? '⭐' : '❤️'}
                </div>

                {/* Image */}
                <div style={{ aspectRatio: '0.75', background: 'var(--surface)', overflow: 'hidden' }}>
                  <img
                    src={imageUrl(item.image_url)}
                    alt={item.title}
                    loading="lazy"
                    style={{ width: '100%', height: '100%', objectFit: 'cover' }}
                  />
                </div>

                {/* Info */}
                <div style={{ padding: '8px 10px', display: 'flex', flexDirection: 'column', gap: 4 }}>
                  <div style={{ fontSize: 12, fontWeight: 500, color: 'var(--text)', overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>
                    {item.title}
                  </div>
                  <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between' }}>
                    {item.price && (
                      <span style={{ fontSize: 12, fontWeight: 700, color: 'var(--accent-2)', fontFamily: 'Syne' }}>
                        {item.price}
                      </span>
                    )}
                    <span style={{ fontSize: 10, color: 'var(--text-3)' }}>Open ↗</span>
                  </div>
                </div>
              </motion.a>
            ))}
          </div>
        )}
      </div>
    </div>
  );
}
