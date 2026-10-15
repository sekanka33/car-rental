import { Link, Stack } from 'expo-router';
import { Pressable, Text } from 'react-native';

import { SignInPrompt } from '@/components/sign-in-prompt';
import { Screen } from '@/components/ui/screen';
import { EmptyState, ErrorState, LoadingState } from '@/components/ui/state-views';
import { useAuth } from '@/context/auth';
import { useAsync } from '@/hooks/use-async';
import { formatDateTime } from '@/lib/dates';
import { listMyDeliveries } from '@/services/owner-deliveries';

const STATUS: Record<string, string> = {
  PENDING_SCHEDULE: 'Time not confirmed',
  SCHEDULED: 'Scheduled',
  EN_ROUTE: 'On the way',
  DELIVERED: 'Delivered, awaiting return',
  FAILED: 'Stopped: support will contact you',
  CANCELLED: 'Cancelled',
};

function DeliveryList() {
  const deliveries = useAsync(listMyDeliveries);
  if (deliveries.status === 'loading') return <LoadingState />;
  if (deliveries.status === 'error') return <ErrorState message={deliveries.error.message} onAction={deliveries.reload} />;
  if (deliveries.data.length === 0) {
    return <EmptyState title="No deliveries" message="Paid bookings of your cars appear here." />;
  }
  return (
    <Screen scroll>
      {deliveries.data.map((delivery) => (
        <Link key={delivery.id} href={{ pathname: '/deliveries/[id]', params: { id: delivery.id } }} asChild>
          <Pressable className="mb-3 rounded-xl border border-surface-border p-4 active:bg-surface-muted">
            <Text className="text-base font-semibold text-ink">
              {delivery.vehicle.make} {delivery.vehicle.model} · {delivery.booking_reference}
            </Text>
            <Text className="mt-1 text-sm text-ink-muted">{STATUS[delivery.status]}</Text>
            <Text className="text-sm text-ink-muted">
              {delivery.scheduled_for ? formatDateTime(delivery.scheduled_for) : `Rental starts ${formatDateTime(delivery.rental_start_at)}`}
            </Text>
          </Pressable>
        </Link>
      ))}
    </Screen>
  );
}

export default function DeliveriesScreen() {
  const { state } = useAuth();
  return (
    <>
      <Stack.Screen options={{ title: 'My deliveries' }} />
      {state.status === 'loading' ? (
        <LoadingState />
      ) : state.status === 'signedOut' ? (
        <SignInPrompt message="Log in to see your deliveries." />
      ) : !state.user.roles.includes('OWNER') ? (
        <EmptyState title="Owner accounts only" message="Deliveries are for vehicle owners." />
      ) : (
        <DeliveryList />
      )}
    </>
  );
}
