import { Stack, router } from 'expo-router';

import { EmptyState } from '@/components/ui/state-views';

export default function NotFoundScreen() {
  return (
    <>
      <Stack.Screen options={{ title: 'Not found' }} />
      <EmptyState
        icon="compass-outline"
        title="Page not found"
        message="The screen you were looking for doesn't exist."
        actionLabel="Go to home"
        onAction={() => router.replace('/')}
      />
    </>
  );
}
