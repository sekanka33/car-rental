import { Link } from 'expo-router';
import { useCallback } from 'react';
import { FlatList, Pressable, RefreshControl, Text, View } from 'react-native';

import { BookingStatusBadge } from '@/components/booking-status-badge';
import { SignInPrompt } from '@/components/sign-in-prompt';
import { EmptyState, ErrorState, LoadingState } from '@/components/ui/state-views';
import { useAuth } from '@/context/auth';
import { useAsync } from '@/hooks/use-async';
import { formatDateTime } from '@/lib/dates';
import { formatZar } from '@/lib/format';
import { listMyBookings } from '@/services/bookings';
import type { Booking } from '@/types/booking';

function BookingRow({ booking }: { booking: Booking }) {
  return (
    <Link href={{ pathname: '/bookings/[id]', params: { id: booking.id } }} asChild>
      <Pressable className="mb-3 rounded-2xl border border-surface-border bg-white p-4 active:opacity-80">
        <View className="flex-row items-start justify-between">
          <Text className="flex-1 pr-2 text-lg font-semibold text-ink">
            {booking.vehicle.make} {booking.vehicle.model}
          </Text>
          <BookingStatusBadge status={booking.status} />
        </View>
        <Text className="mt-1 text-sm text-ink-muted">
          {formatDateTime(booking.start_at)} → {formatDateTime(booking.end_at)}
        </Text>
        <View className="mt-2 flex-row justify-between">
          <Text className="text-sm text-ink-muted">Ref {booking.reference}</Text>
          <Text className="text-base font-semibold text-ink">{formatZar(booking.price.total_amount)}</Text>
        </View>
      </Pressable>
    </Link>
  );
}

function MyBookings() {
  const load = useCallback(() => listMyBookings(), []);
  const bookings = useAsync(load);

  if (bookings.status === 'loading') return <LoadingState message="Loading your bookings…" />;
  if (bookings.status === 'error') return <ErrorState message={bookings.error.message} onAction={bookings.reload} />;
  return (
    <FlatList
      data={bookings.data}
      keyExtractor={(item) => item.id}
      renderItem={({ item }) => <BookingRow booking={item} />}
      contentContainerClassName="flex-grow p-5"
      refreshControl={<RefreshControl refreshing={false} onRefresh={bookings.reload} />}
      ListEmptyComponent={
        <EmptyState icon="calendar-outline" title="No bookings yet" message="Find a car and book your first trip." />
      }
    />
  );
}

export default function BookingsScreen() {
  const { state } = useAuth();
  if (state.status === 'loading') return <LoadingState />;
  if (state.status === 'signedOut') return <SignInPrompt message="Log in to see your bookings." />;
  if (!state.user.roles.includes('RENTER')) {
    return <EmptyState title="Renter accounts only" message="Bookings are made with a renter account." />;
  }
  return (
    <View className="flex-1 bg-surface-muted">
      <MyBookings />
    </View>
  );
}
