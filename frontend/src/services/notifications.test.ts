import { afterEach, describe, expect, it, vi } from 'vitest';
import { disablePush, enablePush, notificationStorageKey, readPushId } from './notifications';

afterEach(() => vi.unstubAllGlobals());
const watch = { location: { lat: 32.6, lon: -115.4, radius_km: 50, threshold: .2 }, language: 'es', levels: ['preventive', 'imminent'] };
function setup(permission: NotificationPermission = 'granted') {
  const values = new Map<string, string>();
  const unsubscribe = vi.fn().mockResolvedValue(true);
  const subscription = { toJSON: () => ({ endpoint: 'https://push.example.invalid/test', keys: { auth: 'fixture', p256dh: 'fixture' } }), unsubscribe };
  const subscribe = vi.fn().mockResolvedValue(subscription);
  const registration = { pushManager: { getSubscription: vi.fn().mockResolvedValue(null), subscribe } };
  const register = vi.fn().mockResolvedValue(registration);
  const requestPermission = vi.fn().mockResolvedValue(permission);
  vi.stubGlobal('window', { isSecureContext: true, Notification: {}, PushManager: {} });
  vi.stubGlobal('Notification', { requestPermission });
  vi.stubGlobal('navigator', { serviceWorker: { register, ready: Promise.resolve(registration), getRegistration: vi.fn().mockResolvedValue({ pushManager: { getSubscription: vi.fn().mockResolvedValue(subscription) } }) } });
  vi.stubGlobal('localStorage', { getItem: (key: string) => values.get(key) ?? null, setItem: (key: string, value: string) => values.set(key, value), removeItem: (key: string) => values.delete(key) });
  const fetch = vi.fn(async (url: string, _options?: RequestInit) => ({ ok: true, status: 200, json: async () => url.endsWith('/config') ? { enabled: true, public_key: 'BAECAwQ' } : { id: 'test_subscription_123456', enabled: true } }));
  vi.stubGlobal('fetch', fetch);
  return { values, fetch, register, subscribe, requestPermission, unsubscribe };
}
describe('Web Push lifecycle', () => {
  it('asks permission directly, registers a root worker and persists only the capability', async () => {
    const state = setup();
    const pending = enablePush(watch);
    expect(state.requestPermission).toHaveBeenCalledOnce();
    expect(state.fetch).not.toHaveBeenCalled();
    await expect(pending).resolves.toBe('test_subscription_123456');
    expect(state.register).toHaveBeenCalledWith('/sw.js', { scope: '/' });
    expect(state.subscribe.mock.calls[0][0].userVisibleOnly).toBe(true);
    expect(state.values.size).toBe(1);
    expect(readPushId()).toBe('test_subscription_123456');
    const options = state.fetch.mock.calls[1][1] as RequestInit;
    expect(JSON.parse(options.body as string)).toMatchObject(watch);
  });
  it('permission denied does not register, contact server or create a subscription', async () => {
    const state = setup('denied');
    await expect(enablePush(watch)).rejects.toThrow('denied');
    expect(state.fetch).not.toHaveBeenCalled(); expect(state.register).not.toHaveBeenCalled();
  });
  it('stops server monitoring before browser cleanup and retains id on connection failure', async () => {
    const state = setup(); state.values.set(notificationStorageKey, 'test_subscription_123456');
    state.fetch.mockRejectedValueOnce(new TypeError('offline'));
    await expect(disablePush('test_subscription_123456')).rejects.toThrow('offline');
    expect(readPushId()).toBe('test_subscription_123456'); expect(state.unsubscribe).not.toHaveBeenCalled();
    await disablePush('test_subscription_123456');
    expect(readPushId()).toBeNull(); expect(state.unsubscribe).toHaveBeenCalledOnce();
  });
  it('does not report enabled if browser storage fails and rolls back server watch', async () => {
    const state = setup(); vi.stubGlobal('localStorage', { setItem: () => { throw new Error('blocked'); } });
    await expect(enablePush(watch)).rejects.toThrow('storage');
    expect(state.fetch.mock.calls.at(-1)?.[0]).toContain('/test_subscription_123456');
  });
});
