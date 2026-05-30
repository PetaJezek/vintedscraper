import { useState, useEffect, useRef } from 'react';
import { useNavigate } from 'react-router-dom';
import { motion, AnimatePresence } from 'framer-motion';
import { fetchConfig, saveConfig } from '../api/client';
import { useToast } from '../components/Toast';

// Strip junk params Vinted adds that expire and break scraping
function cleanVintedUrl(raw) {
  try {
    const u = new URL(raw.trim());
    ['search_id', 'time', 'session_id', 'source', 'ref'].forEach(p => u.searchParams.delete(p));
    return u.toString();
  } catch {
    return raw.trim();
  }
}

export default function ConfigScreen() {
  const navigate  = useNavigate();
  const toast     = useToast();
  const [cfg, setCfg]       = useState(null);
  const [loading, setLoading] = useState(true);
  const [saving, setSaving]   = useState(false);
  const [dirty, setDirty]     = useState(false);
  const [addUrl, setAddUrl]   = useState('');
  const [addLabel, setAddLabel] = useState('');
  const [showAdd, setShowAdd] = useState(false);
  const addInputRef = useRef(null);

  useEffect(() => {
    fetchConfig()
      .then(data => { setCfg(data); setLoading(false); })
      .catch(() => { toast('Failed to load config', 'error'); setLoading(false); });
  }, []);

  useEffect(() => {
    if (showAdd) setTimeout(() => addInputRef.current?.focus(), 50);
  }, [showAdd]);

  function update(patch) {
    setCfg(c => ({ ...c, ...patch }));
    setDirty(true);
  }

  function handleUrlPaste(e) {
    const pasted = e.clipboardData?.getData('text') || e.target.value;
    const cleaned = cleanVintedUrl(pasted);
    setAddUrl(cleaned);
    if (cleaned !== pasted) toast('Cleaned expired params from URL', 'success');
  }

  function addUrlEntry() {
    const url = addUrl.trim();
    if (!url || !url.startsWith('http')) { toast('Enter a valid URL', 'error'); return; }
    update({ urls: [...(cfg.urls || []), { url: cleanVintedUrl(url), label: addLabel.trim() }] });
    setAddUrl(''); setAddLabel(''); setShowAdd(false);
  }

  function removeUrl(idx) {
    update({ urls: cfg.urls.filter((_, i) => i !== idx) });
  }

  async function handleSave() {
    setSaving(true);
    try {
      await saveConfig(cfg);
      toast('Saved!', 'success');
      setDirty(false);
    } catch {
      toast('Save failed', 'error');
    }
    setSaving(false);
  }

  if (loading) return (
    <div style={{ flex: 1, display: 'flex', alignItems: 'center', justifyContent: 'center' }}>
      <div className="skeleton" style={{ width: 200, height: 24, borderRadius: 8 }} />
    </div>
  );

  return (
    <div style={{ flex: 1, display: 'flex', flexDirection: 'column', overflow: 'hidden' }}>
      {/* Header */}
      <div style={{ padding: '16px 20px 12px', flexShrink: 0, display: 'flex', alignItems: 'center', gap: 12 }}>
        <button onClick={() => navigate(-1)} style={styles.backBtn}>
          <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5" strokeLinecap="round" strokeLinejoin="round">
            <path d="M19 12H5M12 5l-7 7 7 7"/>
          </svg>
        </button>
        <span style={{ fontFamily: 'Syne', fontWeight: 800, fontSize: 22, color: 'var(--text)', letterSpacing: '-0.5px', flex: 1 }}>
          Scraper settings
        </span>
        <motion.button
          onClick={handleSave}
          disabled={!dirty || saving}
          whileTap={{ scale: 0.95 }}
          style={{
            ...styles.saveBtn,
            opacity: dirty ? 1 : 0.35,
            background: dirty ? 'var(--accent)' : 'var(--surface)',
          }}
        >
          {saving ? 'Saving…' : 'Save'}
        </motion.button>
      </div>

      <div style={{ flex: 1, overflowY: 'auto', padding: '0 16px 32px' }}>

        {/* ── Scraper settings ─────────────────────────────────────────── */}
        <Section label="Scraper">

          <Row label="Filter Polish sellers"
               desc="Skip items where seller is located in Poland">
            <Toggle value={cfg.filter_polish} onChange={v => update({ filter_polish: v })} />
          </Row>

          <Row label="Max pages per URL"
               desc="Catalog pages fetched per search URL (more = slower)">
            <Stepper value={cfg.max_pages} min={1} max={100} onChange={v => update({ max_pages: v })} />
          </Row>

          <Row label="Concurrent workers"
               desc="Parallel item-page fetches (lower = safer, less likely to get blocked)">
            <Stepper value={cfg.concurrent_items} min={1} max={6} onChange={v => update({ concurrent_items: v })} />
          </Row>

          <Row label="Rate-limit pause (s)"
               desc="Seconds to wait when Vinted blocks you">
            <Stepper value={cfg.rate_limit_pause} min={10} max={300} step={5} onChange={v => update({ rate_limit_pause: v })} />
          </Row>

          <Row label="Image mode"
               desc={cfg.image_mode === 'catalog' ? 'Thumbnail from search page — fast' : 'Full image from item page — slower but higher quality'}>
            <SegmentedPick
              value={cfg.image_mode}
              options={[{ value: 'catalog', label: 'Catalog' }, { value: 'item', label: 'Item page' }]}
              onChange={v => update({ image_mode: v })}
            />
          </Row>
        </Section>

        {/* ── Model settings ───────────────────────────────────────────── */}
        <Section label="Model">
          <Row label={`FashionCLIP weight  α = ${cfg.alpha.toFixed(2)}`}
               desc={`FashionCLIP ${Math.round(cfg.alpha * 100)}%  ·  DINOv2 ${Math.round((1 - cfg.alpha) * 100)}%`}>
            <input
              type="range" min="0" max="1" step="0.05"
              value={cfg.alpha}
              onChange={e => update({ alpha: parseFloat(e.target.value) })}
              style={styles.slider}
            />
          </Row>
        </Section>

        {/* ── Search URLs ──────────────────────────────────────────────── */}
        <Section label={`Search URLs  (${(cfg.urls || []).length})`}>

          <div style={{ fontSize: 12, color: 'var(--text-2)', lineHeight: 1.6, marginBottom: 14, padding: '10px 12px', background: 'var(--surface)', borderRadius: 10 }}>
            <strong style={{ color: 'var(--text)' }}>How to get a URL</strong><br />
            1. Open vinted.cz, set your filters (size, category, price…)<br />
            2. Copy the URL from the address bar<br />
            3. Paste it below — expired params are stripped automatically<br />
            <span style={{ color: 'var(--text-3)', fontSize: 11 }}>CZ: Otevři vinted.cz, nastav filtry, zkopíruj URL z adresního řádku, vlož níže.</span>
          </div>

          <AnimatePresence initial={false}>
            {(cfg.urls || []).map((entry, idx) => (
              <motion.div
                key={idx}
                initial={{ opacity: 0, height: 0 }}
                animate={{ opacity: 1, height: 'auto' }}
                exit={{ opacity: 0, height: 0 }}
                style={{ overflow: 'hidden' }}
              >
                <UrlCard
                  entry={entry}
                  onRemove={() => removeUrl(idx)}
                />
              </motion.div>
            ))}
          </AnimatePresence>

          {/* Add URL form */}
          <AnimatePresence>
            {showAdd && (
              <motion.div
                initial={{ opacity: 0, height: 0 }}
                animate={{ opacity: 1, height: 'auto' }}
                exit={{ opacity: 0, height: 0 }}
                style={{ overflow: 'hidden' }}
              >
                <div style={styles.addForm}>
                  <input
                    ref={addInputRef}
                    placeholder="Paste vinted.cz URL…"
                    value={addUrl}
                    onChange={e => setAddUrl(e.target.value)}
                    onPaste={handleUrlPaste}
                    style={styles.textInput}
                  />
                  <input
                    placeholder="Label (optional, e.g. XL jackets)"
                    value={addLabel}
                    onChange={e => setAddLabel(e.target.value)}
                    onKeyDown={e => e.key === 'Enter' && addUrlEntry()}
                    style={{ ...styles.textInput, marginTop: 8 }}
                  />
                  <div style={{ display: 'flex', gap: 8, marginTop: 10 }}>
                    <button onClick={addUrlEntry} style={styles.addConfirmBtn}>Add</button>
                    <button onClick={() => { setShowAdd(false); setAddUrl(''); setAddLabel(''); }} style={styles.cancelBtn}>Cancel</button>
                  </div>
                </div>
              </motion.div>
            )}
          </AnimatePresence>

          {!showAdd && (
            <button onClick={() => setShowAdd(true)} style={styles.addUrlBtn}>
              + Add URL
            </button>
          )}
        </Section>

      </div>

      {/* Sticky save bar when dirty */}
      <AnimatePresence>
        {dirty && (
          <motion.div
            initial={{ y: 80 }}
            animate={{ y: 0 }}
            exit={{ y: 80 }}
            style={styles.stickyBar}
          >
            <span style={{ fontSize: 13, color: 'var(--text-2)' }}>Unsaved changes</span>
            <button onClick={handleSave} disabled={saving} style={styles.saveBtnLarge}>
              {saving ? 'Saving…' : 'Save changes'}
            </button>
          </motion.div>
        )}
      </AnimatePresence>
    </div>
  );
}

