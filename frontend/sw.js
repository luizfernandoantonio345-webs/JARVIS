/* JARVIS v8.0 — Service Worker (PWA)
   Estratégia: Network-first com fallback para cache.
   Assets estáticos (HTML/CSS/JS): cache-first.
   API calls: sempre network, sem cache.
*/

const CACHE_NAME = 'jarvis-v8';
const STATIC_ASSETS = [
  '/',
  '/static/index.html',
];

// ── Install: pré-cacheia assets estáticos ────────────────────────────────────
self.addEventListener('install', (event) => {
  event.waitUntil(
    caches.open(CACHE_NAME).then((cache) => {
      return cache.addAll(STATIC_ASSETS).catch(() => {
        // Silencia erros de assets não encontrados
      });
    })
  );
  self.skipWaiting();
});

// ── Activate: remove caches antigos ─────────────────────────────────────────
self.addEventListener('activate', (event) => {
  event.waitUntil(
    caches.keys().then((keys) =>
      Promise.all(
        keys
          .filter((key) => key !== CACHE_NAME)
          .map((key) => caches.delete(key))
      )
    )
  );
  self.clients.claim();
});

// ── Fetch: network-first, fallback para cache ────────────────────────────────
self.addEventListener('fetch', (event) => {
  const url = new URL(event.request.url);

  // Requisições de API: sempre network, sem cache
  if (
    url.pathname.startsWith('/chat') ||
    url.pathname.startsWith('/voice') ||
    url.pathname.startsWith('/agents') ||
    url.pathname.startsWith('/generate') ||
    url.pathname.startsWith('/tasks') ||
    url.pathname.startsWith('/metrics') ||
    url.pathname.startsWith('/health') ||
    url.pathname.startsWith('/ws')
  ) {
    event.respondWith(fetch(event.request));
    return;
  }

  // CDN e recursos externos: sem cache
  if (!url.origin.includes(self.location.origin)) {
    event.respondWith(fetch(event.request).catch(() => new Response('', { status: 503 })));
    return;
  }

  // Assets estáticos: cache-first
  event.respondWith(
    caches.match(event.request).then((cached) => {
      if (cached) return cached;

      return fetch(event.request)
        .then((response) => {
          if (response.ok) {
            const clone = response.clone();
            caches.open(CACHE_NAME).then((cache) => cache.put(event.request, clone));
          }
          return response;
        })
        .catch(() => {
          // Fallback offline: retorna a página principal do cache
          if (event.request.headers.get('accept').includes('text/html')) {
            return caches.match('/') || caches.match('/static/index.html');
          }
          return new Response('Offline', { status: 503 });
        });
    })
  );
});

// ── Push Notifications (futuro) ──────────────────────────────────────────────
self.addEventListener('push', (event) => {
  const data = event.data ? event.data.json() : {};
  const title = data.title || 'JARVIS';
  const options = {
    body: data.body || 'Nova notificação do JARVIS',
    icon: '/static/icon-192.png',
    badge: '/static/icon-72.png',
    vibrate: [200, 100, 200],
    data: data,
  };
  event.waitUntil(self.registration.showNotification(title, options));
});
