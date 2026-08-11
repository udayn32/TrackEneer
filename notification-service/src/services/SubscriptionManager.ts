import { PushSubscription } from 'web-push';

export class SubscriptionManager {
  private subscriptions: Map<string, PushSubscription[]>;

  constructor() {
    this.subscriptions = new Map();
  }

  addSubscription(userId: string, subscription: PushSubscription): void {
    const userSubs = this.subscriptions.get(userId) || [];
    
    // Check if subscription already exists
    const exists = userSubs.some(
      sub => sub.endpoint === subscription.endpoint
    );
    
    if (!exists) {
      userSubs.push(subscription);
      this.subscriptions.set(userId, userSubs);
      console.log(`➕ Added subscription for user: ${userId}`);
    } else {
      console.log(`ℹ️  Subscription already exists for user: ${userId}`);
    }
  }

  removeSubscription(userId: string, endpoint: string): void {
    const userSubs = this.subscriptions.get(userId);
    
    if (userSubs) {
      const filtered = userSubs.filter(sub => sub.endpoint !== endpoint);
      
      if (filtered.length < userSubs.length) {
        this.subscriptions.set(userId, filtered);
        console.log(`➖ Removed subscription for user: ${userId}`);
        
        // Remove user entry if no subscriptions left
        if (filtered.length === 0) {
          this.subscriptions.delete(userId);
        }
      }
    }
  }

  getSubscriptions(userId: string): PushSubscription[] {
    return this.subscriptions.get(userId) || [];
  }

  getAllUserIds(): string[] {
    return Array.from(this.subscriptions.keys());
  }

  getStats(): { totalUsers: number; totalSubscriptions: number } {
    let totalSubscriptions = 0;
    
    this.subscriptions.forEach(subs => {
      totalSubscriptions += subs.length;
    });
    
    return {
      totalUsers: this.subscriptions.size,
      totalSubscriptions
    };
  }

  clearUser(userId: string): void {
    this.subscriptions.delete(userId);
    console.log(`🗑️  Cleared all subscriptions for user: ${userId}`);
  }

  clearAll(): void {
    this.subscriptions.clear();
    console.log('🗑️  Cleared all subscriptions');
  }
}
