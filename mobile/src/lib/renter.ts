import type { Booking, BookingStatus } from '@/types/booking';

const CURRENT: BookingStatus[] = ['IN_TRANSIT', 'DELIVERED', 'ACTIVE_RENTAL', 'RETURN_PENDING'];
const UPCOMING: BookingStatus[] = ['PENDING_PAYMENT', 'CONFIRMED', 'DELIVERY_SCHEDULED'];

/**
 * Splits the renter's bookings for the dashboard. `toPay` (unpaid holds) and `toConfirm`
 * (handed over, receipt not confirmed) are also listed in their normal section.
 */
export function groupRenterBookings(bookings: Booking[]) {
  const byStart = (a: Booking, b: Booking) => Date.parse(a.start_at) - Date.parse(b.start_at);
  return {
    toPay: bookings.filter((b) => b.status === 'PENDING_PAYMENT'),
    toConfirm: bookings.filter((b) => b.status === 'DELIVERED'),
    current: bookings.filter((b) => CURRENT.includes(b.status)).sort(byStart),
    upcoming: bookings.filter((b) => UPCOMING.includes(b.status)).sort(byStart),
    past: bookings
      .filter((b) => !CURRENT.includes(b.status) && !UPCOMING.includes(b.status))
      .sort((a, b) => byStart(b, a)),
  };
}
