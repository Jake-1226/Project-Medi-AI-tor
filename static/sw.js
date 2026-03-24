// Service Worker for Medi-AI-tor PWA
const CACHE_NAME = 'medi-ai-tor-v3';
const urlsToCache = [
  '/mobile',
  '/static/css/mobile.css',
  '/static/js/mobile.js',
  '/static/manifest.json'
];

// Install event - cache only mobile resources (not dashboard JS/CSS)
self.addEventListener('install', (event) => {
  self.skipWaiting(); // Activate immediately
  event.waitUntil(
    caches.open(CACHE_NAME)
      .then((cache) => cache.addAll(urlsToCache))
  );
});

// Fetch event - network first, cache fallback (never serve stale JS/CSS)
self.addEventListener('fetch', (event) => {
  const url = new URL(event.request.url);
  // Never cache API calls, HTML pages, or dashboard resources
  if (url.pathname.startsWith('/api/') || 
      url.pathname.endsWith('.html') ||
      url.pathname === '/' ||
      url.pathname === '/technician' ||
      url.pathname === '/login' ||
      url.pathname === '/fleet' ||
      url.pathname === '/monitoring' ||
      url.pathname.includes('app.js') ||
      url.pathname.includes('style.css') ||
      url.pathname.includes('customer.js') ||
      url.pathname.includes('customer.css') ||
      url.pathname.includes('fleet.js') ||
      url.pathname.includes('fleet.css') ||
      url.pathname.includes('realtime.js') ||
      url.pathname.includes('realtime.css')) {
    // Network only — no caching
    event.respondWith(fetch(event.request));
    return;
  }
  // For mobile resources: network first, cache fallback
  event.respondWith(
    fetch(event.request)
      .then((response) => {
        if (response && response.status === 200) {
          const clone = response.clone();
          caches.open(CACHE_NAME).then(c => c.put(event.request, clone));
        }
        return response;
      })
      .catch(() => caches.match(event.request))
  );
});

// Activate event - delete ALL old caches
self.addEventListener('activate', (event) => {
  event.waitUntil(
    caches.keys().then((names) => 
      Promise.all(names.filter(n => n !== CACHE_NAME).map(n => caches.delete(n)))
    ).then(() => self.clients.claim()) // Take control immediately
  );
});
