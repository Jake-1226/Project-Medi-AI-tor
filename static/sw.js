// KILL SWITCH: This service worker destroys itself and all caches immediately
self.addEventListener('install', function() { self.skipWaiting(); });
self.addEventListener('activate', function(e) {
    e.waitUntil(caches.keys().then(function(n){return Promise.all(n.map(function(k){return caches.delete(k);}));}).then(function(){return self.registration.unregister();}).then(function(){return self.clients.claim();}));
});
self.addEventListener('fetch', function(e) { e.respondWith(fetch(e.request)); });
