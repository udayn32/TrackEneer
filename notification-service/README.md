# TrackEneer Notification Service

🔔 Standalone Express/TypeScript service for handling Web Push Notifications

## Features

- ✅ Web Push Notifications (VAPID protocol)
- ✅ WebSocket connection to FastAPI backend
- ✅ Real-time notification forwarding
- ✅ Multi-user subscription management
- ✅ Browser notification support
- ✅ Auto-reconnect on WebSocket disconnect
- ✅ TypeScript for type safety
- ✅ RESTful API for subscription management

## Installation

```bash
cd notification-service
npm install
```

## Configuration

### 1. Generate VAPID Keys

```bash
npx web-push generate-vapid-keys
```

### 2. Create `.env` file

```bash
cp .env.example .env
```

### 3. Update `.env` with your VAPID keys

```env
PORT=3001
BACKEND_URL=http://127.0.0.1:5000
BACKEND_WS_URL=ws://127.0.0.1:5000/ws/notifications

VAPID_PUBLIC_KEY=your_generated_public_key
VAPID_PRIVATE_KEY=your_generated_private_key
VAPID_SUBJECT=mailto:your-email@example.com

ALLOWED_ORIGINS=http://localhost:3000,http://localhost:3001
```

## Running the Service

### Development Mode (with auto-reload)

```bash
npm run dev
```

### Production Mode

```bash
npm run build
npm start
```

## API Endpoints

### Health Check
```http
GET /health
```

Response:
```json
{
  "status": "ok",
  "service": "TrackEneer Notification Service",
  "uptime": 1234.56,
  "timestamp": "2025-10-01T12:00:00.000Z",
  "websocketConnected": true
}
```

### Get VAPID Public Key
```http
GET /vapid-public-key
```

Response:
```json
{
  "publicKey": "BHyG..."
}
```

### Subscribe to Notifications
```http
POST /subscribe
Content-Type: application/json

{
  "subscription": {
    "endpoint": "https://fcm.googleapis.com/fcm/send/...",
    "keys": {
      "p256dh": "...",
      "auth": "..."
    }
  },
  "userId": "user@example.com"
}
```

Response:
```json
{
  "success": true,
  "message": "Subscription added successfully",
  "userId": "user@example.com"
}
```

### Unsubscribe
```http
POST /unsubscribe
Content-Type: application/json

{
  "endpoint": "https://fcm.googleapis.com/fcm/send/...",
  "userId": "user@example.com"
}
```

### Send Test Notification
```http
POST /send-test-notification
Content-Type: application/json

{
  "userId": "user@example.com"
}
```

### Get Statistics
```http
GET /stats
```

Response:
```json
{
  "totalUsers": 5,
  "totalSubscriptions": 8,
  "websocketConnected": true,
  "uptime": 1234.56
}
```

## Frontend Integration

### 1. Copy Service Worker to Next.js Public Folder

```bash
cp public/sw.js ../client/public/sw.js
```

### 2. Register Service Worker in Your Next.js App

```javascript
// In your component or useEffect
async function setupNotifications() {
  // Check browser support
  if (!('serviceWorker' in navigator) || !('PushManager' in window)) {
    console.warn('Push notifications not supported');
    return;
  }

  try {
    // Register service worker
    const registration = await navigator.serviceWorker.register('/sw.js');
    console.log('Service Worker registered:', registration);

    // Request notification permission
    const permission = await Notification.requestPermission();
    if (permission !== 'granted') {
      console.log('Notification permission denied');
      return;
    }

    // Get VAPID public key from notification service
    const response = await fetch('http://localhost:3001/vapid-public-key');
    const { publicKey } = await response.json();

    // Subscribe to push notifications
    const subscription = await registration.pushManager.subscribe({
      userVisibleOnly: true,
      applicationServerKey: urlBase64ToUint8Array(publicKey)
    });

    // Send subscription to notification service
    await fetch('http://localhost:3001/subscribe', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        subscription,
        userId: 'user@example.com' // Use actual user ID
      })
    });

    console.log('✅ Push notifications enabled!');
  } catch (error) {
    console.error('Failed to setup notifications:', error);
  }
}

// Helper function
function urlBase64ToUint8Array(base64String) {
  const padding = '='.repeat((4 - base64String.length % 4) % 4);
  const base64 = (base64String + padding)
    .replace(/\\-/g, '+')
    .replace(/_/g, '/');
  const rawData = window.atob(base64);
  return Uint8Array.from([...rawData].map(char => char.charCodeAt(0)));
}
```

### 3. Create a React Hook for Notifications

