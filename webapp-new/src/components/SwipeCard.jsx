import { useRef, useState } from 'react';
import { motion, useMotionValue, useTransform, useSpring, animate } from 'framer-motion';
import { imageUrl } from '../api/client';

const SWIPE_THRESHOLD = 80;
const ROTATION_FACTOR = 0.08;

export default function SwipeCard({ item, onSwipe, style, isTop }) {
  const cardRef = useRef(null);
  const x = useMotionValue(0);
  const y = useMotionValue(0);
  const [isDragging, setIsDragging] = useState(false);
  const [imgLoaded, setImgLoaded] = useState(false);

  const rotate = useTransform(x, [-200, 0, 200], [-18, 0, 18]);

  // Colour overlays
  const likeOpacity = useTransform(x, [0, SWIPE_THRESHOLD], [0, 1]);
  const dislikeOpacity = useTransform(x, [-SWIPE_THRESHOLD, 0], [1, 0]);
  const superlikeOpacity = useTransform(y, [SWIPE_THRESHOLD, 0], [1, 0]);

  const score = item?.predicted_score;
  const scoreColor = score >= 80 ? '#22c55e' : score >= 60 ? '#f59e0b' : score >= 40 ? '#9898b8' : '#ef4444';

  function handleDragEnd(_, info) {
    const { offset, velocity } = info;
    const vx = velocity.x, vy = velocity.y;

    if (offset.x > SWIPE_THRESHOLD || vx > 500) {
      flyOut('right');
    } else if (offset.x < -SWIPE_THRESHOLD || vx < -500) {
      flyOut('left');
    } else if (offset.y > SWIPE_THRESHOLD || vy > 500) {
      flyOut('down');
    } else {
      // Spring back
      animate(x, 0, { type: 'spring', stiffness: 400, damping: 30 });
      animate(y, 0, { type: 'spring', stiffness: 400, damping: 30 });
    }
    setIsDragging(false);
  }

  function flyOut(dir) {
    const targets = {
      right:  { x: 500, y: 0, rating: 1 },
      left:   { x: -500, y: 0, rating: 0 },
      down:   { x: 0, y: 600, rating: 2 },
    };
    const { x: tx, y: ty, rating } = targets[dir];
    animate(x, tx, { duration: 0.35, ease: 'easeIn' });
    animate(y, ty, { duration: 0.35, ease: 'easeIn' });
    setTimeout(() => onSwipe(item.id, rating, dir), 300);
  }

  if (!item) return null;

  return (
    <motion.div
      ref={cardRef}
      style={{
        position: 'absolute',
        width: '100%',
        height: '100%',
        x,
        y,
        rotate,
        cursor: isDragging ? 'grabbing' : 'grab',
        touchAction: 'none',
        ...style,
      }}
      drag={isTop}
      dragConstraints={{ left: 0, right: 0, top: 0, bottom: 0 }}
      dragElastic={0.8}
      onDragStart={() => setIsDragging(true)}
      onDragEnd={handleDragEnd}
      whileTap={{ scale: 1.02 }}
    >
      {/* Card body */}
      <div style={{
        width: '100%',
        height: '100%',
        borderRadius: 20,
        overflow: 'hidden',
        background: 'var(--bg-card)',
        border: '1px solid var(--border)',
        display: 'flex',
        flexDirection: 'column',
        boxShadow: '0 20px 60px rgba(0,0,0,0.5)',
        position: 'relative',
      }}>
        {/* Image area — 70% height */}
        <div style={{ position: 'relative', flex: '0 0 70%', overflow: 'hidden', background: 'var(--surface)' }}>
          {!imgLoaded && (
            <div className="skeleton" style={{ position: 'absolute', inset: 0, borderRadius: 0 }} />
          )}
          <img
            src={imageUrl(item.image_url)}
            alt={item.title}
            onLoad={() => setImgLoaded(true)}
            style={{
              width: '100%',
              height: '100%',
              objectFit: 'cover',
              opacity: imgLoaded ? 1 : 0,
              transition: 'opacity 0.3s',
            }}
          />

          {/* Score badge */}
          {score != null && (
            <div style={{
              position: 'absolute', top: 12, right: 12,
              background: 'rgba(8,8,15,0.85)',
              backdropFilter: 'blur(8px)',
              border: `1px solid ${scoreColor}44`,
              borderRadius: 20,
              padding: '4px 10px',
              fontSize: 12,
              fontWeight: 700,
              color: scoreColor,
              fontFamily: 'Syne, sans-serif',
            }}>
              {Math.round(score)}
            </div>
          )}

          {/* Swipe direction overlays */}
          <motion.div style={{
            position: 'absolute', inset: 0,
            background: 'linear-gradient(135deg, rgba(34,197,94,0.6) 0%, transparent 60%)',
            opacity: likeOpacity,
            pointerEvents: 'none',
            display: 'flex', alignItems: 'flex-start', justifyContent: 'flex-start',
            padding: 20,
          }}>
            <span style={{ fontSize: 36, fontWeight: 800, color: '#fff', fontFamily: 'Syne', textShadow: '0 2px 8px rgba(0,0,0,0.5)', transform: 'rotate(-8deg)', display: 'block' }}>LIKE</span>
          </motion.div>

          <motion.div style={{
            position: 'absolute', inset: 0,
            background: 'linear-gradient(225deg, rgba(239,68,68,0.6) 0%, transparent 60%)',
            opacity: dislikeOpacity,
            pointerEvents: 'none',
            display: 'flex', alignItems: 'flex-start', justifyContent: 'flex-end',
            padding: 20,
          }}>
            <span style={{ fontSize: 36, fontWeight: 800, color: '#fff', fontFamily: 'Syne', textShadow: '0 2px 8px rgba(0,0,0,0.5)', transform: 'rotate(8deg)', display: 'block' }}>NOPE</span>
          </motion.div>

          <motion.div style={{
            position: 'absolute', inset: 0,
            background: 'linear-gradient(0deg, rgba(245,158,11,0.7) 0%, transparent 60%)',
            opacity: superlikeOpacity,
            pointerEvents: 'none',
            display: 'flex', alignItems: 'flex-end', justifyContent: 'center',
            padding: 20,
          }}>
            <span style={{ fontSize: 32, fontWeight: 800, color: '#fff', fontFamily: 'Syne', textShadow: '0 2px 8px rgba(0,0,0,0.5)' }}>⭐ SUPER</span>
          </motion.div>

          {/* Bottom gradient for text readability */}
          <div style={{
            position: 'absolute', bottom: 0, left: 0, right: 0, height: 60,
            background: 'linear-gradient(transparent, rgba(8,8,15,0.8))',
            pointerEvents: 'none',
          }} />
        </div>

        {/* Info area — 30% */}
        <div style={{
          flex: 1,
          padding: '14px 16px',
          display: 'flex',
          flexDirection: 'column',
          gap: 6,
          overflow: 'hidden',
        }}>
          <div style={{ fontSize: 15, fontWeight: 600, color: 'var(--text)', lineHeight: 1.3, overflow: 'hidden', display: '-webkit-box', WebkitLineClamp: 2, WebkitBoxOrient: 'vertical' }}>
            {item.title}
          </div>

          <div style={{ display: 'flex', gap: 6, flexWrap: 'wrap', alignItems: 'center' }}>
            {item.price && (
              <span style={{
                background: 'var(--accent)', color: '#fff',
                borderRadius: 20, padding: '3px 10px',
                fontSize: 13, fontWeight: 700, fontFamily: 'Syne',
              }}>
                {item.price}
              </span>
            )}
            {item.brand && (
              <span style={{
                background: 'var(--surface)', color: 'var(--text-2)',
                borderRadius: 20, padding: '3px 10px',
                fontSize: 12, fontWeight: 500,
                border: '1px solid var(--border)',
              }}>
                {item.brand}
              </span>
            )}
            {item.size && (
              <span style={{
                background: 'var(--surface)', color: 'var(--text-2)',
                borderRadius: 20, padding: '3px 10px',
                fontSize: 12, fontWeight: 500,
                border: '1px solid var(--border)',
              }}>
                {item.size}
              </span>
            )}
            {item.tag && (
              <span style={{
                background: 'transparent', color: 'var(--text-3)',
                fontSize: 11, marginLeft: 'auto',
              }}>
                {item.tag}
              </span>
            )}
          </div>
        </div>
      </div>
    </motion.div>
  );
}