// ── sub-components ────────────────────────────────────────────────────────────

function Section({ label, children }) {
  return (
    <div style={{ marginBottom: 28 }}>
      <div style={{ fontSize: 11, fontWeight: 700, letterSpacing: '0.1em', color: 'var(--text-3)', textTransform: 'uppercase', marginBottom: 10 }}>
        {label}
      </div>
      <div style={{ background: 'var(--bg-card)', border: '1px solid var(--border)', borderRadius: 16, overflow: 'hidden' }}>
        {children}
      </div>
    </div>
  );
}

function Row({ label, desc, children }) {
  return (
    <div style={{ display: 'flex', alignItems: 'center', gap: 12, padding: '14px 16px', borderBottom: '1px solid var(--border)' }}>
      <div style={{ flex: 1, minWidth: 0 }}>
        <div style={{ fontSize: 14, fontWeight: 500, color: 'var(--text)' }}>{label}</div>
        {desc && <div style={{ fontSize: 11, color: 'var(--text-3)', marginTop: 2, lineHeight: 1.4 }}>{desc}</div>}
      </div>
      <div style={{ flexShrink: 0 }}>{children}</div>
    </div>
  );
}

function Toggle({ value, onChange }) {
  return (
    <motion.button
      onClick={() => onChange(!value)}
      style={{
        width: 44, height: 26, borderRadius: 13,
        background: value ? 'var(--accent)' : 'var(--surface-2)',
        border: '1px solid var(--border)',
        position: 'relative', cursor: 'pointer',
        transition: 'background 0.2s',
        flexShrink: 0,
      }}
    >
      <motion.div
        animate={{ x: value ? 20 : 2 }}
        transition={{ type: 'spring', stiffness: 500, damping: 35 }}
        style={{ position: 'absolute', top: 3, width: 18, height: 18, borderRadius: '50%', background: '#fff', boxShadow: '0 1px 4px rgba(0,0,0,0.3)' }}
      />
    </motion.button>
  );
}

