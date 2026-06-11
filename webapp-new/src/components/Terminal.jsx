import { useState, useEffect, useRef } from 'react';

/*
 * Terminal — the embedded "machine" window.
 *
 * Two modes:
 *  • Ambient (default): endlessly streams cool-looking fake pipeline output.
 *    Purely decorative — lives in the desktop right rail.
 *  • Controlled: pass `lines` (string[]) + `status` to mirror a real job log.
 */

const rnd = (a, b) => Math.floor(a + Math.random() * (b - a));
const bar = (pct) => {
  const w = 22;
  const f = Math.round((pct / 100) * w);
  return '[' + '█'.repeat(f) + '░'.repeat(w - f) + ']';
};

// Build a fresh run of the ambient pipeline with randomised numbers,
// so each loop reads slightly differently and feels live.
function buildScript() {
  const pages = rnd(6, 19);
  const items = pages * rnd(18, 26);
  const newImgs = rnd(40, 180);
  const s = [];

  s.push(['$ python vinted_scraper.py --watch', 'cmd', 420]);
  s.push([`→ session ok · cookies valid · locale cz`, 'dim', 260]);
  s.push([`→ crawling ${pages} pages …`, 'white', 220]);
  for (let p = 1; p <= Math.min(pages, 5); p++) {
    s.push([`  page ${p}/${pages}  ·  +${rnd(18, 26)} items  ·  ${rnd(180, 920)}ms`, 'dim', rnd(120, 240)]);
  }
  s.push([`✓ scraped ${items} listings`, 'ok', 320]);

  s.push(['', 'dim', 80]);
  s.push(['$ python compute_embeddings.py', 'cmd', 360]);
  s.push([`→ ${newImgs} new images · downloading`, 'white', 200]);
  for (let pct = 0; pct <= 100; pct += rnd(18, 30)) {
    const p = Math.min(pct, 100);
    s.push([`  fashionCLIP  ${bar(p)} ${String(p).padStart(3)}%`, p >= 100 ? 'ok' : 'cyan', 130, true]);
  }
  for (let pct = 0; pct <= 100; pct += rnd(20, 34)) {
    const p = Math.min(pct, 100);
    s.push([`  DINOv2       ${bar(p)} ${String(p).padStart(3)}%`, p >= 100 ? 'ok' : 'cyan', 130, true]);
  }
  s.push([`✓ embeddings.npz  ·  ${items}×2570 dims`, 'ok', 320]);

  s.push(['', 'dim', 80]);
  s.push(['$ python train_mlp.py', 'cmd', 360]);
  s.push([`→ StyleMLP · ${rnd(190, 260)} rated · text-weight 0.5`, 'white', 220]);
  let loss = 0.71;
  for (let e = 1; e <= 6; e++) {
    loss = Math.max(0.04, loss - Math.random() * 0.13);
    const acc = (0.6 + e * 0.055 + Math.random() * 0.02).toFixed(3);
    s.push([`  epoch ${String(e).padStart(2)}/6   loss ${loss.toFixed(4)}   acc ${acc}`, 'dim', rnd(160, 280)]);
  }
  s.push(['✓ style_mlp.pt saved', 'ok', 320]);

  s.push(['', 'dim', 80]);
  s.push(['$ python score_with_mlp.py', 'cmd', 340]);
  for (let pct = 0; pct <= 100; pct += rnd(22, 36)) {
    const p = Math.min(pct, 100);
    s.push([`  scoring      ${bar(p)} ${String(p).padStart(3)}%`, p >= 100 ? 'ok' : 'cyan', 120, true]);
  }
  s.push([`✓ ${rnd(20, 60)} items above threshold · top ${rnd(88, 97)}%`, 'ok', 360]);
  s.push([`→ idle · watching for new drops …`, 'dim', 1400]);
  return s;
}

const CLS = {
  cmd: 'term-c-white', ok: '', dim: 'term-c-dim',
  white: 'term-c-white', cyan: 'term-c-cyan', amber: 'term-c-amber', red: 'term-c-red',
};
const PREFIX = { ok: '', cmd: '' };

export default function Terminal({
  title = 'vinted-ai — pipeline',
  lines: controlledLines,
  status,
  maxLines = 16,
  style,
}) {
  const controlled = Array.isArray(controlledLines);
  const [lines, setLines] = useState([]);
  const bodyRef = useRef(null);
  const timer = useRef(null);

  // Ambient streaming loop
  useEffect(() => {
    if (controlled) return;
    let script = buildScript();
    let i = 0;

    const step = () => {
      const entry = script[i];
      if (!entry) { script = buildScript(); i = 0; timer.current = setTimeout(step, 500); return; }
      const [text, kind, delay, replace] = entry;
      setLines(prev => {
        const next = replace && prev.length ? prev.slice(0, -1) : prev.slice();
        next.push({ text, cls: CLS[kind] ?? '', key: Math.random() });
        return next.slice(-maxLines);
      });
      i++;
      timer.current = setTimeout(step, delay);
    };
    timer.current = setTimeout(step, 300);
    return () => clearTimeout(timer.current);
  }, [controlled, maxLines]);

  // Controlled mode mirrors the passed lines
  useEffect(() => {
    if (!controlled) return;
    setLines(controlledLines.slice(-maxLines).map((t, k) => ({ text: t, cls: classify(t), key: k })));
  }, [controlled, controlledLines, maxLines]);

  // Auto-scroll to bottom
  useEffect(() => {
    if (bodyRef.current) bodyRef.current.scrollTop = bodyRef.current.scrollHeight;
  }, [lines]);

  const dotG = status === 'running' ? 'g pulse' : 'g';

  return (
    <div className="term" style={style}>
      <div className="term-bar">
        <span className="term-dot r" />
        <span className="term-dot y" />
        <span className={`term-dot ${dotG}`} />
        <span className="term-title">{title}</span>
      </div>
      <div className="term-body" ref={bodyRef}>
        {lines.map(l => (
          <div className={`term-line ${l.cls}`} key={l.key}>{l.text || ' '}</div>
        ))}
        <span className="term-line"><span className="term-cursor" /></span>
      </div>
    </div>
  );
}

// Heuristic colouring for controlled (real) log lines.
function classify(t = '') {
  const s = t.trim();
  if (/^\$/.test(s)) return 'term-c-white';
  if (/✓|done|saved|success|finished/i.test(s)) return '';
  if (/✗|error|fail|traceback/i.test(s)) return 'term-c-red';
  if (/warn|skip|retry/i.test(s)) return 'term-c-amber';
  if (/^(→|»|\[)/.test(s)) return 'term-c-cyan';
  return 'term-c-dim';
}
