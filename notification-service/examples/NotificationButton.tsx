// NotificationButton.tsx
// React component for enabling/disabling notifications
// 
// NOTE: This is an EXAMPLE file for reference only.
// Copy this to your Next.js/React project and install dependencies:
// npm install react lucide-react
//
// This file is NOT compiled with the notification service.
import React, { useState, useEffect } from 'react';
import { Bell, BellOff } from 'lucide-react';

const NOTIFICATION_SERVICE_URL = 'http://localhost:3001';

interface NotificationButtonProps {
  userId: string;
  className?: string;
}

export const NotificationButton: React.FC<NotificationButtonProps> = ({ 
  userId,
  className = ''
}: NotificationButtonProps) => {
  const [isSubscribed, setIsSubscribed] = useState(false);
  const [isLoading, setIsLoading] = useState(false);
  const [publicKey, setPublicKey] = useState<string | null>(null);

  useEffect(() => {
    checkSubscription();
    fetchPublicKey();
  }, []);

  const fetchPublicKey = async () => {
    try {
      const response = await fetch(`${NOTIFICATION_SERVICE_URL}/vapid-public-key`);
      const { publicKey } = await response.json();
      setPublicKey(publicKey);
    } catch (error) {
      console.error('Failed to fetch VAPID key:', error);
    }
  };

  const checkSubscription = async () => {
    try {
      const registration = await navigator.serviceWorker.getRegistration();
      const subscription = await registration?.pushManager.getSubscription();
      setIsSubscribed(!!subscription);
    } catch (error) {
      console.error('Failed to check subscription:', error);
    }
  };

  const urlBase64ToUint8Array = (base64String: string): Uint8Array<ArrayBuffer> => {
    const padding = '='.repeat((4 - base64String.length % 4) % 4);
    const base64 = (base64String + padding)
      .replace(/\-/g, '+')
      .replace(/_/g, '/');
    const rawData = window.atob(base64);
    const outputArray = new Uint8Array(rawData.length);
    for (let i = 0; i < rawData.length; ++i) {
      outputArray[i] = rawData.charCodeAt(i);
    }
    return outputArray;
  };

  const subscribe = async () => {
    if (!publicKey) {
      alert('Public key not available. Please try again.');
      return;
    }

    setIsLoading(true);
    try {
      // Register service worker
      const registration = await navigator.serviceWorker.register('/sw.js');
      await navigator.serviceWorker.ready;

      // Request notification permission
      const permission = await Notification.requestPermission();
      if (permission !== 'granted') {
        alert('Notification permission denied. Please enable in browser settings.');
        return;
      }

      // Subscribe to push notifications
      const subscription = await registration.pushManager.subscribe({
        userVisibleOnly: true,
        applicationServerKey: urlBase64ToUint8Array(publicKey)
      });

      // Send subscription to notification service
      const response = await fetch(`${NOTIFICATION_SERVICE_URL}/subscribe`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ subscription, userId })
      });

      if (response.ok) {
        setIsSubscribed(true);
        console.log('✅ Successfully subscribed to notifications!');
      } else {
        throw new Error('Failed to send subscription to server');
      }
    } catch (error) {
      console.error('Failed to subscribe:', error);
      alert('Failed to enable notifications. Check console for details.');
    } finally {
      setIsLoading(false);
    }
  };

  const unsubscribe = async () => {
    setIsLoading(true);
    try {
      const registration = await navigator.serviceWorker.getRegistration();
      const subscription = await registration?.pushManager.getSubscription();

      if (subscription) {
        // Unsubscribe from push manager
        await subscription.unsubscribe();

        // Remove from notification service
        await fetch(`${NOTIFICATION_SERVICE_URL}/unsubscribe`, {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ 
            endpoint: subscription.endpoint,
            userId 
          })
        });

        setIsSubscribed(false);
        console.log('✅ Successfully unsubscribed from notifications');
      }
    } catch (error) {
      console.error('Failed to unsubscribe:', error);
      alert('Failed to disable notifications. Check console for details.');
    } finally {
      setIsLoading(false);
    }
  };

  const handleToggle = () => {
    if (isSubscribed) {
      unsubscribe();
    } else {
      subscribe();
    }
  };

  return (
    <button
      onClick={handleToggle}
      disabled={isLoading}
      className={`p-2 rounded-lg hover:bg-gray-100 dark:hover:bg-gray-800 transition-colors relative ${className}`}
      title={isSubscribed ? 'Disable notifications' : 'Enable notifications'}
    >
      {isSubscribed ? (
        <Bell size={20} className="text-blue-600" />
      ) : (
        <BellOff size={20} className="text-gray-500" />
      )}
      
      {isSubscribed && (
        <span className="absolute top-0 right-0 w-2 h-2 bg-green-500 rounded-full"></span>
      )}
    </button>
  );
};

export default NotificationButton;
