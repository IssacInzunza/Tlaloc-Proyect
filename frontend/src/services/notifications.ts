import type { Location } from './api';

export const notificationStorageKey = 'tlaloc.pushId';
export interface Watch { location: Location; language: string; levels: string[] }
export interface PushStatus { enabled: boolean; last_checked: string | null; last_sent: string | null; last_error: string | null }
export class PushRequestError extends Error {
  constructor(public status: number) { super('notification_request_failed'); }
}
async function api<T>(path: string, options?: RequestInit): Promise<T> {
  const response = await fetch(`/api/notifications${path}`, { ...options, credentials: 'same-origin', headers: { 'Content-Type': 'application/json' } });
  if (!response.ok) throw new PushRequestError(response.status);
  return (response.status === 204 ? undefined : await response.json()) as T;
}
const path = (id: string) => `/${encodeURIComponent(id)}`;
export const pushStatus = (id: string, signal?: AbortSignal) => api<PushStatus>(`${path(id)}/status`, { signal });
export const updatePush = (id: string, watch: Watch, signal?: AbortSignal) => api(`${path(id)}/update`, { method: 'POST', body: JSON.stringify(watch), signal });
export const stopPush = (id: string) => api(path(id), { method: 'DELETE' });
export const testPush = (id: string) => api(`${path(id)}/test`, { method: 'POST' });
export function readPushId(): string | null {
  try { const id = localStorage.getItem(notificationStorageKey); return id && /^[A-Za-z0-9_-]{16,160}$/.test(id) ? id : null; } catch { return null; }
}
export function pushSupported() {
  return window.isSecureContext && 'Notification' in window && 'serviceWorker' in navigator && 'PushManager' in window;
}
export async function enablePush(watch: Watch): Promise<string> {
  if (!pushSupported()) throw new Error('unsupported');
  // Must happen before network awaits: this function is called directly by a click.
  const permission = await Notification.requestPermission();
  if (permission !== 'granted') throw new Error(permission === 'denied' ? 'denied' : 'dismissed');
  const config = await api<{ enabled: boolean; public_key: string }>('/config');
  if (!config.enabled || !config.public_key) throw new Error('unavailable');
  await navigator.serviceWorker.register('/sw.js', { scope: '/' });
  const registration = await navigator.serviceWorker.ready;
  const base64 = config.public_key.replace(/-/g, '+').replace(/_/g, '/');
  const key = Uint8Array.from(atob(base64.padEnd(Math.ceil(base64.length / 4) * 4, '=')), char => char.charCodeAt(0));
  const subscription = await registration.pushManager.getSubscription() ?? await registration.pushManager.subscribe({ userVisibleOnly: true, applicationServerKey: key });
  const result = await api<{ id: string; enabled: boolean }>('/subscribe', { method: 'POST', body: JSON.stringify({ ...watch, subscription: subscription.toJSON() }) });
  if (!result.enabled || !/^[A-Za-z0-9_-]{16,160}$/.test(result.id)) throw new Error('subscription');
  try { localStorage.setItem(notificationStorageKey, result.id); }
  catch { await stopPush(result.id).catch(() => undefined); throw new Error('storage'); }
  return result.id;
}
export async function disablePush(id: string) {
  try { await stopPush(id); } catch (error) { if (!(error instanceof PushRequestError && error.status === 404)) throw error; }
  try { localStorage.removeItem(notificationStorageKey); } catch { /* Server has stopped this watch. */ }
  // Stopping server-side first guarantees no new deliveries even if unsubscribe fails.
  try { await (await (await navigator.serviceWorker.getRegistration('/'))?.pushManager.getSubscription())?.unsubscribe(); } catch { /* Best effort browser cleanup. */ }
}
