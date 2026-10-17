import { useEffect, useRef, useState } from 'react';
import { useTranslation } from 'react-i18next';
import { Activity, ArrowUpRight, Bell, Crosshair, Download, Globe2, Layers, LocateFixed, Pause, Play, Radio, Settings2, ShieldCheck, Waves } from 'lucide-react';
import RadarMap from './components/RadarMap';
import AddressSearch from './components/AddressSearch';
import NotificationSettings from './components/NotificationSettings';
import { predictionsForFrame } from './components/temporal';
import { query, readStored, request, store, validLocation } from './services/api';
import type { Analysis, HistoryItem, Location, Replay, Sample } from './services/api';

const defaultLocation: Location = { lat: 32.5149, lon: -117.0382, radius_km: 50, threshold: .2 };
const levels = ['informational', 'preventive', 'imminent'];
type Run = Omit<Replay, 'steps'>;
const utcInput = (value: Date) => value.toISOString().slice(0, 16);
export default function App() {
  const { t, i18n } = useTranslation();
  const [location, setLocation] = useState<Location>(() => { const saved = readStored('tlaloc.location', defaultLocation); return validLocation(saved) ? saved : defaultLocation; });
  const [latitudeDraft, setLatitudeDraft] = useState(String(location.lat));
  const [longitudeDraft, setLongitudeDraft] = useState(String(location.lon));
  const [enabled, setEnabled] = useState<string[]>(() => { const saved = readStored<unknown>('tlaloc.levels', levels); return Array.isArray(saved) ? saved.filter(v => typeof v === 'string' && levels.includes(v)) : levels; });
  const [analysis, setAnalysis] = useState<Analysis | null>(null);
  const [history, setHistory] = useState<HistoryItem[]>([]);
  const [error, setError] = useState('');
  const [busy, setBusy] = useState(false);
  const [paused, setPaused] = useState(false);
  const [mode, setMode] = useState<'live' | 'replay'>('live');
  const [replay, setReplay] = useState<Replay | null>(null);
  const [runs, setRuns] = useState<Run[]>([]);
  const [index, setIndex] = useState(0);
  const [playing, setPlaying] = useState(false);
  const [settings, setSettings] = useState(false);
  const [start, setStart] = useState(() => utcInput(new Date(Date.now() - 3600000)));
  const [end, setEnd] = useState(() => utcInput(new Date(Date.now() - 60000)));
  const [replayBusy, setReplayBusy] = useState(false);
  const [sound, setSound] = useState(false);
  const [clock, setClock] = useState(Date.now());
  const audio = useRef<AudioContext | null>(null);
  const sounded = useRef(new Set<string>());
  const epoch = useRef(0);
  const replayAbort = useRef<AbortController | null>(null);
  const liveLocation = useRef(location);
  const [layerChoice, setSelectedLayer] = useState<'rate' | 'reflectivity'>(() => {
    const saved = readStored<unknown>('tlaloc.radarLayer', 'rate');
    return saved === 'reflectivity' ? 'reflectivity' : 'rate';
  });
  const previousLocation = useRef(query(location));
  const frames = mode === 'replay' ? replay?.steps.map(step => step.frame) ?? [] : analysis?.frames ?? [];
  const frame = frames[index];
  const hasReflectivity = frames.some(item => !!item.layers?.reflectivity);
  const selectedLayer = layerChoice;
  const layer = frame?.layers?.[selectedLayer];
  const isComposite = (frame?.layers?.reflectivity ?? frames.find(item => item.layers?.reflectivity)?.layers?.reflectivity)?.product === 'MergedReflectivityQCComposite';
  const shownFrame = layer && frame ? { ...frame, ...layer } : selectedLayer === 'rate' && frame && !frame.layers ? frame : undefined;
  const isLatest = index === frames.length - 1;
  const baseCoverage = mode === 'replay' ? replay?.steps[index]?.coverage : isLatest ? analysis?.coverage : frame?.coverage;
  const observationAge = mode === 'live' && isLatest && frame ? Math.max(0, (clock - Date.parse(frame.time)) / 60000) : baseCoverage?.age_minutes;
  const coverage = baseCoverage ? { ...baseCoverage, age_minutes: observationAge ?? null, status: mode === 'live' && isLatest && (observationAge ?? 0) > 10 ? 'stale_observations' : baseCoverage.status } : undefined;
  const predictions = (mode === 'live' && (paused || (observationAge ?? 0) > 10) ? [] : predictionsForFrame(mode, index, analysis, replay)).filter(p => enabled.includes(p.level));
  const fmt = (time: string) => new Date(time).toLocaleString(i18n.language, { month: 'short', day: 'numeric', hour: '2-digit', minute: '2-digit', timeZone: 'UTC', hour12: false }) + ' UTC';
  const value = (n: number | null | undefined, unit = '') => n == null ? t('unknown') : `${n.toFixed(1)}${unit}`;
  const fail = (e: unknown) => t(`errors.${e instanceof Error ? e.message : 'request_failed'}`, { defaultValue: t('errors.request_failed') });
  const move = (lat: number, lon: number) => { if (Number.isFinite(lat) && Number.isFinite(lon) && Math.abs(lat) <= 90 && Math.abs(lon) <= 180) setLocation(old => ({ ...old, lat, lon })); };

  useEffect(() => { if (mode === 'live') { liveLocation.current = location; store('tlaloc.location', location); } setLatitudeDraft(String(location.lat)); setLongitudeDraft(String(location.lon)); }, [location, mode]);
  function returnLive() { setLocation(liveLocation.current); setMode('live'); setPlaying(false); setIndex((analysis?.frames.length ?? 1) - 1); }
  useEffect(() => { const timer = window.setInterval(() => setClock(Date.now()), 15000); return () => clearInterval(timer); }, []);
  useEffect(() => { document.documentElement.lang = i18n.language.startsWith('es') ? 'es' : 'en'; }, [i18n.language]);
  useEffect(() => { store('tlaloc.levels', enabled); }, [enabled]);
  useEffect(() => { store('tlaloc.radarLayer', layerChoice); }, [layerChoice]);
  useEffect(() => {
    const key = query(location);
    if (previousLocation.current !== key) {
      previousLocation.current = key; epoch.current++; replayAbort.current?.abort(); setReplay(null); setAnalysis(null); setHistory([]); setIndex(0); setPlaying(false); setError(''); setReplayBusy(false);
    }
  }, [location]);
  useEffect(() => {
    if (mode !== 'live' || paused) return;
    let controller: AbortController | null = null;
    let disposed = false;
    const poll = async () => {
      controller?.abort(); controller = new AbortController(); const signal = controller.signal;
      setBusy(true);
      try {
        const result = await request<Analysis>(`/api/analysis?${query(location)}`, { signal });
        if (disposed || signal.aborted) return;
        setAnalysis(result); setIndex(result.frames.length - 1); setError('');
        const items = await request<HistoryItem[]>(`/api/history?${query(location)}`, { signal });
        if (!disposed && !signal.aborted) setHistory(items);
      } catch (e) { if (!disposed && !signal.aborted) { setError(fail(e)); setAnalysis(null); setHistory([]); setIndex(0); setPlaying(false); } }
      finally { if (!disposed && !signal.aborted) setBusy(false); }
    };
    void poll(); const interval = window.setInterval(() => void poll(), 60000);
    return () => { disposed = true; controller?.abort(); clearInterval(interval); setBusy(false); };
  }, [location, mode, paused]);
  useEffect(() => { if (!playing || frames.length < 2) return; const id = window.setInterval(() => setIndex(old => (old + 1) % frames.length), 850); return () => clearInterval(id); }, [playing, frames.length]);
  useEffect(() => {
    if (!sound || mode !== 'live' || !isLatest || !audio.current) return;
    for (const p of predictions) {
      const key = `${query(location)}:${p.id}:${p.level}`;
      if (sounded.current.has(key)) continue;
      sounded.current.add(key);
      const context = audio.current; const oscillator = context.createOscillator(); const gain = context.createGain();
      oscillator.connect(gain); gain.connect(context.destination); oscillator.frequency.value = p.level === 'imminent' ? 780 : 520;
      gain.gain.setValueAtTime(.06, context.currentTime); gain.gain.exponentialRampToValueAtTime(.001, context.currentTime + .3); oscillator.start(); oscillator.stop(context.currentTime + .3);
    }
  }, [predictions, sound, mode, isLatest]);
  useEffect(() => () => { replayAbort.current?.abort(); void audio.current?.close(); }, []);
  async function loadReplay(sample = false) {
    replayAbort.current?.abort(); const controller = new AbortController(); replayAbort.current = controller;
    const current = ++epoch.current;
    setReplayBusy(true); setError(''); setPlaying(false);
    try {
      let loc = location, begin = new Date(`${start}Z`), finish = new Date(`${end}Z`);
      if (sample) { const data = await request<Sample>('/api/sample', { signal: controller.signal }); loc = { ...data.location, threshold: location.threshold }; begin = new Date(data.frames[0].time); finish = new Date(data.frames[data.frames.length - 1].time); }
      if (!Number.isFinite(begin.getTime()) || !Number.isFinite(finish.getTime()) || finish.getTime() - begin.getTime() < 120000 || finish.getTime() - begin.getTime() > 3600000 || finish.getTime() > Date.now()) throw new Error('replay_period');
      const result = await request<Replay>('/api/replay', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ ...loc, start: begin.toISOString(), end: finish.toISOString(), sample }), signal: controller.signal });
      if (controller.signal.aborted || current !== epoch.current) return;
      // Sample coordinates become active only after a completed request; no stale live data survives.
      if (sample) { previousLocation.current = query(loc); setLocation(loc); setAnalysis(null); setHistory([]); setStart(utcInput(begin)); setEnd(utcInput(finish)); }
      setReplay(result); setIndex(0); setMode('replay');
      setRuns(await request<Run[]>('/api/runs', { signal: controller.signal }));
    } catch (e) { if (!controller.signal.aborted && current === epoch.current) setError(fail(e)); }
    finally { if (!controller.signal.aborted && current === epoch.current) setReplayBusy(false); }
  }
  function exportReplay() { if (!replay) return; const url = URL.createObjectURL(new Blob([JSON.stringify(replay, null, 2)], { type: 'application/json' })); const link = document.createElement('a'); link.href = url; link.download = `tlaloc-${replay.run_id}.json`; link.click(); URL.revokeObjectURL(url); }
  return <div className="app-shell">
    <header className="topbar"><a className="brand" href="/" aria-label="Tláloc Project"><span className="brand-icon"><Waves size={26} /></span><span>TLÁLOC<span className="brand-sub">PROJECT / 1.0</span></span></a><nav className="mode-switch" aria-label={t('view')}><button className={mode === 'live' ? 'active' : ''} onClick={returnLive}><Radio size={15} />{t('live')}</button><button className={mode === 'replay' ? 'active' : ''} onClick={() => { setMode('replay'); setPlaying(false); setIndex(0); }}><Activity size={15} />{t('replay')}</button></nav><div className="header-actions"><span className="experimental">{t('experimental')}</span><button className="icon-button" aria-label={t('language')} onClick={() => void i18n.changeLanguage(i18n.language.startsWith('es') ? 'en' : 'es')}><Globe2 size={17} /><span>{i18n.language.startsWith('es') ? 'ES' : 'EN'}</span></button><button className="icon-button" aria-label={t('settings')} onClick={() => setSettings(!settings)}><Settings2 size={18} /></button></div></header>
    <main><section className="page-heading"><div><div className="eyebrow"><span className="status-dot" />{t('situational')}</div><h1>{t('heading')}</h1><p>{t('subtitle')}</p></div><div className="source-tag"><ShieldCheck size={17} /><div>NOAA MRMS<small>{t('sourceNote')}</small></div></div></section>
    <p className="local-preference-note">{t(mode === 'live' ? 'localWatchNote' : 'temporaryWatchNote')}</p><section className="location-toolbar"><AddressSearch location={location} onSelect={move} /><button className="text-button" onClick={() => { if (!navigator.geolocation) { setError(t('errors.gps')); return; } navigator.geolocation.getCurrentPosition(position => move(position.coords.latitude, position.coords.longitude), () => setError(t('errors.gps')), { timeout: 15000 }); }}><LocateFixed size={17} />{t('useLocation')}</button><div className="coordinates"><label>{t('latitude')}<input type="number" min="-90" max="90" step="0.0001" value={latitudeDraft} onChange={e => setLatitudeDraft(e.target.value)} onBlur={() => { if (latitudeDraft.trim()) move(Number(latitudeDraft), location.lon); }} onKeyDown={e => { if (e.key === 'Enter') e.currentTarget.blur(); }} /></label><label>{t('longitude')}<input type="number" min="-180" max="180" step="0.0001" value={longitudeDraft} onChange={e => setLongitudeDraft(e.target.value)} onBlur={() => { if (longitudeDraft.trim()) move(location.lat, Number(longitudeDraft)); }} onKeyDown={e => { if (e.key === 'Enter') e.currentTarget.blur(); }} /></label></div><label className="radius-label"><Crosshair size={17} />{t('radius')} <strong>{location.radius_km} km</strong><input aria-label={t('radius')} type="range" min="10" max="100" step="5" value={location.radius_km} onChange={e => setLocation({ ...location, radius_km: Number(e.target.value) })} /></label></section>
    {settings && <section className="settings-panel"><label>{t('threshold')} <input type="number" min="0.1" max="10" step="0.1" value={location.threshold} onChange={e => { const threshold = Number(e.target.value); if (threshold >= .1 && threshold <= 10) setLocation({ ...location, threshold }); }} /> mm/h</label><div>{levels.map(level => <label key={level}><input type="checkbox" checked={enabled.includes(level)} onChange={e => setEnabled(e.target.checked ? [...enabled, level] : enabled.filter(l => l !== level))} />{t(level)}</label>)}</div><button className="text-button" aria-pressed={sound} onClick={async () => { if (!sound) { try { audio.current ??= new AudioContext(); await audio.current.resume(); setSound(true); } catch { setError(t('errors.sound')); } } else setSound(false); }}><Bell size={16} />{t(sound ? 'soundOn' : 'soundOff')}</button></section>}
    <div hidden={!settings}><div className="settings-panel"><NotificationSettings location={location} language={i18n.language} levels={enabled} active={mode === 'live'} /></div></div>
    {error && <div className="error-banner" role="alert">{error}</div>}
    {mode === 'replay' && <section className="replay-controls"><div><strong>{t('historical')}</strong><small>{t('replayNote')}</small></div><label>{t('startUTC')}<input aria-label={t('startUTC')} type="datetime-local" value={start} onChange={e => setStart(e.target.value)} /></label><label>{t('endUTC')}<input aria-label={t('endUTC')} type="datetime-local" value={end} onChange={e => setEnd(e.target.value)} /></label><button className="primary" disabled={replayBusy} onClick={() => void loadReplay()}>{t(replayBusy ? 'loading' : 'runReplay')}</button><button className="text-button" disabled={replayBusy} onClick={() => void loadReplay(true)}>{t('sample')}</button></section>}
    <div className="dashboard-grid"><section className="map-panel"><div className="panel-heading"><div><Layers size={16} /><strong>{t('radar')}</strong><label className="layer-selector"><span className="sr-only">{t('radarLayer')}</span><select aria-label={t('radarLayer')} value={selectedLayer} onChange={event => setSelectedLayer(event.target.value as 'rate' | 'reflectivity')}><option value="rate">{t('estimated')}</option><option value="reflectivity" disabled={!hasReflectivity}>{t(isComposite ? 'compositeReflectivity' : 'reflectivity')}</option></select></label></div><span className="map-status"><span className={`status-dot ${paused ? 'paused' : ''}`} />{t(busy ? 'updating' : mode === 'replay' ? 'historical' : paused ? 'paused' : 'live')}</span></div><div className="map-wrap"><RadarMap location={location} frame={shownFrame} predictions={predictions} onMove={move} /><div className="map-coordinate"><Crosshair size={14} />{location.lat.toFixed(4)}°, {location.lon.toFixed(4)}°<span>{t('clickMap')}</span></div>{!shownFrame && <div className="map-message">{t(busy || replayBusy ? 'loadingRadar' : frame ? 'noLayer' : mode === 'replay' ? 'chooseReplay' : 'noRadar')}</div>}{shownFrame && layer && layer.echo_pixels === 0 && <div className="map-message">{t(layer.valid_fraction === 0 ? 'noLayerCoverage' : selectedLayer === 'reflectivity' ? 'noEchoes' : 'noRate')}</div>}<div className="legend"><span>{t(selectedLayer === 'reflectivity' ? 'reflectivityLegend' : 'rainRate')}</span><div className={`legend-gradient ${selectedLayer}`} /><div className="legend-values">{(selectedLayer === 'reflectivity' ? ['5', '20', '40', '60+'] : ['0.1', '2', '10', '50+']).map(label => <span key={label}>{label}</span>)}</div><small><i />{t('missing')} · {selectedLayer === 'reflectivity' ? 'dBZ' : 'mm/h'}</small></div></div>{shownFrame && <a className="observation-source" href={shownFrame.source} target="_blank" rel="noreferrer">{t('source')} · {fmt(shownFrame.time)} · {layer?.unit ?? 'mm/h'} ↗</a>}{layer && <p className="layer-data">{t('layerCoverage')}: {Math.round(layer.valid_fraction * 100)}% · {t('layerPeak')}: {value(layer.max_value, ` ${layer.unit}`)}</p>}<p className="radar-explanation">{t(selectedLayer === 'reflectivity' ? isComposite ? 'compositeReflectivityNote' : 'reflectivityNote' : 'rateNote')}</p><div className="timeline"><button className="play-button" aria-label={t(playing ? 'pauseAnimation' : 'playAnimation')} disabled={frames.length < 2} onClick={() => setPlaying(!playing)}>{playing ? <Pause size={17} /> : <Play size={17} />}</button><div className="timeline-track"><input aria-label={t('observationTime')} type="range" min="0" max={Math.max(0, frames.length - 1)} value={Math.max(0, index)} disabled={!frames.length} onChange={e => { setPlaying(false); setIndex(Number(e.target.value)); }} /><div><span>{frames[0] ? fmt(frames[0].time) : '—'}</span><strong>{shownFrame ? fmt(shownFrame.time) : t('noObservation')}</strong><span>{frames.length ? `${index + 1}/${frames.length}` : '—'}</span></div></div>{mode === 'live' && <button className="text-button polling-button" onClick={() => setPaused(!paused)}>{paused ? <Play size={15} /> : <Pause size={15} />}{t(paused ? 'resume' : 'pause')}</button>}</div></section>
    <aside className="insight-panel"><div className="panel-heading"><div><Bell size={16} /><strong>{t('outlook')}</strong></div><span className="counter">{predictions.length}</span></div><section className="coverage-card"><div className="eyebrow">{t('dataStatus')}</div><h2>{coverage ? t(coverage.status, { defaultValue: t('unknown') }) : t('awaiting')}</h2><div className="coverage-meter"><i style={{ width: `${Math.max(0, Math.min(100, (coverage?.valid_fraction ?? 0) * 100))}%` }} /></div><div className="stat-pair"><span>{t('coverage')}<strong>{coverage ? `${Math.round(coverage.valid_fraction * 100)}%` : '—'}</strong></span><span>{t('age')}<strong>{value(coverage?.age_minutes, ' min')}</strong></span><span>{t('target')}<strong>{coverage ? t(coverage.target_valid ? 'observed' : 'missing') : '—'}</strong></span></div><p className="quality-note">{coverage && t(`quality.${coverage.quality}`, { defaultValue: t('unknown') })} · {t('qualityNote')}</p></section><div className="prediction-list">{predictions.length === 0 ? <div className="empty-outlook"><Activity size={29} /><strong>{t(mode === 'live' && frames.length > 0 && !isLatest ? 'latestOnly' : 'noThreats')}</strong><p>{t(mode === 'live' && frames.length > 0 && !isLatest ? 'latestOnlyNote' : 'noThreatsNote')}</p></div> : predictions.map(p => <article className={`threat ${p.level}`} key={p.id}><div className="threat-top"><span className="level-tag">{t(p.level)}</span><span>{t(p.confidence)} {t('confidence')}</span></div><h3>{t(p.intensity)} {t('precipitation')}<ArrowUpRight size={19} /></h3><div className="arrival">{p.arrival_minutes ? `${Math.round(p.arrival_minutes[0])}–${Math.round(p.arrival_minutes[1])} min` : t('arrivalUnknown')}<small>{t('arrivalWindow')}</small></div><dl><div><dt>{t('distance')}</dt><dd>{value(p.distance_km, ' km')}</dd></div><div><dt>{t('speed')}</dt><dd>{value(p.speed_kmh, ' km/h')}</dd></div><div><dt>{t('direction')}</dt><dd>{value(p.direction_deg, '°')}</dd></div><div><dt>{t('peak')}</dt><dd>{value(p.peak_rate, ' mm/h')}</dd></div><div><dt>{t('area')}</dt><dd>{value(p.area_km2, ' km²')}</dd></div><div><dt>{t('event')}</dt><dd>{t(`events.${p.event}`, { defaultValue: t('unknown') })}</dd></div></dl><small>{t('region')} {p.id} · {p.lat.toFixed(3)}°, {p.lon.toFixed(3)}°</small><small>{fmt(p.observation_time)} · {t(`quality.${p.data_quality}`, { defaultValue: t('quality.product_mask_only') })}</small></article>)}</div><p className="science-note">{t('scienceNote')}</p></aside></div>
    <section className="bottom-grid"><article className="history-panel"><div className="panel-heading"><div><Activity size={16} /><strong>{t('alertHistory')}</strong></div><span className="muted">{t('localHistory')}</span></div>{mode === 'replay' ? <p className="empty-row">{t('historyLiveOnly')}</p> : history.length ? <div className="history-rows">{history.slice(0, 12).map((item, n) => <div key={`${item.time}-${n}`}><span className={`history-dot ${item.alert.level}`} /><strong>{t(item.action, { defaultValue: t('unknown') })}</strong><span>{t(item.alert.level)}</span><time>{fmt(item.time)}</time></div>)}</div> : <p className="empty-row">{t('noHistory')}</p>}</article><article className="method-panel"><div className="eyebrow">{t('method')}</div><h3>{t('methodHeading')}</h3><p>{t('methodNote')}</p><div><span className="status-dot" />{t('refreshNote')}</div></article></section>
    {replay && mode === 'replay' && <section className="metrics-panel"><div className="panel-heading"><div><Activity size={16} /><strong>{t('metrics')}</strong></div><button className="text-button" onClick={exportReplay}><Download size={15} />{t('export')}</button></div><p className="quality-note">{t('metricsNote')}</p><div className="metric-grid">{Object.entries(replay.metrics).map(([key, val]) => <div key={key}><small>{t(`metricsLabels.${key}`, { defaultValue: t('unknownMetric') })}</small><strong>{value(val)}</strong></div>)}</div>{runs.length > 1 && <details><summary>{t('compareRuns')} ({runs.length})</summary><div className="comparison-table"><table><thead><tr><th>{t('run')}</th><th>{t('location')}</th><th>{t('metricsLabels.arrival_mae_minutes')}</th><th>{t('metricsLabels.trajectory_mae_km')}</th><th>{t('metricsLabels.false_alarm_forecasts')}</th></tr></thead><tbody>{runs.slice(0, 10).map(run => <tr key={run.run_id}><td>{fmt(run.start)}</td><td>{run.location.lat.toFixed(2)}, {run.location.lon.toFixed(2)} · {run.location.radius_km} km</td><td>{value(run.metrics.arrival_mae_minutes)}</td><td>{value(run.metrics.trajectory_mae_km)}</td><td>{value(run.metrics.false_alarm_forecasts)}</td></tr>)}</tbody></table></div></details>}</section>}
    <footer><span>TLÁLOC PROJECT <span className="footer-separator">/</span> {t('footer')}</span><span>{t('notOfficial')}</span></footer></main>
  </div>;
}
