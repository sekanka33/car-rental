import { isRunningInExpoGo } from 'expo';
import { router } from 'expo-router';
import { useEffect } from 'react';
import { Platform } from 'react-native';

import type * as Notifications from 'expo-notifications';

/** Only paths inside the app (e.g. /bookings/123) are followed; anything else is ignored. */
export function safeAppPath(link: unknown): string | null {
  return typeof link === 'string' && /^\/[A-Za-z0-9/_-]*$/.test(link) ? link : null;
}

function open(response: Notifications.NotificationResponse | null) {
  const path = safeAppPath(response?.notification.request.content.data?.link);
  if (path) router.push(path as never);
}

function loadNotifications(): typeof import('expo-notifications') {
  // Expo Go may not include this native module, so keep its require behind the runtime check.
  // eslint-disable-next-line @typescript-eslint/no-require-imports
  return require('expo-notifications') as typeof import('expo-notifications');
}

/** Tapping a push notification opens the screen it is about (also when it started the app). */
export function useNotificationLinks() {
  useEffect(() => {
    if (Platform.OS === 'web' || isRunningInExpoGo()) return;
    try {
      const Notifications = loadNotifications();
      open(Notifications.getLastNotificationResponse());
      const subscription = Notifications.addNotificationResponseReceivedListener(open);
      return () => subscription.remove();
    } catch (error) {
      console.warn('Could not load notification links. Rebuild the app to include expo-notifications.', error);
    }
  }, []);
}
