import { router, Stack } from 'expo-router';
import { FlatList, Pressable, RefreshControl, Text, View } from 'react-native';

import { Badge, type BadgeTone } from '@/components/ui/badge';
import { EmptyState, ErrorState, LoadingState } from '@/components/ui/state-views';
import { useAsync } from '@/hooks/use-async';
import { formatDateTime } from '@/lib/dates';
import { formatZar } from '@/lib/format';
import { listMyPayments } from '@/services/customers';
import type { PaymentStatus, RenterPayment } from '@/types/payment';

const STATUS: Record<PaymentStatus, { label: string; tone: BadgeTone }> = {
  PENDING: { label: 'Not completed', tone: 'warning' },
  SUCCEEDED: { label: 'Paid', tone: 'success' },
  FAILED: { label: 'Failed', tone: 'danger' },
  CANCELLED: { label: 'Cancelled', tone: 'neutral' },
  REFUND_PENDING: { label: 'Refund on its way', tone: 'info' },
  REFUNDED: { label: 'Refunded', tone: 'neutral' },
  PARTIALLY_REFUNDED: { label: 'Partly refunded', tone: 'info' },
};

const REFUND_STATUS = { PENDING: 'on its way', PROCESSED: 'refunded', FAILED: 'failed (support will contact you)' };

function PaymentRow({ payment }: { payment: RenterPayment }) {
  const status = STATUS[payment.status];
  return (
    <Pressable
      accessibilityRole="button"
      onPress={() => router.push({ pathname: '/bookings/[id]', params: { id: payment.booking_id } })}
      className="mb-3 rounded-2xl border border-surface-border bg-white p-4 active:opacity-80">
      <View className="flex-row items-start justify-between">
        <Text className="flex-1 pr-2 text-base font-semibold text-ink">{payment.vehicle}</Text>
        <Badge label={status.label} tone={status.tone} />
      </View>
      <Text className="mt-1 text-sm text-ink-muted">
        {formatDateTime(payment.paid_at ?? payment.created_at)} · Booking {payment.booking_reference}
      </Text>
      <Text className="mt-2 text-base font-semibold text-ink">{formatZar(payment.amount)}</Text>
      {payment.failure_reason && payment.status === 'FAILED' ? (
        <Text className="mt-1 text-sm text-danger">{payment.failure_reason}</Text>
      ) : null}
      {payment.refunds.map((refund) => (
        <Text key={refund.id} className="mt-1 text-sm text-ink-muted">
          {formatZar(refund.amount)} {REFUND_STATUS[refund.status]} · {formatDateTime(refund.processed_at ?? refund.created_at)}
        </Text>
      ))}
    </Pressable>
  );
}

export default function PaymentHistoryScreen() {
  const payments = useAsync(listMyPayments);
  return (
    <>
      <Stack.Screen options={{ title: 'Payment history' }} />
      {payments.status === 'loading' ? (
        <LoadingState />
      ) : payments.status === 'error' ? (
        <ErrorState message={payments.error.message} onAction={payments.reload} />
      ) : (
        <FlatList
          className="flex-1 bg-surface-muted"
          data={payments.data}
          keyExtractor={(p) => p.id}
          renderItem={({ item }) => <PaymentRow payment={item} />}
          contentContainerClassName="flex-grow p-5"
          refreshControl={<RefreshControl refreshing={false} onRefresh={payments.reload} />}
          ListHeaderComponent={
            <Text className="mb-3 text-sm text-ink-muted">
              Refunds go back to the card you paid with and can take 5–10 working days to show.
            </Text>
          }
          ListEmptyComponent={<EmptyState icon="receipt-outline" title="No payments yet" message="Payments for your bookings appear here." />}
        />
      )}
    </>
  );
}
