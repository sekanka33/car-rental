import { router } from 'expo-router';

import { EmptyState } from '@/components/ui/state-views';

export function SignInPrompt({ message }: { message: string }) {
  return (
    <EmptyState
      icon="person-circle-outline"
      title="Log in to continue"
      message={message}
      actionLabel="Log in"
      onAction={() => router.push('/login')}
    />
  );
}
