import { useEffect, useRef, useState } from 'react';
import { useTranslation } from 'react-i18next';
import type { Location } from '../services/api';
import { disablePush, enablePush, PushRequestError, pushStatus, pushSupported, readPushId, testPush, updatePush } from '../services/notifications';
import type { PushStatus } from '../services/notifications';

export default function NotificationSettings({ location, language, levels, active }: { location: Location; language?: string; levels: string[]; active: boolean }) {
  const { t, i18n } = useTranslation();
  const [id, setId] = useState(readPushId);
  const [status, setStatus] = useState<PushStatus | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState('');
  const [message, setMessage] = useState('');
  const mounted = useRef(true);
  const supported = pushSupported();
  const watch = { location, language: (language ?? i18n.language).startsWith('es') ? 'es' : 'en', levels };
  const watchKey = JSON.stringify(watch);
  useEffect(() => { mounted.current = true; return () => { mounted.current = false; }; }, []);
  useEffect(() => {
    if (!id) return;
    const abort = new AbortController();
    const check = () => pushStatus(id, abort.signal).then(value => { if (!abort.signal.aborted) { setStatus(value); setError(''); } }).catch(cause => { if (!abort.signal.aborted) { const missing = cause instanceof PushRequestError && cause.status === 404; setStatus(missing ? { enabled: false, last_checked: null, last_sent: null, last_error: null } : null); setError(missing ? '' : 'statusError'); } });
    void check(); const timer = window.setInterval(check, 60000);
    return () => { abort.abort(); clearInterval(timer); };
  }, [id]);
  useEffect(() => {
    if (!id || !status?.enabled || !active) return;
    const abort = new AbortController();
    const timer = window.setTimeout(() => { void updatePush(id, JSON.parse(watchKey), abort.signal).then(() => { if (!abort.signal.aborted) setError(''); }).catch(() => { if (!abort.signal.aborted) setError('updateError'); }); }, 600);
    return () => { clearTimeout(timer); abort.abort(); };
  }, [id, status?.enabled, active, watchKey]);
  async function action(kind: 'enable' | 'disable' | 'test') {
    if (busy) return;
    setBusy(true); setError(''); setMessage('');
    try {
      if (kind === 'enable') { const next = await enablePush(watch); if (mounted.current) { setId(next); setStatus({ enabled: true, last_checked: null, last_sent: null, last_error: null }); } }
      if (kind === 'disable' && id) { await disablePush(id); if (mounted.current) { setId(null); setStatus(null); } }
      if (kind === 'test' && id) { await testPush(id); if (mounted.current) setMessage('testSent'); }
    } catch (cause) {
      const code = cause instanceof Error ? cause.message : '';
      if (mounted.current) setError(['unsupported', 'denied', 'dismissed', 'unavailable', 'storage'].includes(code) ? code : kind === 'disable' ? 'disableError' : kind === 'test' ? 'testError' : 'subscriptionError');
    } finally { if (mounted.current) setBusy(false); }
  }
  return <section aria-label={t('push.title')} data-testid="notification-settings" style={{ flexBasis: '100%', minWidth: 0 }}>
    <h3>{t('push.title')}</h3>
    <p>{t('push.description')}</p>
    <small>{t('push.privacy')}</small>
    <p role="status">{t(`push.${id ? status?.enabled ? 'enabled' : status ? 'inactive' : 'checking' : 'disabled'}`)}</p>
    {!supported && <p>{t('push.unsupported')}</p>}
    {supported && Notification.permission === 'denied' && <p>{t('push.denied')}</p>}
    {!active && <p>{t('push.replay')}</p>}
    {id && status?.last_checked && <small>{t('push.lastChecked')}: {new Date(status.last_checked).toLocaleString(i18n.language)}</small>}
    {id && status?.last_error && <p role="alert">{t('push.deliveryError')}</p>}
    {error && <p role="alert">{t(`push.${error}`)}</p>}
    {message && <p role="status">{t(`push.${message}`)}</p>}
    <div style={{ display: 'flex', flexWrap: 'wrap', gap: 8, marginTop: 12 }}>
      {(!id || status?.enabled === false) && <button type="button" disabled={busy || !supported || !active} onClick={() => void action('enable')}>{t('push.enable')}</button>}
      {id && <button type="button" disabled={busy} onClick={() => void action('disable')}>{t('push.disable')}</button>}
      {id && status?.enabled && <button type="button" disabled={busy} onClick={() => void action('test')}>{t('push.test')}</button>}
    </div>
  </section>;
}
