// Service Worker for Push Notifications
// Copied from notification-service/public/sw.js

self.addEventListener('install', (event) => {
  console.log('Service Worker installed (client)');
  self.skipWaiting();
});

self.addEventListener('activate', (event) => {
  console.log('Service Worker activated (client)');
  event.waitUntil(clients.claim());
});

self.addEventListener('push', (event) => {
  console.log('Push notification received (client):', event);
  
  if (!event.data) {
    return;
  }

  try {
    const data = event.data.json();
    let body = data.body || 'New notification';

    const options = {
      body: body,
      icon: data.icon || '/icon.png',
      badge: data.badge || '/badge.png',
      tag: data.tag || 'default',
      requireInteraction: data.requireInteraction || false,
      vibrate: data.vibrate || [200, 100, 200],
      data: data.data || {},
      actions: [
        { action: 'view', title: 'View Task' },
        { action: 'dismiss', title: 'Dismiss' }
      ],
      timestamp: Date.now()
    };

    event.waitUntil(
      self.registration.showNotification(data.title || 'TrackEneer', options)
    );
  } catch (error) {
    console.error('Error showing notification (client):', error);
  }
});

self.addEventListener('notificationclick', (event) => {
  console.log('Notification clicked (client):', event);
  event.notification.close();
  if (event.action === 'view') {
    event.waitUntil(clients.openWindow(event.notification.data.url || '/'));
  }
});

self.addEventListener('notificationclose', (event) => {
  console.log('Notification closed (client):', event);
});
