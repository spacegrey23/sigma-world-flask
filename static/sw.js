// Nazwa pamięci podręcznej (cache)
const CACHE_NAME = 'sigma-world-flask-cache-v1';

// Lista plików do zapisania w pamięci podręcznej.
// Ścieżki muszą być absolutne z perspektywy serwera.
const urlsToCache = [
  '/', // Główna strona aplikacji
  '/static/css/style.css',
  '/static/js/main.js',
  '/static/manifest.json',
  '/static/icons/icon-192x192.png',
  '/static/icons/icon-512x512.png',
  'https://cdn.socket.io/4.7.5/socket.io.min.js', // Biblioteka Socket.IO również jest cachowana
  'https://fonts.googleapis.com/css2?family=Prompt:wght@300;400;500;600;700&display=swap' // Czcionka
];

// Instalacja Service Workera
self.addEventListener('install', event => {
  // Czekamy, aż wszystkie pliki zostaną zapisane w cache
  event.waitUntil(
    caches.open(CACHE_NAME)
      .then(cache => {
        console.log('Otwarto cache');
        return cache.addAll(urlsToCache);
      })
      .catch(err => {
        console.error('Nie udało się zapisać plików w cache podczas instalacji:', err);
      })
  );
});

// Aktywacja Service Workera
self.addEventListener('activate', event => {
  const cacheWhitelist = [CACHE_NAME];
  event.waitUntil(
    caches.keys().then(cacheNames => {
      return Promise.all(
        cacheNames.map(cacheName => {
          // Usuwamy stare wersje pamięci podręcznej
          if (cacheWhitelist.indexOf(cacheName) === -1) {
            return caches.delete(cacheName);
          }
        })
      );
    })
  );
});

// Przechwytywanie żądań sieciowych
self.addEventListener('fetch', event => {
  event.respondWith(
    caches.match(event.request)
      .then(response => {
        // Jeśli plik jest w cache, zwracamy go
        if (response) {
          return response;
        }

        // Jeśli pliku nie ma w cache, próbujemy pobrać go z sieci
        return fetch(event.request);
      })
  );
});