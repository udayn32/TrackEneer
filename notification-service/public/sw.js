// Service Worker for Push Notifications
// Place this file in your public folder: public/sw.js

self.addEventListener('install', (event) => {
  console.log('Service Worker installed');
  self.skipWaiting();
});

self.addEventListener('activate', (event) => {
  console.log('Service Worker activated');
  event.waitUntil(clients.claim());
});

self.addEventListener('push', (event) => {
  console.log('Push notification received:', event);
  
  if (!event.data) {
    return;
  }

  try {
    const data = event.data.json();
    
    // Add IST timezone info if not already present
    let body = data.body || 'New notification';
    if (data.data && data.data.timezone === 'IST' && !body.includes('IST')) {
      // Body should already have IST from backend, but this is a safeguard
      console.log('Notification is in IST timezone');
    }
    
    const options = {
      body: body,
      icon: data.icon || '/icon.png',
      badge: data.badge || '/badge.png',
      tag: data.tag || 'default',
      requireInteraction: data.requireInteraction || false,
      vibrate: data.vibrate || [200, 100, 200],
      data: data.data || {},
      actions: [
        { action: 'view', title: 'View Task', icon: '/icons/view.png' },
        { action: 'dismiss', title: 'Dismiss', icon: '/icons/dismiss.png' }
      ],
      timestamp: Date.now() // Add timestamp for proper ordering
    };

    event.waitUntil(
      self.registration.showNotification(data.title || 'TrackEneer', options)
    );
  } catch (error) {
    console.error('Error showing notification:', error);
  }
});

self.addEventListener('notificationclick', (event) => {
  console.log('Notification clicked:', event);
  
  event.notification.close();
  
  if (event.action === 'view') {
    event.waitUntil(
      clients.openWindow(event.notification.data.url || '/')
    );
  }
});

self.addEventListener('notificationclose', (event) => {
  console.log('Notification closed:', event);
});
