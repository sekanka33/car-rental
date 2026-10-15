import { useFocusEffect } from 'expo-router';
import { useCallback, useRef } from 'react';

/** Re-runs `reload` when the screen comes back into view (not on the first visit, which
 * already loads), so dashboards reflect changes made on other screens. */
export function useReloadOnFocus(reload: () => void) {
  const first = useRef(true);
  useFocusEffect(
    useCallback(() => {
      if (first.current) {
        first.current = false;
        return;
      }
      reload();
    }, [reload]),
  );
}
