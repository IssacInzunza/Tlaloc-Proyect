/* Receives browser Web Push even when no Tláloc tab is open. No offline radar cache. */
self.addEventListener('install', event => event.waitUntil(self.skipWaiting()));
self.addEventListener('activate', event => event.waitUntil(self.clients.claim()));
self.addEventListener('push', event => {
  let payload = {};
  try { const value = event.data?.json(); if (value && typeof value === 'object' && !Array.isArray(value)) payload = value; } catch { /* Show a generic visible notice for malformed pushes. */ }
  const safeText = (value, fallback, max) => typeof value === 'string' && value.trim() ? value.replace(/[\u0000-\u001f]/g, ' ').slice(0, max) : fallback;
  const title = safeText(payload.title, 'Tláloc', 100);
  const body = safeText(payload.body, 'Abre Tláloc para consultar el estado del radar. / Open Tláloc for radar status.', 500);
  event.waitUntil(self.registration.showNotification(title, { body, tag: safeText(payload.tag, 'tlaloc-rain', 100) }));
});
self.addEventListener('notificationclick', event => {
  event.notification.close();
  // Never trust a URL received in a push payload.
  const home = new URL('/', self.location.origin).href;
  event.waitUntil(self.clients.matchAll({ type: 'window', includeUncontrolled: true }).then(async windows => {
    const existing = windows.find(client => new URL(client.url).origin === self.location.origin);
    if (existing) { await existing.navigate(home); return existing.focus(); }
    return self.clients.openWindow(home);
  }));
});
