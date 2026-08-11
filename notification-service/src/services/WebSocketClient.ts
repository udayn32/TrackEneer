import WebSocket from 'ws';
import { NotificationService } from './NotificationService';

export class WebSocketClient {
  private ws: WebSocket | null = null;
  private notificationService: NotificationService;
  private reconnectInterval: number = 5000;
  private reconnectTimer: NodeJS.Timeout | null = null;
  private backendUrl: string;

  constructor(notificationService: NotificationService) {
    this.notificationService = notificationService;
    this.backendUrl = process.env.BACKEND_WS_URL || 'ws://127.0.0.1:5000/ws/notifications';
  }

  connect(): void {
    try {
      console.log(`🔌 Connecting to backend WebSocket: ${this.backendUrl}`);
      this.ws = new WebSocket(this.backendUrl);

      this.ws.on('open', () => {
        console.log('✅ Connected to backend WebSocket');
        this.ws?.send('ready');
        
        // Clear any existing reconnect timer
        if (this.reconnectTimer) {
          clearTimeout(this.reconnectTimer);
          this.reconnectTimer = null;
        }
      });

      this.ws.on('message', async (data: Buffer) => {
        try {
          const message = JSON.parse(data.toString());
          console.log('📨 Received from backend:', message);
          
          // Forward notification to all subscribed clients
          await this.notificationService.handleBackendNotification(message);
        } catch (error) {
          console.error('Error processing message:', error);
        }
      });

      this.ws.on('error', (error: any) => {
        console.error('❌ WebSocket error:', error.message);
      });

      this.ws.on('close', () => {
        console.log('🔌 WebSocket disconnected');
        this.ws = null;
        
        // Attempt to reconnect
        this.scheduleReconnect();
      });
    } catch (error) {
      console.error('Failed to connect to WebSocket:', error);
      this.scheduleReconnect();
    }
  }

  private scheduleReconnect(): void {
    if (this.reconnectTimer) {
      return; // Already scheduled
    }

    console.log(`🔄 Scheduling reconnect in ${this.reconnectInterval / 1000}s...`);
    this.reconnectTimer = setTimeout(() => {
      this.reconnectTimer = null;
      this.connect();
    }, this.reconnectInterval);
  }

  disconnect(): void {
    if (this.reconnectTimer) {
      clearTimeout(this.reconnectTimer);
      this.reconnectTimer = null;
    }

    if (this.ws) {
      this.ws.close();
      this.ws = null;
    }
  }

  isConnected(): boolean {
    return this.ws !== null && this.ws.readyState === WebSocket.OPEN;
  }
}
