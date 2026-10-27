import { fireEvent, render, screen } from '@testing-library/react-native';
import { SafeAreaProvider } from 'react-native-safe-area-context';

import NotificationsScreen from '@/app/notifications';
import { useAuth } from '@/context/auth';
import { safeAppPath } from '@/hooks/use-notification-links';
import { configureForegroundNotifications, forgetPushToken, setUpPush } from '@/lib/push';
import * as notificationsService from '@/services/notifications';

jest.mock('@/context/auth', () => ({ useAuth: jest.fn() }));
jest.mock('@/services/notifications', () => ({
  getInbox: jest.fn(),
  getPreferences: jest.fn(),
  setPreferences: jest.fn(),
  markRead: jest.fn(),
  markAllRead: jest.fn(),
  registerPushToken: jest.fn(),
  removePushToken: jest.fn(),
}));
jest.mock('expo-router', () => ({
  Stack: { Screen: () => null },
  router: { push: jest.fn() },
}));
jest.mock('expo', () => ({ isRunningInExpoGo: jest.fn(() => false) }));
jest.mock('expo-device', () => ({ isDevice: true }));
jest.mock('expo-constants', () => ({ __esModule: true, default: { expoConfig: { extra: { eas: { projectId: 'proj-1' } } } } }));
jest.mock('expo-notifications', () => ({
  __esModule: true,
  getPermissionsAsync: jest.fn(),
  requestPermissionsAsync: jest.fn(),
  setNotificationChannelAsync: jest.fn(),
  getExpoPushTokenAsync: jest.fn(async () => ({ data: 'ExponentPushToken[device-1-abcdefgh]' })),
  setNotificationHandler: jest.fn(),
  AndroidImportance: { HIGH: 4 },
}));

const mockRouter = jest.requireMock('expo-router').router as { push: jest.Mock };
const mockIsRunningInExpoGo = jest.requireMock('expo').isRunningInExpoGo as jest.Mock;
const Notifications = jest.requireMock('expo-notifications') as Record<string, jest.Mock>;
const service = notificationsService as unknown as Record<string, jest.Mock>;
const METRICS = { frame: { x: 0, y: 0, width: 390, height: 844 }, insets: { top: 0, left: 0, right: 0, bottom: 0 } };
const wrap = (ui: React.ReactElement) => render(<SafeAreaProvider initialMetrics={METRICS}>{ui}</SafeAreaProvider>);

const item = (id: string, read: boolean, link: string | null = `/bookings/${id}`) => ({
  id,
  event: 'booking.confirmed',
  title: `Booking ${id} confirmed`,
  body: 'We received your payment.',
  link,
  created_at: '2026-10-15T08:00:00Z',
  read_at: read ? '2026-10-15T09:00:00Z' : null,
});

beforeEach(() => {
  mockIsRunningInExpoGo.mockReturnValue(false);
  (useAuth as jest.Mock).mockReturnValue({ state: { status: 'signedIn', user: { id: 'u1', roles: ['RENTER'] } } });
  service.getPreferences.mockResolvedValue({ email_enabled: true, push_enabled: true, note: 'Payment receipts, refunds and cancellations are always emailed.' });
});

describe('links from notifications', () => {
  it('only follows paths inside the app', () => {
    expect(safeAppPath('/bookings/123')).toBe('/bookings/123');
    expect(safeAppPath('/owner/vehicles/a-b_c')).toBe('/owner/vehicles/a-b_c');
    for (const bad of ['https://evil.example', '//evil.example', 'javascript:alert(1)', '/bookings/1?x=<script>', 42, null]) {
      expect(safeAppPath(bad)).toBeNull();
    }
  });
});

