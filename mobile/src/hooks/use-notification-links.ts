import * as Notifications from 'expo-notifications';
import { router } from 'expo-router';
import { useEffect } from 'react';
import { Platform } from 'react-native';

/** Only paths inside the app (e.g. /bookings/123) are followed; anything else is ignored. */
export function safeAppPath(link: unknown): string | null {
  return typeof link === 'string' && /^\/[A-Za-z0-9/_-]*$/.test(link) ? link : null;
}

function open(response: Notifications.NotificationResponse | null) {
  const path = safeAppPath(response?.notification.request.content.data?.link);
  if (path) router.push(path as never);
}

/** Tapping a push notification opens the screen it is about (also when it started the app). */
export function useNotificationLinks() {
  useEffect(() => {
    if (Platform.OS === 'web') return;
    open(Notifications.getLastNotificationResponse());
    const subscription = Notifications.addNotificationResponseReceivedListener(open);
    return () => subscription.remove();
  }, []);
}
