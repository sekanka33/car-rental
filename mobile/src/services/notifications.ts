import { apiRequest } from '@/lib/api';
import type { AppNotification, Inbox, NotificationPreferences } from '@/types/notification';

const BASE = '/api/v1/notifications/me';

export function getInbox(limit = 30): Promise<Inbox> {
  return apiRequest<Inbox>('GET', BASE, { auth: true, params: { limit } });
}

export function markRead(id: string): Promise<AppNotification> {
  return apiRequest<AppNotification>('POST', `${BASE}/${encodeURIComponent(id)}/read`, { auth: true });
}

export function markAllRead(): Promise<void> {
  return apiRequest<void>('POST', `${BASE}/read-all`, { auth: true });
}

export function getPreferences(): Promise<NotificationPreferences> {
  return apiRequest<NotificationPreferences>('GET', `${BASE}/preferences`, { auth: true });
}

export function setPreferences(changes: Partial<Pick<NotificationPreferences, 'email_enabled' | 'push_enabled'>>) {
  return apiRequest<NotificationPreferences>('PUT', `${BASE}/preferences`, { auth: true, body: changes });
}

export function registerPushToken(token: string, platform: string): Promise<void> {
  return apiRequest<void>('POST', `${BASE}/push-tokens`, { auth: true, body: { token, platform } });
}

export function removePushToken(token: string): Promise<void> {
  return apiRequest<void>('POST', `${BASE}/push-tokens/remove`, { auth: true, body: { token } });
}
