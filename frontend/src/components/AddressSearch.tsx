import { useEffect, useRef, useState } from 'react';
import { MapPin, Search } from 'lucide-react';
import { useTranslation } from 'react-i18next';
import { request } from '../services/api';
import type { Location, Place } from '../services/api';

function retryDelay(milliseconds: number, signal: AbortSignal): Promise<void> {
  return new Promise(resolve => {
    const finish = () => { clearTimeout(timer); signal.removeEventListener('abort', finish); resolve(); };
    const timer = window.setTimeout(finish, milliseconds);
    signal.addEventListener('abort', finish, { once: true });
    if (signal.aborted) finish();
  });
}

export default function AddressSearch({ location, onSelect }: { location: Location; onSelect: (lat: number, lon: number) => void }) {
  const { t, i18n } = useTranslation();
  const [text, setText] = useState('');
  const [items, setItems] = useState<Place[]>([]);
  const [status, setStatus] = useState('');
  const [open, setOpen] = useState(false);
  const [active, setActive] = useState(-1);
  const box = useRef<HTMLFormElement>(null);
  const controller = useRef<AbortController | null>(null);
  const revision = useRef(0);
  const debounce = useRef<number | undefined>(undefined);
  const skipSuggestion = useRef(false);
  const cache = useRef(new Map<string, Place[]>());
  const language = i18n.language.startsWith('es') ? 'es' : 'en';

  function close() { clearTimeout(debounce.current); revision.current++; controller.current?.abort(); setOpen(false); setActive(-1); }
  function choose(place: Place) { skipSuggestion.current = true; setText(place.name); close(); onSelect(place.lat, place.lon); }
  async function find(suggest: boolean) {
    const q = text.trim();
    if (q.length < (suggest ? 3 : 2)) return;
    controller.current?.abort();
    const current = ++revision.current;
    const abort = new AbortController(); controller.current = abort;
    clearTimeout(debounce.current);
    const params = new URLSearchParams({ q, language, lat: location.lat.toFixed(2), lon: location.lon.toFixed(2), suggest: String(suggest), external: 'true' });
    const key = params.toString();
    setOpen(true); setActive(-1); setStatus('searching'); setItems([]);
    // At most three retries, spaced beyond the provider's one-request/second limit.
    // Aborting a browser request can leave its provider request finishing on the server.
    for (let attempt = 0; attempt <= 3; attempt++) {
      try {
        const found = cache.current.get(key) ?? await request<Place[]>(`/api/search?${key}`, { signal: abort.signal });
        if (abort.signal.aborted || revision.current !== current) return;
        if (cache.current.size >= 50) cache.current.clear();
        cache.current.set(key, found); setItems(found); setStatus(found.length ? '' : 'noPlaces');
        return;
      } catch (error) {
        if (abort.signal.aborted || revision.current !== current) return;
        if (error instanceof Error && error.message === 'search_rate_limit' && attempt < 3) {
          await retryDelay(1100 * 2 ** attempt, abort.signal);
          if (abort.signal.aborted || revision.current !== current) return;
          continue;
        }
        setStatus(`errors.${error instanceof Error ? error.message : 'request_failed'}`);
        return;
      }
    }
  }
  useEffect(() => {
    revision.current++; controller.current?.abort(); setItems([]); setStatus(''); setActive(-1);
    if (skipSuggestion.current) { skipSuggestion.current = false; return; }
    if (text.trim().length < 3) { setOpen(false); return; }
    debounce.current = window.setTimeout(() => void find(true), 900);
    return () => clearTimeout(debounce.current);
  }, [text, language, location.lat, location.lon]);
  useEffect(() => {
    const outside = (event: PointerEvent) => { if (!box.current?.contains(event.target as Node)) close(); };
    document.addEventListener('pointerdown', outside);
    return () => { document.removeEventListener('pointerdown', outside); controller.current?.abort(); };
  }, []);
  return <form className="search-box" ref={box} onSubmit={event => { event.preventDefault(); if (open && active >= 0 && items[active]) choose(items[active]); else void find(false); }}>
    <Search size={18} /><input role="combobox" aria-label={t('search')} aria-autocomplete="list" aria-expanded={open} aria-controls="address-options" aria-activedescendant={open && active >= 0 ? `address-option-${active}` : undefined} placeholder={t('search')} value={text} minLength={2} maxLength={200} autoComplete="off" onChange={event => setText(event.target.value)} onFocus={() => { if (items.length || status) setOpen(true); }} onKeyDown={event => {
      if (event.key === 'Escape') { event.preventDefault(); close(); }
      if ((event.key === 'ArrowDown' || event.key === 'ArrowUp') && items.length) { event.preventDefault(); setOpen(true); setActive(old => old < 0 ? event.key === 'ArrowDown' ? 0 : items.length - 1 : (old + (event.key === 'ArrowDown' ? 1 : -1) + items.length) % items.length); }
    }} />
    <button type="submit">{t('find')}</button>
    {open && <div className="search-results"><div role="status" aria-live="polite">{status && <p>{t(status, { defaultValue: t('errors.search_unavailable') })}</p>}</div><div id="address-options" role="listbox" aria-label={t('searchSuggestions')}>{items.map((place, index) => <button id={`address-option-${index}`} role="option" aria-selected={index === active} className={index === active ? 'selected' : ''} type="button" key={`${place.lat},${place.lon},${index}`} onClick={() => choose(place)}><MapPin size={14} />{place.name}</button>)}</div></div>}
    <small className="search-consent">{t('searchProviderNote')}</small>
  </form>;
}
