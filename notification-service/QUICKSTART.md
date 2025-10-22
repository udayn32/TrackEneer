# 🚀 Quick Start Guide - TrackEneer Notifications

This guide will help you set up native OS notifications (like the one in your screenshot) for TrackEneer.

## Architecture Overview

```
Backend (Python) → Notification Service (Node.js) → Browser → OS Notification
```

## Step 1: Install Notification Service

```bash
cd C:\Trackeneer\notification-service
npm install
```

## Step 2: Generate VAPID Keys

```bash
npx web-push generate-vapid-keys
```

**Save the output!** You'll see something like:

```
=======================================
Public Key:
BHyGr7qR8...

Private Key:
r5jF3pQ...
=======================================
```

## Step 3: Configure Environment

Create `.env` file:

```bash
cp .env.example .env
```

Edit `.env` and add your VAPID keys:

```env
PORT=3001
NODE_ENV=development

BACKEND_URL=http://127.0.0.1:5000
BACKEND_WS_URL=ws://127.0.0.1:5000/ws/notifications

VAPID_PUBLIC_KEY=BHyGr7qR8...  # Paste your public key here
VAPID_PRIVATE_KEY=r5jF3pQ...    # Paste your private key here
VAPID_SUBJECT=mailto:your-email@example.com

ALLOWED_ORIGINS=http://localhost:3000,http://localhost:3001
```

## Step 4: Copy Service Worker to Frontend

```bash
# Windows PowerShell
Copy-Item public\sw.js ..\client\public\sw.js

# Or manually copy:
# FROM: C:\Trackeneer\notification-service\public\sw.js
# TO:   C:\Trackeneer\client\public\sw.js
```

## Step 5: Start All Services

### Terminal 1: Start Backend
```bash
cd C:\Trackeneer\server
python scheduler.py
```

### Terminal 2: Start Notification Service
```bash
cd C:\Trackeneer\notification-service
npm run dev
```

### Terminal 3: Start Frontend
```bash
cd C:\Trackeneer\client
npm run dev
```

## Step 6: Enable Notifications in Browser

1. Open **http://localhost:3000**
2. Click the **Bell icon** 🔔
3. Allow notifications when prompted
4. You should see: "🔔 Notifications Enabled"

## Step 7: Test Notifications

### Method 1: Add a Task

1. Go to "Add Task" in the app
2. Create a task with:
   - `startTime`: 30 seconds from now
   - `endTime`: 2 minutes from now
3. Wait and watch for notifications!

### Method 2: Use Test Endpoint

```bash
# Open a new terminal
curl -X POST http://localhost:3001/send-test-notification `
  -H "Content-Type: application/json" `
  -d '{\"userId\": \"user@example.com\"}'
```

## Expected Notifications

You should see OS-level notifications (like in your screenshot) for:

1. **✅ New Task Added** - Immediately when you create a task
2. **🚀 Time to Start** - When task startTime arrives  
3. **🏁 Task Ending Now** - When task endTime arrives
4. **⏰ Task Due** - When task dueDate arrives

## Notification Appearance

The notifications will appear:

- **Windows 10/11**: Bottom-right corner (Action Center style)
- **macOS**: Top-right corner
- **Linux**: Depends on desktop environment

Features:
- Icon with app logo
- Title and message body
- Click to view in browser
- Vibration on mobile
- Sound alert

## Troubleshooting

### "Service Worker registration failed"

**Solution**: Make sure `sw.js` is in `client/public/sw.js`

```bash
# Verify file exists
Test-Path C:\Trackeneer\client\public\sw.js
```

### "Notification permission denied"

**Solution**: Reset browser permissions

**Chrome**:
1. Click lock icon in address bar
2. Site Settings → Notifications → Allow

**Edge**:
1. Settings → Cookies and site permissions
2. Notifications → Allow for localhost

### "Cannot connect to notification service"

**Solution**: Check all services are running

```bash
# Check backend
curl http://localhost:5000/api/health

# Check notification service  
curl http://localhost:3001/health

# Check frontend
curl http://localhost:3000
```

### No notifications appearing

1. **Check subscription**:
   ```bash
   curl http://localhost:3001/stats
   ```
   Should show: `"totalSubscriptions": 1` or more

2. **Check browser console** (F12):
   - Look for "✅ Push notifications enabled!"
   - Check for any errors

3. **Check notification service logs**:
   - Should see: "📨 Received from backend:"
   - Should see: "✅ Notification sent:"

4. **Test directly**:
   ```bash
   curl -X POST http://localhost:3001/send-test-notification `
     -H "Content-Type: application/json" `
     -d '{\"userId\": \"anonymous\"}'
   ```

### VAPID keys not working

**Solution**: Regenerate and reconfigure

```bash
npx web-push generate-vapid-keys
```

Update `.env` with new keys and restart notification service.

## Verification Checklist

✅ Backend running on port 5000  
✅ Notification service running on port 3001  
✅ Frontend running on port 3000  
✅ Service worker registered (`/sw.js`)  
✅ Notification permission granted  
✅ Subscribed to notifications (Bell icon active)  
✅ VAPID keys configured in `.env`  
✅ WebSocket connected (check logs)  

## Next Steps

### Production Deployment

For production, you'll need:

1. **HTTPS**: Web Push requires SSL
2. **Valid Domain**: For VAPID subject
3. **Environment Variables**: Set in production hosting
4. **Service Worker**: Hosted on your domain

### Customization

Edit `NotificationService.ts` to customize:

- Notification icons
- Vibration patterns  
- Notification sounds
- Action buttons
- Click behavior

## Advanced Features

### Custom Notification Actions

Edit `public/sw.js`:

```javascript
actions: [
  { action: 'view', title: 'View Task', icon: '/icons/view.png' },
  { action: 'snooze', title: 'Snooze 5m', icon: '/icons/snooze.png' },
  { action: 'dismiss', title: 'Dismiss', icon: '/icons/dismiss.png' }
]
```

### Notification Sounds

Add to notification payload:

```javascript
{
  ...payload,
  silent: false,
  sound: '/sounds/notification.mp3'
}
```

### Badge Count

Update badge count:

```javascript
navigator.setAppBadge(unreadCount);
```

## Support

For issues or questions:

1. Check the logs in all three terminals
2. Review browser console (F12)
3. Check notification service stats: http://localhost:3001/stats
4. Verify WebSocket connection: http://localhost:3001/health

## Files Reference

- `src/index.ts` - Main Express server
- `src/services/NotificationService.ts` - Push notification logic
- `src/services/WebSocketClient.ts` - Backend connection
- `src/services/SubscriptionManager.ts` - User subscriptions
- `public/sw.js` - Service worker for browser
- `examples/NotificationButton.tsx` - React component

---

**You're all set!** 🎉

Create a task and watch the notifications appear like magic! ✨