```typescript
// hooks/useNotifications.ts
import { useEffect, useState } from 'react';

export function useNotifications(userId: string) {
  const [isSubscribed, setIsSubscribed] = useState(false);
  const [publicKey, setPublicKey] = useState<string | null>(null);

  useEffect(() => {
    fetchPublicKey();
  }, []);

  const fetchPublicKey = async () => {
    try {
      const response = await fetch('http://localhost:3001/vapid-public-key');
      const { publicKey } = await response.json();
      setPublicKey(publicKey);
    } catch (error) {
      console.error('Failed to fetch VAPID key:', error);
    }
  };

  const subscribe = async () => {
    if (!publicKey) return;

    try {
      const registration = await navigator.serviceWorker.register('/sw.js');
      const permission = await Notification.requestPermission();
      
      if (permission !== 'granted') {
        throw new Error('Permission denied');
      }

      const subscription = await registration.pushManager.subscribe({
        userVisibleOnly: true,
        applicationServerKey: urlBase64ToUint8Array(publicKey)
      });

      await fetch('http://localhost:3001/subscribe', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ subscription, userId })
      });

      setIsSubscribed(true);
    } catch (error) {
      console.error('Failed to subscribe:', error);
    }
  };

  const unsubscribe = async () => {
    try {
      const registration = await navigator.serviceWorker.getRegistration();
      const subscription = await registration?.pushManager.getSubscription();
      
      if (subscription) {
        await fetch('http://localhost:3001/unsubscribe', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ 
            endpoint: subscription.endpoint, 
            userId 
          })
        });
        
        await subscription.unsubscribe();
        setIsSubscribed(false);
      }
    } catch (error) {
      console.error('Failed to unsubscribe:', error);
    }
  };

  return { isSubscribed, subscribe, unsubscribe };
}

function urlBase64ToUint8Array(base64String: string): Uint8Array {
  const padding = '='.repeat((4 - base64String.length % 4) % 4);
  const base64 = (base64String + padding)
    .replace(/\\-/g, '+')
    .replace(/_/g, '/');
  const rawData = window.atob(base64);
  return Uint8Array.from([...rawData].map(char => char.charCodeAt(0)));
}
```

## Architecture

```
┌─────────────────────┐
│  FastAPI Backend    │
│  (scheduler.py)     │
│  Port: 5000         │
└──────────┬──────────┘
           │ WebSocket
           │ /ws/notifications
           │
           ▼
┌─────────────────────┐
│ Notification Service│
│ (Express/TypeScript)│
│  Port: 3001         │
└──────────┬──────────┘
           │ Web Push
           │ (VAPID)
           │
           ▼
┌─────────────────────┐
│  Next.js Frontend   │
│  Service Worker     │
│  Port: 3000         │
└─────────────────────┘
           │
           ▼
┌─────────────────────┐
│ Browser Notification│
│  (Native OS)        │
└─────────────────────┘
```

## Notification Flow

1. **Backend Event**: Task added/started/ended/due in FastAPI
2. **WebSocket Push**: Backend sends notification via WebSocket
3. **Notification Service**: Receives WebSocket message
4. **Web Push**: Service sends push notification to all subscribed browsers
5. **Service Worker**: Browser service worker receives push
6. **Native Notification**: OS displays notification (like in your screenshot)

## Notification Types

The service handles these notification types from the backend:

- `task_added` - ✅ New Task Added
- `task_start` - 🚀 Time to Start!
- `task_end` - 🏁 Task Ending Now!
- `task_due` - ⏰ Task Due!

## Testing

### Test Notification Flow

1. Start the backend:
```bash
cd server
python scheduler.py
```

2. Start the notification service:
```bash
cd notification-service
npm run dev
```

3. In another terminal, subscribe and test:
```bash
curl -X POST http://localhost:3001/send-test-notification \\
  -H "Content-Type: application/json" \\
  -d '{"userId": "test@example.com"}'
```

## Troubleshooting

### Service Worker Not Registering

- Ensure you're using HTTPS or localhost
- Check browser console for errors
- Verify service worker file is in `/public/sw.js`

### Notifications Not Appearing

1. Check browser notification permissions
2. Verify VAPID keys are correctly configured
3. Check notification service logs
4. Test with `/send-test-notification` endpoint

### WebSocket Connection Issues

- Ensure backend is running on port 5000
- Check `BACKEND_WS_URL` in `.env`
- Look for connection errors in service logs

## Browser Support

- ✅ Chrome/Edge 90+
- ✅ Firefox 78+
- ✅ Safari 16+ (macOS 13+)
- ✅ Opera 76+
- ❌ IE (not supported)

## Production Deployment

### Environment Variables

Set these in your production environment:

```env
NODE_ENV=production
PORT=3001
BACKEND_WS_URL=wss://your-backend.com/ws/notifications
VAPID_PUBLIC_KEY=...
VAPID_PRIVATE_KEY=...
VAPID_SUBJECT=mailto:support@yourdomain.com
ALLOWED_ORIGINS=https://yourdomain.com
```

### SSL/TLS

Web Push requires HTTPS in production. Use a reverse proxy like Nginx or deploy to platforms that provide SSL:

- Vercel
- Netlify
- Railway
- Render
- Heroku

## License

MIT

---

**Made with ❤️ for TrackEneer**
