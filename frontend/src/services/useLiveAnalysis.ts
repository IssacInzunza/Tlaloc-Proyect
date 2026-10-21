import { useEffect, useState } from 'react';
import { query, request, type Analysis, type Location } from './api';

/** Serial polling lets slow radar downloads finish instead of cancelling every minute. */
export function useLiveAnalysis(location: Location, active: boolean, onResult: (result: Analysis) => void, onError: (error: unknown) => void) {
  const [busy, setBusy] = useState(false);
  const [lastChecked, setLastChecked] = useState<number | null>(null);
  const [failed, setFailed] = useState(false);
  const [online, setOnline] = useState(navigator.onLine);
  useEffect(() => {
    if (!active) return;
    let disposed = false, inFlight = false;
    let timer: ReturnType<typeof setTimeout> | undefined;
    let controller: AbortController | undefined;
    setLastChecked(null); setFailed(false);
    async function poll() {
      if (disposed || inFlight) return;
      clearTimeout(timer);
      if (!navigator.onLine) { setOnline(false); return; }
      inFlight = true; setBusy(true);
      controller = new AbortController();
      const timeout = setTimeout(() => controller?.abort(), 240000);
      try {
        const result = await request<Analysis>(`/api/analysis?${query(location)}`, { signal: controller.signal, cache: 'no-store' });
        if (result.coverage.status === 'provider_unavailable') throw new Error('provider_unavailable');
        if (!disposed) { onResult(result); setLastChecked(Date.now()); setFailed(false); }
      } catch (error) {
        if (!disposed) { setFailed(true); onError(error); }
      } finally {
        clearTimeout(timeout); inFlight = false;
        if (!disposed) { setBusy(false); timer = setTimeout(() => void poll(), 60000); }
      }
    }
    const wake = () => { setOnline(navigator.onLine); if (document.visibilityState === 'visible') void poll(); };
    const offline = () => setOnline(false);
    void poll();
    window.addEventListener('online', wake); window.addEventListener('offline', offline);
    window.addEventListener('focus', wake); document.addEventListener('visibilitychange', wake);
    return () => {
      disposed = true; controller?.abort(); clearTimeout(timer); setBusy(false);
      window.removeEventListener('online', wake); window.removeEventListener('offline', offline);
      window.removeEventListener('focus', wake); document.removeEventListener('visibilitychange', wake);
    };
    // Callbacks deliver state; location and mode own the request lifecycle.
  }, [location, active]);
  return { busy, lastChecked, failed, online };
}
