import { router } from 'expo-router';
import { RefreshControl, ScrollView, Text, View } from 'react-native';

import { ActionRow, SectionTitle, StatTile } from '@/components/dashboard';
import { SignInPrompt } from '@/components/sign-in-prompt';
import { BookingStatusBadge } from '@/components/booking-status-badge';
import { EmptyState, ErrorState, LoadingState } from '@/components/ui/state-views';
import { useAuth } from '@/context/auth';
import { useAsync } from '@/hooks/use-async';
import { useReloadOnFocus } from '@/hooks/use-reload-on-focus';
import { formatDateTime } from '@/lib/dates';
import { formatZar } from '@/lib/format';
import { DOCUMENT_TYPE } from '@/lib/labels';
import { getOwnerDashboard } from '@/services/owner';
import type { OwnerDashboard } from '@/types/owner';

function plural(n: number, one: string, many = `${one}s`) {
  return `${n} ${n === 1 ? one : many}`;
}

function Dashboard({ data, reload }: { data: OwnerDashboard; reload: () => void }) {
  const cars = data.vehicles_by_status;
  const totalCars = Object.values(cars).reduce((a, b) => a + b, 0);
  const listed = cars.APPROVED;
  const next = data.next_booking;
  const toDo = data.deliveries_to_do + data.returns_to_record;

  return (
    <ScrollView
      className="flex-1 bg-surface-muted"
      contentContainerClassName="p-5 pb-10"
      refreshControl={<RefreshControl refreshing={false} onRefresh={reload} />}>
      <View className="rounded-2xl bg-brand-500 p-5">
        <Text className="text-sm text-white/80">Collected this month</Text>
        <Text className="mt-1 text-3xl font-bold text-white">{formatZar(data.month_net)}</Text>
        <Text className="mt-1 text-sm text-white/80">
          {formatZar(data.year_net)} this year · before platform commission
        </Text>
      </View>

      <View className="mt-4 flex-row gap-3">
        <StatTile value={String(data.upcoming_bookings)} label="Upcoming" onPress={() => router.push('/owner/bookings')} />
        <StatTile value={String(data.active_rentals)} label="On the road" onPress={() => router.push('/owner/bookings?scope=active')} />
        <StatTile value={`${listed}/${totalCars}`} label="Cars listed" onPress={() => router.push('/owner/vehicles')} />
      </View>

      {toDo > 0 || data.expiring_documents.length > 0 || cars.REJECTED > 0 || cars.DRAFT > 0 ? (
        <>
          <SectionTitle title="Needs your attention" />
          {data.deliveries_to_do > 0 ? (
            <ActionRow
              icon="navigate-outline"
              tone="attention"
              title={plural(data.deliveries_to_do, 'delivery', 'deliveries') + ' to do'}
              detail="Confirm the time, set off and hand over"
              onPress={() => router.push('/deliveries')}
            />
          ) : null}
          {data.returns_to_record > 0 ? (
            <ActionRow
              icon="return-down-back-outline"
              tone="attention"
              title={plural(data.returns_to_record, 'return') + ' to record'}
              detail="Record the odometer and condition when the car comes back"
              onPress={() => router.push('/deliveries')}
            />
          ) : null}
          {data.expiring_documents.map((doc) => (
            <ActionRow
              key={`${doc.vehicle_id}-${doc.document_type}`}
              icon="document-text-outline"
              tone="attention"
              title={`${DOCUMENT_TYPE[doc.document_type]} ${doc.expired ? 'expired' : 'expires soon'}`}
              detail={`${doc.vehicle} · ${doc.expiry_date}. Upload the renewed one.`}
              onPress={() => router.push({ pathname: '/owner/vehicles/[id]', params: { id: doc.vehicle_id } })}
            />
          ))}
          {cars.REJECTED > 0 ? (
            <ActionRow
              icon="alert-circle-outline"
              tone="attention"
              title={`${plural(cars.REJECTED, 'car')} rejected`}
              detail="See the reason, fix it and submit again"
              onPress={() => router.push('/owner/vehicles')}
            />
          ) : null}
          {cars.DRAFT > 0 ? (
            <ActionRow
              icon="create-outline"
              title={`${plural(cars.DRAFT, 'draft')} not submitted`}
              detail="Add photos and documents, then submit for review"
              onPress={() => router.push('/owner/vehicles')}
            />
          ) : null}
        </>
      ) : null}

      {next ? (
        <>
          <SectionTitle title="Next booking" />
          <ActionRow
            icon="calendar-outline"
            title={`${next.vehicle.make} ${next.vehicle.model} · ${next.renter_first_name}`}
            detail={`${formatDateTime(next.start_at)} → ${formatDateTime(next.end_at)}`}
            onPress={() =>
              next.delivery_id
                ? router.push({ pathname: '/deliveries/[id]', params: { id: next.delivery_id } })
                : router.push('/owner/bookings')
            }
          />
          <View className="-mt-1 mb-1 ml-1">
            <BookingStatusBadge status={next.status} />
          </View>
        </>
      ) : null}

      <SectionTitle title="Manage" />
      <ActionRow icon="car-sport-outline" title="My cars" detail={plural(totalCars, 'car')} onPress={() => router.push('/owner/vehicles')} />
      <ActionRow icon="calendar-outline" title="Bookings" detail="Upcoming, on the road and past" onPress={() => router.push('/owner/bookings')} />
      <ActionRow icon="navigate-outline" title="Deliveries and returns" onPress={() => router.push('/deliveries')} />
      <ActionRow icon="cash-outline" title="Earnings" detail="Per month and per booking" onPress={() => router.push('/owner/earnings')} />
    </ScrollView>
  );
}

function OwnerHome() {
  const dashboard = useAsync(getOwnerDashboard);
  useReloadOnFocus(dashboard.reload);
  if (dashboard.status === 'loading') return <LoadingState />;
  if (dashboard.status === 'error') return <ErrorState message={dashboard.error.message} onAction={dashboard.reload} />;
  return <Dashboard data={dashboard.data} reload={dashboard.reload} />;
}

export default function OwnerTab() {
  const { state } = useAuth();
  if (state.status === 'loading') return <LoadingState />;
  if (state.status === 'signedOut') return <SignInPrompt message="Log in to manage your cars." />;
  if (!state.user.roles.includes('OWNER')) {
    return <EmptyState title="Owner accounts only" message="Register as an owner to list your car." />;
  }
  return <OwnerHome />;
}
