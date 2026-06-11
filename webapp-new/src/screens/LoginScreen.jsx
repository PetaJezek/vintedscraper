import { useState } from 'react';
import { login } from '../api/client';
import Terminal from '../components/Terminal';

export default function LoginScreen({ onLogin }) {
  const [password, setPassword] = useState('');
  const [show, setShow] = useState(false);
  const [error, setError] = useState('');
  const [loading, setLoading] = useState(false);
  const [shake, setShake] = useState(false);
  const [showWarn, setShowWarn] = useState(false);

  async function handleSubmit(e) {
    e.preventDefault();
    if (!password) return;
    setLoading(true);
    setError('');
    try {
      const token = await login(password);
      onLogin(token);
    } catch (err) {
      setError(err.message === 'Wrong password' ? 'Wrong password' : 'Could not reach server');
      setShake(true);
      setTimeout(() => setShake(false), 500);
    } finally {
      setLoading(false);
    }
  }

  return (
    <div style={styles.root}>
      <div style={styles.col}>
        <div style={{ textAlign: 'center' }}>
          <div className="eyebrow" style={{ marginBottom: 12 }}>· vinted intelligence ·</div>
          <div className="display" style={styles.logo}>
            Vinted<span style={styles.logoAccent}> AI</span>
          </div>
          <div style={styles.tagline}>A fashion engine trained on your taste.</div>
        </div>

        <Terminal
          title="vinted-ai — boot"
          status="done"
          maxLines={5}
          lines={[
            '$ vinted-ai --boot',
            '→ loading style_mlp.pt ......... ok',
            '→ embeddings  217 × 2570 ....... ok',
            '✓ ready · authenticate to continue',
          ]}
        />

        <form onSubmit={handleSubmit} style={styles.form}>
          <div style={{ ...styles.inputWrap, ...(shake ? styles.shake : {}) }}>
            <input
              type={show ? 'text' : 'password'}
              placeholder="Password"
              value={password}
              onChange={e => setPassword(e.target.value)}
              style={styles.input}
              autoFocus
              autoComplete="current-password"
            />
            <button type="button" onClick={() => setShow(s => !s)} style={styles.eyeBtn} tabIndex={-1}>
              {show ? '🙈' : '👁️'}
            </button>
          </div>

          {error && <div style={styles.error}>{error}</div>}

          <button
            type="submit"
            disabled={loading || !password}
            style={{ ...styles.btn, ...(loading || !password ? styles.btnDisabled : {}) }}
          >
            {loading ? 'Unlocking…' : 'Unlock'}
          </button>
        </form>

        <button onClick={() => setShowWarn(v => !v)} style={styles.warnToggle}>
          {showWarn ? '▾' : '▸'} No password recovery — read this
        </button>
        {showWarn && (
          <div style={styles.warnBody} className="fade-up">
            There is no reset link, no email, nothing. If you forget your password you must delete{' '}
            <code style={styles.code}>webapp/password.hash</code> on the PC and restart the server to set a new one.
          </div>
        )}
      </div>
    </div>
  );
}

const styles = {
  root: {
    position: 'fixed', inset: 0, zIndex: 1,
    display: 'flex', alignItems: 'center', justifyContent: 'center',
    padding: 24,
  },
  col: {
    width: '100%', maxWidth: 400,
    display: 'flex', flexDirection: 'column', gap: 22,
  },
  logo: {
    fontSize: 52, fontWeight: 600, color: 'var(--text)', lineHeight: 1,
  },
  logoAccent: { fontStyle: 'italic', color: 'var(--accent)' },
  tagline: { marginTop: 12, fontSize: 14, color: 'var(--text-2)' },
  form: { display: 'flex', flexDirection: 'column', gap: 12 },
  inputWrap: { position: 'relative' },
  input: {
    width: '100%',
    background: 'color-mix(in srgb, var(--bg-card) 72%, transparent)',
    backdropFilter: 'blur(12px)',
    border: '1px solid var(--border)',
    borderRadius: 14,
    padding: '15px 46px 15px 18px',
    fontSize: 15, color: 'var(--text)', outline: 'none',
    boxSizing: 'border-box', transition: 'border-color 0.15s',
  },
  eyeBtn: {
    position: 'absolute', right: 12, top: '50%', transform: 'translateY(-50%)',
    fontSize: 16, padding: 4, lineHeight: 1,
  },
  error: { fontSize: 13, color: 'var(--dislike)', textAlign: 'center' },
  btn: {
    background: 'var(--accent)', color: '#1a1206',
    border: 'none', borderRadius: 14, padding: '15px',
    fontSize: 15, fontWeight: 700, letterSpacing: '0.01em',
    boxShadow: '0 10px 30px rgba(230,189,118,0.22)',
    transition: 'opacity 0.15s, transform 0.1s',
  },
  btnDisabled: { opacity: 0.4, cursor: 'default', boxShadow: 'none' },
  shake: { animation: 'shake 0.45s ease' },
  warnToggle: {
    fontFamily: 'var(--font-mono)', fontSize: 11, color: 'var(--text-3)',
    letterSpacing: '0.04em', textAlign: 'center', padding: 4,
  },
  warnBody: {
    fontSize: 12, color: 'var(--text-2)', lineHeight: 1.6, textAlign: 'center',
    background: 'var(--superlike-bg)', border: '1px solid rgba(230,189,118,0.25)',
    borderRadius: 12, padding: '12px 14px',
  },
  code: {
    background: 'var(--surface)', borderRadius: 4, padding: '1px 5px',
    fontSize: 11, fontFamily: 'var(--font-mono)', color: 'var(--text)',
  },
};
