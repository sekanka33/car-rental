import { Link, router } from 'expo-router';
import { useCallback } from 'react';
import { Pressable, RefreshControl, ScrollView, Text, View } from 'react-native';

import { BookingStatusBadge } from '@/components/booking-status-badge';
import { ActionRow, SectionTitle } from '@/components/dashboard';
import { SignInPrompt } from '@/components/sign-in-prompt';
import { EmptyState, ErrorState, LoadingState } from '@/components/ui/state-views';
import { useAuth } from '@/context/auth';
import { useAsync } from '@/hooks/use-async';
import { useReloadOnFocus } from '@/hooks/use-reload-on-focus';
import { groupRenterBookings } from '@/lib/renter';
import { formatDateTime } from '@/lib/dates';
import { formatZar } from '@/lib/format';
import { listMyBookings } from '@/services/bookings';
import { getCustomerProfile } from '@/services/customers';
import type { Booking } from '@/types/booking';
import type { CustomerProfile } from '@/types/profile';

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

function Section({ title, bookings }: { title: string; bookings: Booking[] }) {
  if (bookings.length === 0) return null;
  return (
    <>
      <SectionTitle title={title} />
      {bookings.map((b) => (
        <BookingRow key={b.id} booking={b} />
      ))}
    </>
  );
}

function verificationTask(profile: CustomerProfile | undefined): string | null {
  if (!profile) return null;
  const statuses = [profile.id_verification_status, profile.licence_verification_status];
  if (statuses.every((s) => s === 'APPROVED') && profile.date_of_birth) return null;
  if (statuses.some((s) => s === 'REJECTED' || s === 'REQUIRES_MORE_INFORMATION')) {
    return 'A document needs attention before you can book';
  }
  if (statuses.every((s) => s === 'PENDING' || s === 'APPROVED') && profile.date_of_birth) return null; // under review
  return 'Add your date of birth, ID and driving licence to book';
}

function Dashboard() {
  const loadBookings = useCallback(() => listMyBookings(), []);
  const bookings = useAsync(loadBookings);
  const profile = useAsync(getCustomerProfile);
  const { reload: reloadBookings } = bookings;
  const { reload: reloadProfile } = profile;
  const reload = useCallback(() => {
    reloadBookings();
    reloadProfile();
  }, [reloadBookings, reloadProfile]);
  useReloadOnFocus(reload);

  if (bookings.status === 'loading') return <LoadingState message="Loading your bookings…" />;
  if (bookings.status === 'error') return <ErrorState message={bookings.error.message} onAction={bookings.reload} />;

  const groups = groupRenterBookings(bookings.data);
  const verify = verificationTask(profile.data);
  const empty = bookings.data.length === 0;

  return (
    <ScrollView
      className="flex-1 bg-surface-muted"
      contentContainerClassName="flex-grow p-5 pb-10"
      refreshControl={<RefreshControl refreshing={false} onRefresh={reload} />}>
      {groups.toPay.length > 0 || groups.toConfirm.length > 0 || verify ? (
        <>
          <SectionTitle title="Needs your attention" />
          {groups.toPay.map((b) => (
            <ActionRow
              key={b.id}
              icon="card-outline"
              tone="attention"
              title={`Pay for ${b.vehicle.make} ${b.vehicle.model}`}
              detail={b.hold_expires_at ? `Held until ${formatDateTime(b.hold_expires_at)}` : undefined}
              onPress={() => router.push({ pathname: '/bookings/[id]', params: { id: b.id } })}
            />
          ))}
          {groups.toConfirm.map((b) => (
            <ActionRow
              key={b.id}
              icon="key-outline"
              tone="attention"
              title={`Confirm you have the ${b.vehicle.make} ${b.vehicle.model}`}
              detail="Check the handover record and confirm receipt"
              onPress={() => router.push({ pathname: '/bookings/[id]', params: { id: b.id } })}
            />
          ))}
          {verify ? (
            <ActionRow icon="id-card-outline" tone="attention" title="Verify your identity" detail={verify} onPress={() => router.push('/verification')} />
          ) : null}
        </>
      ) : null}

      {empty ? (
        <EmptyState icon="calendar-outline" title="No bookings yet" message="Find a car and book your first trip." />
      ) : (
        <>
          <Section title="Now" bookings={groups.current} />
          <Section title="Upcoming" bookings={groups.upcoming} />
          <Section title="Past" bookings={groups.past} />
        </>
      )}
      <View className="mt-4">
        <ActionRow icon="receipt-outline" title="Payment history" detail="Payments and refunds" onPress={() => router.push('/payments')} />
      </View>
    </ScrollView>
  );
}

export default function BookingsScreen() {
  const { state } = useAuth();
  if (state.status === 'loading') return <LoadingState />;
  if (state.status === 'signedOut') return <SignInPrompt message="Log in to see your bookings." />;
  if (!state.user.roles.includes('RENTER')) {
    return <EmptyState title="Renter accounts only" message="Bookings are made with a renter account." />;
  }
  return <Dashboard />;
}
