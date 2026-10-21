import { useEffect, useState } from 'react';
import { useTranslation } from 'react-i18next';
import { ApiRequestError, request, type Location } from '../services/api';

interface Monitor { id: string; name: string; location: Location; enabled: boolean; last_checked?: string; last_error?: string }
export default function MonitoringSettings({ location, active, onSelect }: { location: Location; active: boolean; onSelect: (location: Location) => void }) {
  const { t, i18n } = useTranslation();
  const [monitors, setMonitors] = useState<Monitor[]>([]);
  const [name, setName] = useState('');
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState('');
  async function load(signal?: AbortSignal) {
    const result = await request<Monitor[]>('/api/monitors', { signal, cache: 'no-store' });
    if (!signal?.aborted) { setMonitors(result); setError(''); }
  }
  useEffect(() => {
    const abort = new AbortController();
    const check = () => void load(abort.signal).catch(() => { if (!abort.signal.aborted) setError('loadError'); });
    check(); const timer = setInterval(check, 60000);
    return () => { abort.abort(); clearInterval(timer); };
  }, []);
  async function save(record?: Monitor, remove = false) {
    const previous = monitors;
    setBusy(true);
    if (record && !remove) setMonitors(items => items.map(item => item.id === record.id ? { ...item, enabled: !record.enabled } : item));
    try {
      await request(`/api/monitors${remove ? `/${record!.id}` : ''}`, {
        method: remove ? 'DELETE' : 'POST', headers: { 'Content-Type': 'application/json' },
        body: remove ? undefined : JSON.stringify(record ? { name: record.name, location: record.location, enabled: !record.enabled } : { name: name.trim() || `${location.lat.toFixed(3)}, ${location.lon.toFixed(3)}`, location, enabled: true }),
      });
      await load(); if (!record) setName('');
    } catch (cause) {
      setMonitors(previous);
      setError(cause instanceof ApiRequestError ? cause.status === 403 ? 'originError' : cause.status === 409 ? 'limitError' : cause.status === 422 ? 'locationError' : 'saveError' : 'connectionError');
    }
    finally { setBusy(false); }
  }
  return <section className="monitor-panel" aria-label={t('monitor.title')}>
    <strong>{t('monitor.title')}</strong><p>{t('monitor.description')}</p>
    <div className="monitor-actions"><input aria-label={t('monitor.name')} placeholder={t('monitor.name')} value={name} maxLength={80} onChange={event => setName(event.target.value)} />
      <button disabled={busy || !active} onClick={() => void save()}>{t('monitor.save')}</button></div>
    {error && <p role="alert">{t(`monitor.${error}`)}</p>}
    {monitors.map(record => <div className="monitor-row" key={record.id}>
      <button disabled={!active} onClick={() => onSelect(record.location)}>{record.name}</button>
      <label><input type="checkbox" checked={record.enabled} disabled={busy} onChange={() => void save(record)} />{t('monitor.enabled')}</label>
      <small>{record.last_checked ? `${t('monitor.checked')}: ${new Date(record.last_checked).toLocaleString(i18n.language)}` : t('monitor.pending')}{record.last_error ? ` · ${t('monitor.checkError')}` : ''}</small>
      <button disabled={busy} onClick={() => void save(record, true)} aria-label={`${t('monitor.remove')} ${record.name}`}>{t('monitor.remove')}</button>
    </div>)}
  </section>;
}
