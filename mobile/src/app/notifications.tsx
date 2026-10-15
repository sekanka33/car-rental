import { router, Stack } from 'expo-router';
import { useCallback, useState } from 'react';
import { Platform, Pressable, RefreshControl, ScrollView, Switch, Text, View } from 'react-native';

import { SectionTitle } from '@/components/dashboard';
import { SignInPrompt } from '@/components/sign-in-prompt';
import { Button } from '@/components/ui/button';
import { Notice } from '@/components/ui/notice';
import { EmptyState, ErrorState, LoadingState } from '@/components/ui/state-views';
import { useAuth } from '@/context/auth';
import { useAsync } from '@/hooks/use-async';
import { safeAppPath } from '@/hooks/use-notification-links';
import { ApiError } from '@/lib/api';
import { formatDateTime } from '@/lib/dates';
import { pushUnavailableReason, setUpPush } from '@/lib/push';
import { getInbox, getPreferences, markAllRead, markRead, setPreferences } from '@/services/notifications';
import type { AppNotification, NotificationPreferences } from '@/types/notification';

function Item({ item, onOpened }: { item: AppNotification; onOpened: () => void }) {
  const unread = item.read_at === null;
  const open = async () => {
    if (unread) {
      try {
        await markRead(item.id);
      } catch {
        // Still open it; it shows as unread until the next refresh.
      }
      onOpened();
    }
    const path = safeAppPath(item.link);
    if (path) router.push(path as never);
  };
  return (
    <Pressable
      accessibilityRole="button"
      accessibilityLabel={`${unread ? 'Unread: ' : ''}${item.title}`}
      onPress={open}
      className={`mb-2 rounded-2xl border p-4 active:opacity-80 ${unread ? 'border-brand-500 bg-brand-50' : 'border-surface-border bg-white'}`}>
      <View className="flex-row items-start">
        {unread ? <View className="mr-2 mt-2 h-2 w-2 rounded-full bg-brand-500" /> : null}
        <View className="flex-1">
          <Text className={`text-base text-ink ${unread ? 'font-bold' : 'font-semibold'}`}>{item.title}</Text>
          <Text className="mt-1 text-sm text-ink-muted">{item.body}</Text>
          <Text className="mt-1 text-xs text-ink-subtle">{formatDateTime(item.created_at)}</Text>
        </View>
      </View>
    </Pressable>
  );
}

function Preferences({ initial }: { initial: NotificationPreferences }) {
  const [prefs, setPrefs] = useState(initial);
  const [message, setMessage] = useState<{ tone: 'info' | 'danger'; text: string } | null>(null);
  const unavailable = pushUnavailableReason();

  const update = async (changes: Partial<NotificationPreferences>) => {
    setMessage(null);
    const previous = prefs;
    setPrefs({ ...prefs, ...changes });
    try {
      setPrefs(await setPreferences(changes));
    } catch (e) {
      setPrefs(previous);
      setMessage({ tone: 'danger', text: e instanceof ApiError ? e.message : 'Could not save your choice.' });
    }
  };

  const togglePush = async (on: boolean) => {
    if (on && Platform.OS !== 'web') {
      const result = await setUpPush({ ask: true });
      if (result.status === 'denied') {
        setMessage({ tone: 'info', text: 'Allow notifications for CarHire SA in your phone settings to get them here.' });
      } else if (result.status === 'unsupported') {
        setMessage({ tone: 'info', text: result.reason });
      }
    }
    await update({ push_enabled: on });
  };

  return (
    <>
      <SectionTitle title="How we contact you" />
      <View className="rounded-2xl border border-surface-border bg-white px-4">
        <View className="flex-row items-center justify-between py-3">
          <Text className="flex-1 pr-3 text-base text-ink">Email</Text>
          <Switch accessibilityLabel="Email notifications" value={prefs.email_enabled} onValueChange={(on) => update({ email_enabled: on })} />
        </View>
        <View className="flex-row items-center justify-between border-t border-surface-border py-3">
          <Text className="flex-1 pr-3 text-base text-ink">Push notifications on your phone</Text>
          <Switch accessibilityLabel="Push notifications" value={prefs.push_enabled} onValueChange={togglePush} />
        </View>
      </View>
      <Text className="mt-2 text-sm text-ink-muted">{prefs.note}</Text>
      {unavailable && prefs.push_enabled ? <Text className="mt-1 text-sm text-ink-muted">{unavailable}</Text> : null}
      {message ? (
        <View className="mt-3">
          <Notice tone={message.tone} message={message.text} />
        </View>
      ) : null}
    </>
  );
}

function Inbox() {
  const loadInbox = useCallback(() => getInbox(50), []);
  const inbox = useAsync(loadInbox);
  const prefs = useAsync(getPreferences);
  const [busy, setBusy] = useState(false);

  if (inbox.status === 'loading') return <LoadingState />;
  if (inbox.status === 'error') return <ErrorState message={inbox.error.message} onAction={inbox.reload} />;

  return (
    <ScrollView className="flex-1 bg-surface-muted" contentContainerClassName="p-5 pb-10" refreshControl={<RefreshControl refreshing={false} onRefresh={inbox.reload} />}>
      {inbox.data.unread > 0 ? (
        <Button
          label={`Mark all ${inbox.data.unread} as read`}
          variant="ghost"
          loading={busy}
          className="mb-2 self-end"
          onPress={async () => {
            setBusy(true);
            try {
              await markAllRead();
              inbox.reload();
            } finally {
              setBusy(false);
            }
          }}
        />
      ) : null}
      {inbox.data.items.length === 0 ? (
        <EmptyState icon="notifications-outline" title="Nothing yet" message="Updates about your bookings, payments and deliveries appear here." />
      ) : (
        inbox.data.items.map((item) => <Item key={item.id} item={item} onOpened={inbox.reload} />)
      )}
      {prefs.status === 'success' ? <Preferences initial={prefs.data} /> : null}
    </ScrollView>
  );
}

export default function NotificationsScreen() {
  const { state } = useAuth();
  return (
    <>
      <Stack.Screen options={{ title: 'Notifications' }} />
      {state.status === 'loading' ? (
        <LoadingState />
      ) : state.status === 'signedOut' ? (
        <SignInPrompt message="Log in to see your notifications." />
      ) : (
        <Inbox />
      )}
    </>
  );
}
