const CACHE_NAME = 'instasavehub-pwa-v5';
const OFFLINE_URL = '/offline/';

const PRECACHE_ASSETS = [
  '/',
  '/offline/',
  '/static/css/tokens.css',
  '/static/css/glass-orbit.css',
  '/static/css/components.css',
  '/static/css/responsive.css',
  '/static/images/logo.png',
  '/static/images/icon-192.png',
  '/static/images/icon-512.png',
  '/static/js/pwa-install.js',
  '/static/js/orbit-engine.js'
];

const EXCLUDED_PATTERNS = [
  /\/admin\//,
  /\/auth\//,
  /\/donations\//,
  /\/donate\//,
  /\/payment\//,
  /\/api\//,
  /pagead2\.googlesyndication\.com/,
  /doubleclick\.net/,
  /google-analytics\.com/,
  /googletagmanager\.com/,
  /checkout\.razorpay\.com/,
  /api\.razorpay\.com/
];

function isExcluded(urlStr) {
  return EXCLUDED_PATTERNS.some((pattern) => pattern.test(urlStr));
}

self.addEventListener('install', (event) => {
  self.skipWaiting();
  event.waitUntil(
    caches.open(CACHE_NAME).then((cache) => {
      return cache.addAll(PRECACHE_ASSETS).catch((err) => {
        console.warn('[PWA SW] Precache warning:', err);
      });
    })
  );
});

self.addEventListener('activate', (event) => {
  event.waitUntil(
    caches.keys().then((keys) =>
      Promise.all(
        keys.filter((k) => k !== CACHE_NAME).map((k) => {
          return caches.delete(k);
        })
      )
    ).then(() => self.clients.claim())
  );
});

self.addEventListener('fetch', (event) => {
  if (event.request.method !== 'GET') return;

  const url = new URL(event.request.url);

  // Strictly avoid caching admin, auth, payment, API, and ad networks
  if (isExcluded(event.request.url) || isExcluded(url.pathname)) {
    return;
  }

  // Navigation requests: HTML pages (Network-first with offline fallback)
  if (event.request.mode === 'navigate') {
    event.respondWith(
      fetch(event.request)
        .then((networkResponse) => {
          if (networkResponse && networkResponse.status === 200) {
            const responseClone = networkResponse.clone();
            caches.open(CACHE_NAME).then((cache) => cache.put(event.request, responseClone));
          }
          return networkResponse;
        })
        .catch(async () => {
          const cached = await caches.match(event.request);
          if (cached) return cached;
          const offlinePage = await caches.match(OFFLINE_URL);
          if (offlinePage) return offlinePage;
          return new Response(
            '<!DOCTYPE html><html><head><title>Offline</title><meta name="viewport" content="width=device-width, initial-scale=1"></head><body style="background:#030712;color:#f8fafc;font-family:sans-serif;text-align:center;padding:50px;"><h1>You are offline</h1><p>Please check your connection and reload.</p></body></html>',
            { headers: { 'Content-Type': 'text/html; charset=utf-8' } }
          );
        })
    );
    return;
  }

  // Static Assets (Cache-First with Background Revalidation)
  if (url.origin === self.location.origin && url.pathname.startsWith('/static/')) {
    event.respondWith(
      caches.match(event.request).then((cachedResponse) => {
        const fetchPromise = fetch(event.request)
          .then((networkResponse) => {
            if (networkResponse && networkResponse.status === 200) {
              const responseClone = networkResponse.clone();
              caches.open(CACHE_NAME).then((cache) => cache.put(event.request, responseClone));
            }
            return networkResponse;
          })
          .catch(() => null);

        return cachedResponse || fetchPromise;
      })
    );
  }
});