function Stepper({ value, min, max, step = 1, onChange }) {
  return (
    <div style={{ display: 'flex', alignItems: 'center', gap: 0, background: 'var(--surface)', borderRadius: 10, border: '1px solid var(--border)' }}>
      <button onClick={() => onChange(Math.max(min, value - step))} style={styles.stepBtn}>−</button>
      <span style={{ fontSize: 14, fontWeight: 600, minWidth: 32, textAlign: 'center', color: 'var(--text)' }}>{value}</span>
      <button onClick={() => onChange(Math.min(max, value + step))} style={styles.stepBtn}>+</button>
    </div>
  );
}

function SegmentedPick({ value, options, onChange }) {
  return (
    <div style={{ display: 'flex', background: 'var(--surface)', borderRadius: 10, border: '1px solid var(--border)', overflow: 'hidden' }}>
      {options.map(opt => (
        <button
          key={opt.value}
          onClick={() => onChange(opt.value)}
          style={{
            padding: '6px 12px', fontSize: 12, fontWeight: 600,
            background: value === opt.value ? 'var(--accent)' : 'transparent',
            color: value === opt.value ? '#fff' : 'var(--text-2)',
            border: 'none', cursor: 'pointer',
            transition: 'all 0.15s',
          }}
        >
          {opt.label}
        </button>
      ))}
    </div>
  );
}

