import webPush, { PushSubscription } from 'web-push';
import { SubscriptionManager } from './SubscriptionManager';

export interface NotificationPayload {
  title: string;
  body: string;
  icon?: string;
  badge?: string;
  tag?: string;
  data?: any;
  requireInteraction?: boolean;
  vibrate?: number[];
}

export class NotificationService {
  private subscriptionManager: SubscriptionManager;

  constructor(subscriptionManager: SubscriptionManager) {
    this.subscriptionManager = subscriptionManager;
  }

  async sendNotification(
    subscription: PushSubscription,
    payload: NotificationPayload,
    userId?: string
  ): Promise<void> {
    try {
      const notificationPayload = JSON.stringify({
        title: payload.title,
        body: payload.body,
        icon: payload.icon || '/icon.png',
        badge: payload.badge || '/badge.png',
        tag: payload.tag || 'default',
        data: payload.data || {},
        requireInteraction: payload.requireInteraction || false,
        vibrate: payload.vibrate || [200, 100, 200]
      });

      await webPush.sendNotification(subscription, notificationPayload);
      console.log(`✅ Notification sent: ${payload.title}`);
    } catch (error: any) {
      console.error(`❌ Failed to send notification: ${error.message}`);

      if ((error.statusCode === 410 || error.statusCode === 404) && userId) {
        console.log(`🗑️  Removing invalid subscription for user ${userId}`);
        this.subscriptionManager.removeSubscription(userId, subscription.endpoint);
      }

      throw error;
    }
  }

  async broadcastNotification(
    userId: string,
    payload: NotificationPayload
  ): Promise<{ sent: number; failed: number }> {
    const subscriptions = this.subscriptionManager.getSubscriptions(userId);
    let sent = 0;
    let failed = 0;

    const results = await Promise.allSettled(
      subscriptions.map((sub: PushSubscription) => this.sendNotification(sub, payload, userId))
    );

    results.forEach((result: any) => {
      if (result.status === 'fulfilled') {
        sent++;
      } else {
        failed++;
      }
    });

    console.log(`📊 Broadcast complete: ${sent} sent, ${failed} failed`);
    return { sent, failed };
  }

  async broadcastToAll(payload: NotificationPayload): Promise<void> {
    const allUsers = this.subscriptionManager.getAllUserIds();
    
    console.log(`📢 Broadcasting to ${allUsers.length} users...`);
    
    for (const userId of allUsers) {
      await this.broadcastNotification(userId, payload);
    }
  }

  private formatTimeIST(dateString: string | undefined): string {
    if (!dateString) return 'N/A';
    try {
      const date = new Date(dateString);
      return date.toLocaleString('en-IN', {
        timeZone: 'Asia/Kolkata',
        hour: '2-digit',
        minute: '2-digit',
        hour12: true
      });
    } catch {
      return 'N/A';
    }
  }

  async handleBackendNotification(data: any): Promise<void> {
    try {
      const { type, task } = data;
      
      // Ignore acknowledgment and non-notification messages
      if (type === 'ack' || type === 'ping' || type === 'pong' || !type) {
        return;
      }
      
      let payload: NotificationPayload;

      switch (type) {
        case 'task_added':
          payload = {
            title: '✅ New Task Added',
            body: `${task?.title || 'A new task has been added'}${task?.startTime ? ` at ${this.formatTimeIST(task.startTime)}` : ''}`,
            tag: `task-added-${task?.id}`,
            icon: '/icon.png',
            data: { taskId: task?.id, type: 'task_added', timezone: 'IST' }
          };
          break;

        case 'task_start':
          payload = {
            title: '🚀 Time to Start!',
            body: `${task?.title || 'Your task is starting now'} - ${this.formatTimeIST(task?.startTime)} IST`,
            tag: `task-start-${task?.id}`,
            icon: '/icon.png',
            requireInteraction: true,
            vibrate: [200, 100, 200, 100, 200],
            data: { taskId: task?.id, type: 'task_start', startTime: task?.startTime, timezone: 'IST' }
          };
          break;

        case 'task_end':
          payload = {
            title: '🏁 Task Ending Now!',
            body: `${task?.title || 'Your task time is up'} - ${this.formatTimeIST(task?.endTime)} IST`,
            tag: `task-end-${task?.id}`,
            icon: '/icon.png',
            requireInteraction: true,
            vibrate: [300, 100, 300],
            data: { taskId: task?.id, type: 'task_end', endTime: task?.endTime, timezone: 'IST' }
          };
          break;

        case 'task_due':
          payload = {
            title: '⏰ Task Due!',
            body: `${task?.title || 'A task is due now'} - Due: ${this.formatTimeIST(task?.dueDate)} IST`,
            tag: `task-due-${task?.id}`,
            icon: '/icon.png',
            requireInteraction: true,
            vibrate: [400, 200, 400],
            data: { taskId: task?.id, type: 'task_due', dueDate: task?.dueDate, timezone: 'IST' }
          };
          break;

        default:
          console.log(`ℹ️  Ignoring message type: ${type}`);
          return;
      }

      console.log(`📤 Broadcasting notification: ${payload.title}`);
      await this.broadcastToAll(payload);
    } catch (error) {
      console.error('Error handling backend notification:', error);
    }
  }
}
