import { useEffect, useState } from 'react';
import { AppState } from 'react-native';

import { getInbox } from '@/services/notifications';

const POLL_MS = 60_000;

/** Unread notifications for the signed-in user: on sign-in, every minute and when the app
 * comes back to the foreground. 0 when signed out or offline. */
export function useUnreadCount(signedIn: boolean): number {
  const [count, setCount] = useState(0);
  useEffect(() => {
    if (!signedIn) return;
    let active = true;
    const refresh = () =>
      getInbox(1).then(
        (inbox) => active && setCount(inbox.unread),
        () => undefined,
      );
    void refresh();
    const timer = setInterval(refresh, POLL_MS);
    const subscription = AppState.addEventListener('change', (next) => next === 'active' && void refresh());
    return () => {
      active = false;
      clearInterval(timer);
      subscription.remove();
    };
  }, [signedIn]);
  return signedIn ? count : 0;
}