describe('inbox', () => {
  it('shows unread first-class, marks read and opens the linked screen', async () => {
    service.getInbox.mockResolvedValue({ items: [item('b1', false), item('b2', true)], unread: 1 });
    service.markRead.mockResolvedValue({});
    await wrap(<NotificationsScreen />);

    await fireEvent.press(await screen.findByLabelText('Unread: Booking b1 confirmed'));
    expect(service.markRead).toHaveBeenCalledWith('b1');
    expect(mockRouter.push).toHaveBeenCalledWith('/bookings/b1');

    await fireEvent.press(screen.getByLabelText('Booking b2 confirmed'));
    expect(service.markRead).toHaveBeenCalledTimes(1); // already read
  });

  it('marks everything read', async () => {
    service.getInbox.mockResolvedValue({ items: [item('b1', false), item('b3', false)], unread: 2 });
    await wrap(<NotificationsScreen />);
    await fireEvent.press(await screen.findByText('Mark all 2 as read'));
    expect(service.markAllRead).toHaveBeenCalled();
  });

  it('explains an empty inbox and that essential emails always go out', async () => {
    service.getInbox.mockResolvedValue({ items: [], unread: 0 });
    await wrap(<NotificationsScreen />);
    expect(await screen.findByText('Nothing yet')).toBeTruthy();
    expect(await screen.findByText(/always emailed/)).toBeTruthy();
  });

  it('saves the email choice', async () => {
    service.getInbox.mockResolvedValue({ items: [], unread: 0 });
    service.setPreferences.mockResolvedValue({ email_enabled: false, push_enabled: true, note: 'n' });
    await wrap(<NotificationsScreen />);
    await fireEvent(await screen.findByLabelText('Email notifications'), 'valueChange', false);
    expect(service.setPreferences).toHaveBeenCalledWith({ email_enabled: false });
  });
});

describe('push setup', () => {
  it('does not load push notifications in Expo Go', async () => {
    mockIsRunningInExpoGo.mockReturnValue(true);
    configureForegroundNotifications();
    await expect(setUpPush({ ask: true })).resolves.toEqual({
      status: 'unsupported',
      reason: 'Push notifications need a development or store build of the app (not Expo Go).',
    });
    expect(Notifications.getPermissionsAsync).not.toHaveBeenCalled();
    expect(Notifications.setNotificationHandler).not.toHaveBeenCalled();
  });

  it('registers the token when permission is granted', async () => {
    Notifications.getPermissionsAsync.mockResolvedValue({ granted: true, canAskAgain: true });
    await expect(setUpPush({ ask: false })).resolves.toEqual({ status: 'registered' });
    expect(service.registerPushToken).toHaveBeenCalledWith('ExponentPushToken[device-1-abcdefgh]', expect.any(String));
    expect(Notifications.getExpoPushTokenAsync).toHaveBeenCalledWith({ projectId: 'proj-1' });
  });

  it('never prompts at sign-in, only when asked', async () => {
    Notifications.getPermissionsAsync.mockResolvedValue({ granted: false, canAskAgain: true });
    Notifications.requestPermissionsAsync.mockResolvedValue({ granted: false, canAskAgain: false });

    await expect(setUpPush({ ask: false })).resolves.toEqual({ status: 'denied' });
    expect(Notifications.requestPermissionsAsync).not.toHaveBeenCalled();

    await expect(setUpPush({ ask: true })).resolves.toEqual({ status: 'denied' });
    expect(Notifications.requestPermissionsAsync).toHaveBeenCalledTimes(1);
    expect(service.registerPushToken).not.toHaveBeenCalled();
  });

  it('fails softly when the build cannot receive push', async () => {
    Notifications.getPermissionsAsync.mockResolvedValue({ granted: true, canAskAgain: true });
    Notifications.getExpoPushTokenAsync.mockRejectedValueOnce(new Error('No projectId found'));
    await expect(setUpPush({ ask: true })).resolves.toEqual({ status: 'unsupported', reason: 'No projectId found' });
  });

  it('forgets the token on sign-out, even when offline', async () => {
    Notifications.getPermissionsAsync.mockResolvedValue({ granted: true, canAskAgain: true });
    await setUpPush({ ask: false });
    service.removePushToken.mockRejectedValueOnce(new Error('offline'));
    await expect(forgetPushToken()).resolves.toBeUndefined();
    service.removePushToken.mockResolvedValueOnce(undefined);
    await forgetPushToken();
    expect(service.removePushToken).toHaveBeenLastCalledWith('ExponentPushToken[device-1-abcdefgh]');
  });
});
