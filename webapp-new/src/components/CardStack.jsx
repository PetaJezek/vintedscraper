import { useState, useEffect, useCallback } from 'react';
import { AnimatePresence, motion } from 'framer-motion';
import SwipeCard from './SwipeCard';
import { fetchNextItem, rateItem, undoLastSwipe } from '../api/client';
import { useToast } from './Toast';

const PREFETCH_SIZE = 3;

export default function CardStack({ order = 'random', context = 'training', onUndo: onUndoRef }) {
  const [queue, setQueue] = useState([]);
  const [loading, setLoading] = useState(true);
  const [exhausted, setExhausted] = useState(false);
  const [history, setHistory] = useState([]);
  const toast = useToast();

  const fetchOne = useCallback(async () => {
    try {
      const item = await fetchNextItem(order, context);
      return item;
    } catch {
      return null;
    }
  }, [order, context]);

  const fillQueue = useCallback(async () => {
    const needed = PREFETCH_SIZE - queue.length;
    if (needed <= 0) return;
    const fetched = await Promise.all(Array.from({ length: needed }, fetchOne));
    const valid = fetched.filter(Boolean);
    if (valid.length === 0 && queue.length === 0) setExhausted(true);
    setQueue(q => {
      const existingIds = new Set(q.map(i => i.id));
      const newItems = valid.filter(i => !existingIds.has(i.id));
      return [...q, ...newItems];
    });
    setLoading(false);
  }, [queue.length, fetchOne]);

  // Reset when order or context changes
  useEffect(() => {
    setQueue([]);
    setLoading(true);
    setExhausted(false);
    setHistory([]);
  }, [order, context]);

  // Fill queue whenever it gets low
  useEffect(() => {
    if (!exhausted) fillQueue();
  }, [queue.length, order, context, exhausted]); // eslint-disable-line

  const handleSwipe = useCallback(async (itemId, rating, dir) => {
    const ratingLabels = { 0: '👎 Skipped', 1: '❤️ Liked', 2: '⭐ Super liked' };
    setHistory(h => [...h, { itemId, rating }]);
    setQueue(q => q.filter(i => i.id !== itemId));
    try {
      await rateItem(itemId, rating);
    } catch {
      toast('Rating failed to save', 'error');
    }
  }, [toast]);

  const handleUndo = useCallback(async () => {
    if (history.length === 0) { toast('Nothing to undo', 'info'); return; }
    try {
      const res = await undoLastSwipe();
      if (res?.item) {
        setQueue(q => [res.item, ...q]);
        setHistory(h => h.slice(0, -1));
        toast('Undone ↩', 'success');
      }
    } catch {
      // Backend may not support undo fully — just pop queue
      setHistory(h => h.slice(0, -1));
      toast('Undone ↩', 'success');
    }
  }, [history, toast]);

  // Expose undo to parent
  useEffect(() => {
    if (onUndoRef) onUndoRef.current = handleUndo;
  }, [handleUndo, onUndoRef]);

  if (loading) return <CardSkeleton />;
  if (exhausted && queue.length === 0) return <EmptyState />;

  return (
    <div style={{ position: 'relative', width: '100%', height: '100%' }}>
      <AnimatePresence>
        {queue.slice(0, 3).map((item, i) => {
          const isTop = i === 0;
          const scale = 1 - i * 0.035;
          const translateY = i * 10;
          return (
            <motion.div
              key={item.id}
              style={{
                position: 'absolute',
                inset: 0,
                zIndex: 10 - i,
              }}
              initial={isTop ? { scale: 0.92, opacity: 0 } : false}
              animate={{
                scale,
                y: translateY,
                opacity: 1,
              }}
              exit={{
                scale: 0.85,
                opacity: 0,
                transition: { duration: 0.2 },
              }}
              transition={{ type: 'spring', stiffness: 300, damping: 28 }}
            >
              <SwipeCard
                item={item}
                onSwipe={handleSwipe}
                isTop={isTop}
              />
            </motion.div>
          );
        })}
      </AnimatePresence>
    </div>
  );
}

function CardSkeleton() {
  return (
    <div style={{ width: '100%', height: '100%', borderRadius: 20, overflow: 'hidden' }}>
      <div className="skeleton" style={{ width: '100%', height: '70%', borderRadius: '20px 20px 0 0' }} />
      <div style={{ padding: 16, display: 'flex', flexDirection: 'column', gap: 10, background: 'var(--bg-card)' }}>
        <div className="skeleton" style={{ height: 20, width: '75%' }} />
        <div style={{ display: 'flex', gap: 8 }}>
          <div className="skeleton" style={{ height: 26, width: 60, borderRadius: 20 }} />
          <div className="skeleton" style={{ height: 26, width: 80, borderRadius: 20 }} />
        </div>
      </div>
    </div>
  );
}

function EmptyState() {
  return (
    <div style={{
      display: 'flex', flexDirection: 'column', alignItems: 'center', justifyContent: 'center',
      height: '100%', gap: 16, color: 'var(--text-2)',
    }}>
      <div style={{ fontSize: 52 }}>✨</div>
      <div style={{ fontFamily: 'Syne', fontSize: 20, fontWeight: 700, color: 'var(--text)' }}>All caught up!</div>
      <div style={{ fontSize: 14, textAlign: 'center', maxWidth: 220 }}>No more items in this queue. Try switching modes or scraping more.</div>
    </div>
  );
}
