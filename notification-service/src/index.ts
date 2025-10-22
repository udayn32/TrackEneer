import express, { Request, Response } from 'express';
import cors from 'cors';
import webPush from 'web-push';
import dotenv from 'dotenv';
import { NotificationService } from './services/NotificationService';
import { WebSocketClient } from './services/WebSocketClient';
import { SubscriptionManager } from './services/SubscriptionManager';

// Load environment variables
dotenv.config();

const app = express();
const PORT = process.env.PORT || 3001;

// Middleware
app.use(cors({
  origin: process.env.ALLOWED_ORIGINS?.split(',') || ['http://localhost:3000'],
  credentials: true
}));
app.use(express.json());

// Initialize services
const subscriptionManager = new SubscriptionManager();
const notificationService = new NotificationService(subscriptionManager);
const wsClient = new WebSocketClient(notificationService);

// Setup Web Push
if (process.env.VAPID_PUBLIC_KEY && process.env.VAPID_PRIVATE_KEY) {
  webPush.setVapidDetails(
    process.env.VAPID_SUBJECT || 'mailto:support@trackeneer.com',
    process.env.VAPID_PUBLIC_KEY,
    process.env.VAPID_PRIVATE_KEY
  );
  console.log('✅ Web Push configured with VAPID keys');
} else {
  console.warn('⚠️  VAPID keys not configured. Generate them with: npx web-push generate-vapid-keys');
}

// Helper function to get IST time
function getISTTime() {
  return new Date().toLocaleString('en-IN', { 
    timeZone: 'Asia/Kolkata',
    year: 'numeric',
    month: '2-digit',
    day: '2-digit',
    hour: '2-digit',
    minute: '2-digit',
    second: '2-digit',
    hour12: true
  });
}

// Routes
app.get('/health', (_req: Request, res: Response) => {
  res.json({
    status: 'ok',
    service: 'TrackEneer Notification Service',
    uptime: process.uptime(),
    timestamp: new Date().toISOString(),
    timestampIST: getISTTime(),
    timezone: 'Asia/Kolkata (IST)',
    websocketConnected: wsClient.isConnected()
  });
});

app.get('/vapid-public-key', (_req: Request, res: Response) => {
  res.json({
    publicKey: process.env.VAPID_PUBLIC_KEY || null
  });
});

app.post('/subscribe', async (req: Request, res: Response) => {
  try {
    const { subscription, userId } = req.body;
    
    if (!subscription || !subscription.endpoint) {
      return res.status(400).json({ error: 'Invalid subscription object' });
    }

    subscriptionManager.addSubscription(userId || 'anonymous', subscription);

    // Try to send a welcome notification but do not fail the HTTP request if push fails
    (async () => {
      try {
        await notificationService.sendNotification(subscription, {
          title: '🔔 Notifications Enabled',
          body: 'You will now receive real-time task notifications',
          icon: '/icon.png',
          badge: '/badge.png',
          tag: 'welcome'
        }, userId || 'anonymous');
      } catch (err) {
        console.warn('Welcome notification failed (subscription stored):', err?.message || err);
      }
    })();

    res.json({ 
      success: true, 
      message: 'Subscription added successfully',
      userId 
    });
  } catch (error) {
    console.error('Error adding subscription:', error);
    res.status(500).json({ error: 'Failed to add subscription' });
  }
});

app.post('/unsubscribe', (req: Request, res: Response) => {
  try {
    const { endpoint, userId } = req.body;
    
    if (!endpoint) {
      return res.status(400).json({ error: 'Endpoint is required' });
    }

    subscriptionManager.removeSubscription(userId || 'anonymous', endpoint);
    
    res.json({ 
      success: true, 
      message: 'Subscription removed successfully' 
    });
  } catch (error) {
    console.error('Error removing subscription:', error);
    res.status(500).json({ error: 'Failed to remove subscription' });
  }
});

app.post('/send-test-notification', async (req: Request, res: Response) => {
  try {
    const { userId } = req.body;
    const subscriptions = subscriptionManager.getSubscriptions(userId || 'anonymous');
    
    if (subscriptions.length === 0) {
      return res.status(404).json({ error: 'No subscriptions found for user' });
    }

    const results = await Promise.allSettled(
      subscriptions.map(sub => 
        notificationService.sendNotification(sub, {
          title: '🧪 Test Notification',
          body: 'This is a test notification from TrackEneer',
          icon: '/icon.png',
          tag: 'test'
        })
      )
    );

    const successful = results.filter(r => r.status === 'fulfilled').length;
    
    res.json({ 
      success: true, 
      sent: successful,
      total: subscriptions.length 
    });
  } catch (error) {
    console.error('Error sending test notification:', error);
    res.status(500).json({ error: 'Failed to send test notification' });
  }
});

app.get('/stats', (_req: Request, res: Response) => {
  const stats = subscriptionManager.getStats();
  res.json({
    ...stats,
    websocketConnected: wsClient.isConnected(),
    uptime: process.uptime()
  });
});

// Start server
app.listen(PORT, () => {
  console.log('\n' + '='.repeat(60));
  console.log('  🔔 TrackEneer Notification Service');
  console.log('='.repeat(60));
  console.log(`📍 Server running on http://localhost:${PORT}`);
  console.log(`🔌 Connecting to backend: ${process.env.BACKEND_WS_URL}`);
  console.log('='.repeat(60) + '\n');
  
  // Connect to backend WebSocket
  wsClient.connect();
});

// Graceful shutdown
process.on('SIGTERM', () => {
  console.log('SIGTERM received, shutting down gracefully...');
  wsClient.disconnect();
  process.exit(0);
});

process.on('SIGINT', () => {
  console.log('\nSIGINT received, shutting down gracefully...');
  wsClient.disconnect();
  process.exit(0);
});

export default app;
