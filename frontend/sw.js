/**
 * JARVIS Service Worker — PWA offline support
 * Cache-first para assets estáticos, network-first para API.
 */

const CACHE_NAME = 'jarvis-v9';
const OFFLINE_URL = '/';

const PRECACHE_ASSETS = ['/', '/manifest.json'];

const API_PREFIXES = [
  '/health', '/status', '/chat', '/voice', '/agents',
  '/investigate', '/analyze', '/architect', '/generate',
  '/tasks', '/memory', '/metrics', '/network',
];

self.addEventListener('install', (event) => {
  event.waitUntil(
    caches.open(CACHE_NAME)
      .then((cache) => cache.addAll(PRECACHE_ASSETS).catch(() => {}))
      .then(() => self.skipWaiting())
  );
});

self.addEventListener('activate', (event) => {
  event.waitUntil(
    caches.keys()
      .then((names) => Promise.all(
        names.filter((n) => n !== CACHE_NAME).map((n) => caches.delete(n))
      ))
      .then(() => self.clients.claim())
  );
});

self.addEventListener('fetch', (event) => {
  const { request } = event;
  const url = new URL(request.url);
  if (url.protocol === 'ws:' || url.protocol === 'wss:') return;
  const isApi = API_PREFIXES.some((p) => url.pathname.startsWith(p));
  event.respondWith(isApi ? networkFirst(request) : cacheFirst(request));
});

async function cacheFirst(request) {
  const cached = await caches.match(request);
  if (cached) return cached;
  try {
    const response = await fetch(request);
    if (response.ok && request.method === 'GET') {
      const cache = await caches.open(CACHE_NAME);
      cache.put(request, response.clone());
    }
    return response;
  } catch {
    const fallback = await caches.match(OFFLINE_URL);
    return fallback || new Response(
      '<html><body style="background:#000;color:#00e5ff;font-family:monospace;text-align:center;padding:40px"><h1>J.A.R.V.I.S.</h1><p>Offline. Conecte ao servidor para continuar.</p></body></html>',
      { headers: { 'Content-Type': 'text/html' } }
    );
  }
}

async function networkFirst(request) {
  try {
    const response = await fetch(request);
    if (response.ok && request.method === 'GET') {
      const cache = await caches.open(CACHE_NAME);
      cache.put(request, response.clone());
    }
    return response;
  } catch {
    const cached = await caches.match(request);
    return cached || new Response(
      JSON.stringify({ error: 'offline', message: 'JARVIS offline.' }),
      { status: 503, headers: { 'Content-Type': 'application/json' } }
    );
  }
}

self.addEventListener('push', (event) => {
  const data = event.data ? event.data.json() : {};
  event.waitUntil(
    self.registration.showNotification(data.title || 'JARVIS', {
      body: data.body || 'Notificacao do JARVIS',
      tag: 'jarvis-notification',
    })
  );
});
