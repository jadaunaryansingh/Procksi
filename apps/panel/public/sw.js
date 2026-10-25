// Service Worker to handle background push notification actions

self.addEventListener('install', () => {
  self.skipWaiting();
});

self.addEventListener('activate', (event) => {
  event.waitUntil(self.clients.claim());
});

self.addEventListener('notificationclick', (event) => {
  event.notification.close();

  const action = event.action;
  
  if (action === 'extend-5' || action === 'extend-10') {
    const minutes = action === 'extend-5' ? 5 : 10;
    
    // Broadcast the extension request to all open PMS windows
    event.waitUntil(
      self.clients.matchAll({ type: 'window', includeUncontrolled: true }).then((clients) => {
        if (clients && clients.length > 0) {
          clients.forEach((client) => {
            client.postMessage({
              type: 'EXTEND_SLOT',
              minutes: minutes
            });
          });
        }
      })
    );
  } else {
    // Default notification click: focus the active evaluation tab
    event.waitUntil(
      self.clients.matchAll({ type: 'window', includeUncontrolled: true }).then((clients) => {
        // Try to find a client that is on the evaluation page
        for (const client of clients) {
          if (client.url.includes('/panel/evaluation/') && 'focus' in client) {
            return client.focus();
          }
        }
        // If not found but we have a client, focus the first one
        if (clients.length > 0 && 'focus' in clients[0]) {
          return clients[0].focus();
        }
      })
    );
  }
});
