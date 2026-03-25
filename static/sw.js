// Self-destructing service worker — clears all caches and unregisters itself
self.addEventListener('install', () => self.skipWaiting());
self.addEventListener('activate', (event) => {
    event.waitUntil(
        caches.keys()
            .then(names => Promise.all(names.map(n => caches.delete(n))))
            .then(() => self.registration.unregister())
            .then(() => self.clients.claim())
    );
});
// Pass all requests through to network — never cache
self.addEventListener('fetch', (event) => {
    event.respondWith(fetch(event.request));
});
