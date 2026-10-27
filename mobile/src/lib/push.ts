/**
 * Push notifications on this phone (Expo Push Service).
 *
 * Needs a development or store build linked to an EAS project (extra.eas.projectId in the app
 * config): Expo Go on Android cannot receive remote pushes since SDK 53, and the web has none.
 * Everything here fails softly: without push the inbox and email still work.
 */
import Constants from 'expo-constants';
import * as Device from 'expo-device';
import { isRunningInExpoGo } from 'expo';
import * as SecureStore from 'expo-secure-store';
import { Platform } from 'react-native';

import { registerPushToken, removePushToken } from '@/services/notifications';

const TOKEN_KEY = 'push.expoToken';

function loadNotifications(): typeof import('expo-notifications') {
  // Expo Go may not include this native module, so keep its require behind runtime checks.
  // eslint-disable-next-line @typescript-eslint/no-require-imports
  return require('expo-notifications') as typeof import('expo-notifications');
}

export type PushSetup =
  | { status: 'registered' }
  | { status: 'denied' }
  | { status: 'unsupported'; reason: string };

function projectId(): string | undefined {
  return (Constants.expoConfig?.extra?.eas as { projectId?: string } | undefined)?.projectId ?? Constants.easConfig?.projectId;
}

/** Why push cannot work here, or null if it can. */
export function pushUnavailableReason(): string | null {
  if (Platform.OS === 'web') return 'Push notifications are only available in the phone app.';
  if (isRunningInExpoGo()) return 'Push notifications need a development or store build of the app (not Expo Go).';
  if (!Device.isDevice) return 'Push notifications need a real phone, not a simulator.';
  if (!projectId()) return 'Push notifications need a development or store build of the app (not Expo Go).';
  return null;
}

/**
 * Registers this phone for push. With `ask`, the system permission prompt may be shown;
 * without it, only an already-granted permission is used (silent refresh after sign-in).
 */
export async function setUpPush({ ask }: { ask: boolean }): Promise<PushSetup> {
  const reason = pushUnavailableReason();
  if (reason) return { status: 'unsupported', reason };
  try {
    const Notifications = loadNotifications();
    let permission = await Notifications.getPermissionsAsync();
    if (!permission.granted && ask && permission.canAskAgain) {
      permission = await Notifications.requestPermissionsAsync();
    }
    if (!permission.granted) return { status: 'denied' };
    if (Platform.OS === 'android') {
      await Notifications.setNotificationChannelAsync('default', {
        name: 'Bookings and deliveries',
        importance: Notifications.AndroidImportance.HIGH,
      });
    }
    const { data: token } = await Notifications.getExpoPushTokenAsync({ projectId: projectId() });
    await registerPushToken(token, Platform.OS);
    await SecureStore.setItemAsync(TOKEN_KEY, token);
    return { status: 'registered' };
  } catch (error) {
    return { status: 'unsupported', reason: error instanceof Error ? error.message : 'Push could not be set up.' };
  }
}

/** Before signing out: stop pushes to this phone for this account. Never blocks sign-out. */
export async function forgetPushToken(): Promise<void> {
  try {
    const token = await SecureStore.getItemAsync(TOKEN_KEY);
    if (token) {
      await removePushToken(token);
      await SecureStore.deleteItemAsync(TOKEN_KEY);
    }
  } catch {
    // Offline or already signed out: the token is replaced at the next sign-in anyway.
  }
}

/** Show notifications while the app is open, too. */
export function configureForegroundNotifications(): void {
  if (Platform.OS === 'web' || isRunningInExpoGo()) return;
  try {
    const Notifications = loadNotifications();
    Notifications.setNotificationHandler({
      handleNotification: async () => ({
        shouldShowBanner: true,
        shouldShowList: true,
        shouldPlaySound: false,
        shouldSetBadge: false,
      }),
    });
  } catch (error) {
    console.warn('Could not configure foreground notifications. Rebuild the app to include expo-notifications.', error);
  }
}
