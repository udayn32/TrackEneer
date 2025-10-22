# Examples - Reference Only

⚠️ **Important**: These files are **examples for reference only**. They are NOT compiled as part of the notification service.

## NotificationButton.tsx

React/TypeScript component for enabling/disabling push notifications.

### Usage

**1. Copy to your Next.js/React project:**
```bash
# Copy to your components folder
cp examples/NotificationButton.tsx ../client/components/NotificationButton.tsx
```

**2. Install dependencies in your Next.js project:**
```bash
cd ../client
npm install lucide-react
```

**3. Use in your app:**
```tsx
import NotificationButton from '@/components/NotificationButton';

export default function MyApp() {
  return (
    <div>
      <NotificationButton userId="user@example.com" />
    </div>
  );
}
```

## Why TypeScript Errors?

These example files show TypeScript errors because:
- `react` is not installed in notification-service (it's a backend service)
- `lucide-react` is not needed for the backend
- These are meant to be copied to your frontend project

## What's Actually Compiled?

Only files in `src/` are compiled:
- ✅ `src/index.ts` - Main Express server
- ✅ `src/services/NotificationService.ts` - Notification logic
- ✅ `src/services/WebSocketClient.ts` - Backend connection
- ✅ `src/services/SubscriptionManager.ts` - Subscription management

The `examples/` folder is excluded from compilation (see `tsconfig.json`).

## Integration Guide

See the main [README.md](../README.md) for full integration instructions.
