import { useState } from 'react';
import { login } from '../api/client';

export default function LoginScreen({ onLogin }) {
  const [password, setPassword] = useState('');
  const [show, setShow] = useState(false);
  const [error, setError] = useState('');
  const [loading, setLoading] = useState(false);
  const [shake, setShake] = useState(false);

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
      <div style={styles.card}>
        <div style={styles.logo}>
          <span style={styles.logoText}>Vinted</span>
          <span style={styles.logoAccent}> AI</span>
        </div>

        <div style={styles.warning}>
          <span style={styles.warningIcon}>⚠️</span>
          <div>
            <div style={styles.warningTitle}>No password recovery</div>
            <div style={styles.warningBody}>
              There is no reset link, no email, nothing. If you forget your password,
              you must delete <code style={styles.code}>webapp/password.hash</code> on
              the PC and restart the server to set a new one.
            </div>
          </div>
        </div>

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
            <button
              type="button"
              onClick={() => setShow(s => !s)}
              style={styles.eyeBtn}
              tabIndex={-1}
            >
              {show ? '🙈' : '👁️'}
            </button>
          </div>

          {error && <div style={styles.error}>{error}</div>}

          <button
            type="submit"
            disabled={loading || !password}
            style={{ ...styles.btn, ...(loading || !password ? styles.btnDisabled : {}) }}
          >
            {loading ? 'Checking…' : 'Unlock'}
          </button>
        </form>
      </div>
    </div>
  );
}

const styles = {
  root: {
    position: 'fixed',
    inset: 0,
    display: 'flex',
    alignItems: 'center',
    justifyContent: 'center',
    background: 'var(--bg)',
    padding: '24px',
  },
  card: {
    width: '100%',
    maxWidth: '380px',
    background: 'var(--bg-card)',
    border: '1px solid var(--border)',
    borderRadius: '20px',
    padding: '32px 28px',
    display: 'flex',
    flexDirection: 'column',
    gap: '24px',
  },
  logo: {
    textAlign: 'center',
    fontSize: '28px',
    fontWeight: 800,
    fontFamily: "'Syne', sans-serif",
    letterSpacing: '-0.5px',
  },
  logoText: { color: 'var(--text)' },
  logoAccent: { color: 'var(--accent)' },
  warning: {
    display: 'flex',
    gap: '12px',
    background: 'rgba(245,158,11,0.08)',
    border: '1px solid rgba(245,158,11,0.3)',
    borderRadius: '12px',
    padding: '14px',
  },
  warningIcon: { fontSize: '18px', flexShrink: 0, lineHeight: 1.4 },
  warningTitle: {
    fontWeight: 600,
    fontSize: '13px',
    color: '#f59e0b',
    marginBottom: '4px',
  },
  warningBody: {
    fontSize: '12px',
    color: 'var(--text-2)',
    lineHeight: 1.5,
  },
  code: {
    background: 'var(--surface)',
    borderRadius: '4px',
    padding: '1px 5px',
    fontSize: '11px',
    fontFamily: 'monospace',
    color: 'var(--text)',
  },
  form: {
    display: 'flex',
    flexDirection: 'column',
    gap: '12px',
  },
  inputWrap: {
    position: 'relative',
  },
  input: {
    width: '100%',
    background: 'var(--surface)',
    border: '1px solid var(--border)',
    borderRadius: '12px',
    padding: '14px 44px 14px 16px',
    fontSize: '15px',
    color: 'var(--text)',
    outline: 'none',
    boxSizing: 'border-box',
    fontFamily: 'inherit',
    transition: 'border-color 0.15s',
  },
  eyeBtn: {
    position: 'absolute',
    right: '12px',
    top: '50%',
    transform: 'translateY(-50%)',
    background: 'none',
    border: 'none',
    cursor: 'pointer',
    fontSize: '16px',
    padding: '4px',
    lineHeight: 1,
  },
  error: {
    fontSize: '13px',
    color: 'var(--dislike)',
    textAlign: 'center',
  },
  btn: {
    background: 'var(--accent)',
    color: '#fff',
    border: 'none',
    borderRadius: '12px',
    padding: '14px',
    fontSize: '15px',
    fontWeight: 600,
    cursor: 'pointer',
    fontFamily: 'inherit',
    transition: 'opacity 0.15s',
  },
  btnDisabled: {
    opacity: 0.45,
    cursor: 'default',
  },
  shake: {
    animation: 'shake 0.45s ease',
  },
};