function UrlCard({ entry, onRemove }) {
  const displayUrl = entry.url.replace(/^https?:\/\/(www\.)?/, '').slice(0, 55) + (entry.url.length > 70 ? '…' : '');
  return (
    <div style={{ padding: '12px 16px', borderBottom: '1px solid var(--border)', display: 'flex', alignItems: 'flex-start', gap: 10 }}>
      <div style={{ flex: 1, minWidth: 0 }}>
        {entry.label && (
          <div style={{ fontSize: 13, fontWeight: 600, color: 'var(--text)', marginBottom: 2 }}>{entry.label}</div>
        )}
        <div style={{ fontSize: 11, color: 'var(--text-3)', wordBreak: 'break-all', lineHeight: 1.4 }}>{displayUrl}</div>
      </div>
      <div style={{ display: 'flex', gap: 6, flexShrink: 0 }}>
        <button
          onClick={() => window.open(entry.url, '_blank', 'noopener')}
          title="Open in browser"
          style={styles.iconBtn}
        >
          <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
            <path d="M18 13v6a2 2 0 01-2 2H5a2 2 0 01-2-2V8a2 2 0 012-2h6"/><polyline points="15 3 21 3 21 9"/><line x1="10" y1="14" x2="21" y2="3"/>
          </svg>
        </button>
        <button onClick={onRemove} title="Remove" style={{ ...styles.iconBtn, color: 'var(--dislike)' }}>
          <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
            <polyline points="3 6 5 6 21 6"/><path d="M19 6l-1 14a2 2 0 01-2 2H8a2 2 0 01-2-2L5 6"/><path d="M10 11v6M14 11v6"/><path d="M9 6V4a1 1 0 011-1h4a1 1 0 011 1v2"/>
          </svg>
        </button>
      </div>
    </div>
  );
}

// ── styles ────────────────────────────────────────────────────────────────────
const styles = {
  backBtn: {
    background: 'var(--surface)', border: '1px solid var(--border)',
    borderRadius: 10, width: 36, height: 36,
    display: 'flex', alignItems: 'center', justifyContent: 'center',
    cursor: 'pointer', color: 'var(--text)', flexShrink: 0,
  },
  saveBtn: {
    color: '#fff', border: 'none', borderRadius: 10,
    padding: '8px 16px', fontSize: 13, fontWeight: 600,
    cursor: 'pointer', fontFamily: 'inherit', transition: 'all 0.2s',
  },
  saveBtnLarge: {
    background: 'var(--accent)', color: '#fff', border: 'none',
    borderRadius: 12, padding: '12px 24px', fontSize: 14, fontWeight: 600,
    cursor: 'pointer', fontFamily: 'inherit',
  },
  stepBtn: {
    background: 'none', border: 'none', cursor: 'pointer',
    color: 'var(--text-2)', fontSize: 18, fontWeight: 400,
    padding: '4px 10px', lineHeight: 1,
  },
  iconBtn: {
    background: 'var(--surface)', border: '1px solid var(--border)',
    borderRadius: 8, width: 30, height: 30,
    display: 'flex', alignItems: 'center', justifyContent: 'center',
    cursor: 'pointer', color: 'var(--text-2)',
  },
  textInput: {
    width: '100%', boxSizing: 'border-box',
    background: 'var(--surface)', border: '1px solid var(--border)',
    borderRadius: 10, padding: '11px 14px', fontSize: 13,
    color: 'var(--text)', fontFamily: 'inherit', outline: 'none',
  },
  addForm: {
    padding: '12px 16px', borderBottom: '1px solid var(--border)',
    background: 'var(--bg-card-2)',
  },
  addUrlBtn: {
    width: '100%', background: 'none', border: 'none',
    color: 'var(--accent)', fontSize: 14, fontWeight: 600,
    padding: '14px', cursor: 'pointer', fontFamily: 'inherit',
    textAlign: 'center',
  },
  addConfirmBtn: {
    background: 'var(--accent)', color: '#fff', border: 'none',
    borderRadius: 8, padding: '8px 20px', fontSize: 13, fontWeight: 600,
    cursor: 'pointer', fontFamily: 'inherit',
  },
  cancelBtn: {
    background: 'var(--surface)', color: 'var(--text-2)',
    border: '1px solid var(--border)',
    borderRadius: 8, padding: '8px 16px', fontSize: 13, fontWeight: 500,
    cursor: 'pointer', fontFamily: 'inherit',
  },
  slider: {
    width: 120, accentColor: 'var(--accent)', cursor: 'pointer',
  },
  stickyBar: {
    position: 'absolute', bottom: 'calc(var(--nav-h) + env(safe-area-inset-bottom, 0px))',
    left: 16, right: 16,
    background: 'var(--bg-card)', border: '1px solid var(--border)',
    borderRadius: 14, padding: '12px 16px',
    display: 'flex', alignItems: 'center', justifyContent: 'space-between',
    boxShadow: '0 8px 32px rgba(0,0,0,0.4)',
    zIndex: 10,
  },
};
