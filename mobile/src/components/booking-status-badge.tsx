import { Badge, type BadgeTone } from '@/components/ui/badge';
import type { BookingStatus } from '@/types/booking';

const DISPLAY: Record<BookingStatus, { label: string; tone: BadgeTone }> = {
  PENDING_PAYMENT: { label: 'Awaiting payment', tone: 'warning' },
  CONFIRMED: { label: 'Confirmed', tone: 'success' },
  CANCELLED: { label: 'Cancelled', tone: 'neutral' },
  EXPIRED: { label: 'Expired', tone: 'neutral' },
  DELIVERY_SCHEDULED: { label: 'Delivery scheduled', tone: 'info' },
  IN_TRANSIT: { label: 'On the way', tone: 'info' },
  DELIVERED: { label: 'Delivered', tone: 'info' },
  ACTIVE_RENTAL: { label: 'Active rental', tone: 'success' },
  RETURN_PENDING: { label: 'Return pending', tone: 'info' },
  COMPLETED: { label: 'Completed', tone: 'neutral' },
};

export function BookingStatusBadge({ status }: { status: BookingStatus }) {
  return <Badge label={DISPLAY[status].label} tone={DISPLAY[status].tone} />;
}
