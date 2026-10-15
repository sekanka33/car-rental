import { fireEvent, render, screen } from '@testing-library/react-native';
import { SafeAreaProvider } from 'react-native-safe-area-context';

import OwnerTab from '@/app/(tabs)/owner';
import DeliveryScreen from '@/app/deliveries/[id]';
import OwnerBookingsScreen from '@/app/owner/bookings';
import EarningsScreen from '@/app/owner/earnings';
import AvailabilityScreen from '@/app/owner/vehicles/[id]/availability';
import EditVehicleScreen from '@/app/owner/vehicles/[id]/edit';
import VehicleScreen from '@/app/owner/vehicles/[id]/index';
import RegisterVehicleScreen from '@/app/owner/vehicles/new';
import { useAuth } from '@/context/auth';
import * as owner from '@/services/owner';
import * as deliveries from '@/services/owner-deliveries';
import type { AssignedDelivery } from '@/services/owner-deliveries';
import type { OwnerDashboard, OwnerVehicle } from '@/types/owner';

jest.mock('@/context/auth', () => ({ useAuth: jest.fn() }));
jest.mock('@/services/owner', () => ({
  getOwnerDashboard: jest.fn(),
  listOwnerBookings: jest.fn(),
  getEarnings: jest.fn(),
  listMyVehicles: jest.fn(),
  getMyVehicle: jest.fn(),
  registerVehicle: jest.fn(),
  updateVehicle: jest.fn(),
  deleteVehicle: jest.fn(),
  submitVehicle: jest.fn(),
  withdrawVehicle: jest.fn(),
  setListed: jest.fn(),
  vehiclePhotoPath: (v: string, p: string) => `/photos/${v}/${p}`,
  uploadVehiclePhoto: jest.fn(),
  deleteVehiclePhoto: jest.fn(),
  uploadVehicleDocument: jest.fn(),
  listBlocks: jest.fn(),
  addBlock: jest.fn(),
  removeBlock: jest.fn(),
}));
jest.mock('@/services/owner-deliveries', () => ({
  getMyDelivery: jest.fn(),
  startDelivery: jest.fn(),
  scheduleDelivery: jest.fn(),
  recordHandover: jest.fn(),
  recordReturn: jest.fn(),
  reportProblem: jest.fn(),
  uploadRecordPhoto: jest.fn(),
}));
jest.mock('@/hooks/use-location-sharing', () => ({
  useLocationSharing: () => ({ sharing: false, lastSentAt: null, error: null, ended: false, start: jest.fn(), stop: jest.fn() }),
}));
jest.mock('@/components/private-image', () => ({ PrivateImage: () => null }));
jest.mock('@/lib/upload', () => ({
  pickImage: jest.fn(),
  pickDocument: jest.fn(async () => ({ uri: 'file:///disc.pdf', name: 'disc.pdf', mimeType: 'application/pdf' })),
}));
jest.mock('expo-router', () => ({
  Link: ({ children }: { children: React.ReactNode }) => children,
  Stack: { Screen: () => null },
  router: { replace: jest.fn(), push: jest.fn(), back: jest.fn() },
  useLocalSearchParams: () => jest.requireMock('expo-router').params,
  useFocusEffect: jest.fn(),
  params: { id: 'v1' },
}));

const mockRouter = jest.requireMock('expo-router') as {
  router: { replace: jest.Mock; push: jest.Mock; back: jest.Mock };
  params: Record<string, string>;
};
const mocked = <T extends (...args: never[]) => unknown>(fn: T) => fn as unknown as jest.Mock;

const METRICS = { frame: { x: 0, y: 0, width: 390, height: 844 }, insets: { top: 0, left: 0, right: 0, bottom: 0 } };
const wrap = (ui: React.ReactElement) => render(<SafeAreaProvider initialMetrics={METRICS}>{ui}</SafeAreaProvider>);

const ownerUser = { id: 'o1', email: 'o@b.co', full_name: 'Thabo Owner', phone_number: null, status: 'ACTIVE', roles: ['OWNER'], email_verified: true, created_at: '' };

function vehicle(overrides: Partial<OwnerVehicle> = {}): OwnerVehicle {
  return {
    id: 'v1', make: 'Toyota', model: 'Corolla', year: 2022, registration_number: 'CA123456', vin: 'AHTBB3JE500012345',
    colour: 'White', transmission: 'AUTOMATIC', fuel_type: 'PETROL', seats: 5, city: 'Cape Town', province: 'Western Cape',
    description: null, status: 'DRAFT', rejection_reason: null, suspension_reason: null, submitted_at: null, approved_at: null,
    created_at: '2026-10-01T08:00:00Z', current_price: null, photos: [], documents: [],
    compliance: { ok: false, missing: ['REGISTRATION_CERTIFICATE', 'LICENCE_DISC', 'INSURANCE'], expired: [] },
    ...overrides,
  };
}

const photos = (n: number) => Array.from({ length: n }, (_, i) => ({ id: `p${i}`, content_type: 'image/jpeg', size_bytes: 1, sort_order: i }));

beforeEach(() => {
  mocked(useAuth).mockReturnValue({ state: { status: 'signedIn', user: ownerUser } });
  mockRouter.params = { id: 'v1' };
});

describe('owner dashboard', () => {
  const dashboard: OwnerDashboard = {
    vehicles_by_status: { DRAFT: 0, PENDING_APPROVAL: 1, APPROVED: 2, REJECTED: 0, SUSPENDED: 0, UNAVAILABLE: 0 },
    upcoming_bookings: 3, active_rentals: 1, deliveries_to_do: 2, returns_to_record: 0,
    month_net: '3400.00', year_net: '18250.50', currency: 'ZAR',
    expiring_documents: [{ vehicle_id: 'v9', vehicle: 'VW Polo (CA1)', document_type: 'LICENCE_DISC', expiry_date: '2026-10-30', expired: false }],
    next_booking: null,
  };

  it('shows money, counts and what needs doing', async () => {
    mocked(owner.getOwnerDashboard).mockResolvedValue(dashboard);
    await wrap(<OwnerTab />);

    expect(await screen.findByText('R 3 400.00')).toBeTruthy();
    expect(screen.getByText(/R 18 250.50 this year · before platform commission/)).toBeTruthy();
    expect(screen.getByText('2/3')).toBeTruthy(); // listed of all cars
    await fireEvent.press(screen.getByText('2 deliveries to do'));
    expect(mockRouter.router.push).toHaveBeenCalledWith('/deliveries');
    await fireEvent.press(screen.getByText('Licence disc expires soon'));
    expect(mockRouter.router.push).toHaveBeenCalledWith({ pathname: '/owner/vehicles/[id]', params: { id: 'v9' } });
  });

  it('is only for owners', async () => {
    mocked(useAuth).mockReturnValue({ state: { status: 'signedIn', user: { ...ownerUser, roles: ['RENTER'] } } });
    await wrap(<OwnerTab />);
    expect(screen.getByText('Owner accounts only')).toBeTruthy();
    expect(owner.getOwnerDashboard).not.toHaveBeenCalled();
  });
});

describe('registering and editing a car', () => {
  async function fill(fields: Record<string, string>) {
    for (const [label, value] of Object.entries(fields)) await fireEvent.changeText(screen.getByLabelText(label), value);
  }

  it('checks the form, then saves a normalised car and opens it', async () => {
    mocked(owner.registerVehicle).mockResolvedValue(vehicle({ id: 'new1' }));
    await wrap(<RegisterVehicleScreen />);

    await fill({ Make: 'Toyota', Model: 'Corolla', Year: '2022', 'Registration number': 'ca 123-456', VIN: 'BAD', 'City or town': 'Cape Town' });
    await fireEvent.press(screen.getByText('Save and continue'));
    expect(screen.getByText('The VIN has 17 letters and digits (no I, O or Q).')).toBeTruthy();
    expect(screen.getByText('Choose a province.')).toBeTruthy();
    expect(owner.registerVehicle).not.toHaveBeenCalled();

    await fill({ VIN: 'ahtbb3je500012345' });
    await fireEvent.press(screen.getByText('Automatic'));
    await fireEvent.press(screen.getByText('Petrol'));
    await fireEvent.press(screen.getByText('Western Cape'));
    await fireEvent.press(screen.getByText('Save and continue'));

    expect(owner.registerVehicle).toHaveBeenCalledWith(
      expect.objectContaining({ registration_number: 'CA123456', vin: 'AHTBB3JE500012345', province: 'Western Cape', seats: 5, colour: null }),
    );
    expect(mockRouter.router.replace).toHaveBeenCalledWith({ pathname: '/owner/vehicles/[id]', params: { id: 'new1' } });
  });

  it('shows backend field errors', async () => {
    const { ApiError } = jest.requireActual('@/lib/api');
    mocked(owner.registerVehicle).mockRejectedValue(
      new ApiError('x', 422, 'validation_error', [{ location: ['body', 'year'], message: 'year must be between 1981 and 2027' }]),
    );
    await wrap(<RegisterVehicleScreen />);
    await fill({ Make: 'Toyota', Model: 'Corolla', Year: '2029', 'Registration number': 'CA1', VIN: 'AHTBB3JE500012345', 'City or town': 'Durban' });
    await fireEvent.press(screen.getByText('Manual'));
    await fireEvent.press(screen.getByText('Diesel'));
    await fireEvent.press(screen.getByText('KwaZulu-Natal'));
    await fireEvent.press(screen.getByText('Save and continue'));
    expect(await screen.findByText('year must be between 1981 and 2027')).toBeTruthy();
  });

  it('sends only changed fields, so cosmetic edits do not trigger a review', async () => {
    mocked(owner.getMyVehicle).mockResolvedValue(vehicle({ status: 'APPROVED' }));
    await wrap(<EditVehicleScreen />);
    expect(await screen.findByText(/sends the car back for review/)).toBeTruthy();

    await fill({ 'Colour (optional)': 'Silver' });
    await fireEvent.press(screen.getByText('Save changes'));

    expect(owner.updateVehicle).toHaveBeenCalledWith('v1', { colour: 'Silver' });
    expect(mockRouter.router.back).toHaveBeenCalled();
  });
});

describe('car details', () => {
  it('only allows submitting with 3 photos and the required documents', async () => {
    mocked(owner.getMyVehicle).mockResolvedValue(vehicle({ photos: photos(2) }));
    await wrap(<VehicleScreen />);

    expect(await screen.findByText(/To submit: a confirmed email address, at least 3 photos/)).toBeTruthy();
    expect(screen.getByText('Add at least 3 clear photos: front, back, side and inside.')).toBeTruthy();
    await fireEvent.press(screen.getByText('Submit for review'));
    expect(owner.submitVehicle).not.toHaveBeenCalled();
  });

  it('submits a complete draft', async () => {
    mocked(owner.getMyVehicle).mockResolvedValue(vehicle({ photos: photos(3), compliance: { ok: true, missing: [], expired: [] } }));
    mocked(owner.submitVehicle).mockResolvedValue(vehicle({ status: 'PENDING_APPROVAL' }));
    await wrap(<VehicleScreen />);

    await fireEvent.press(await screen.findByText('Submit for review'));
    expect(owner.submitVehicle).toHaveBeenCalledWith('v1');
  });

  it('shows the rejection reason and the read-only official price', async () => {
    mocked(owner.getMyVehicle).mockResolvedValue(
      vehicle({
        status: 'REJECTED',
        rejection_reason: 'Licence disc photo is blurry',
        current_price: { daily_rate: '650.00', delivery_fee: '150.00', deposit_amount: '2000.00', currency: 'ZAR' },
      }),
    );
    await wrap(<VehicleScreen />);
    expect(await screen.findByText('Not approved: Licence disc photo is blurry. Fix this and submit again.')).toBeTruthy();
    expect(screen.getByText('R 650.00 per day')).toBeTruthy();
    expect(screen.getByText('Official price (set by CarHire SA)')).toBeTruthy();
  });

  it('hides a listed car from the marketplace', async () => {
    mocked(owner.getMyVehicle).mockResolvedValue(vehicle({ status: 'APPROVED', photos: photos(3), compliance: { ok: true, missing: [], expired: [] } }));
    mocked(owner.setListed).mockResolvedValue(vehicle({ status: 'UNAVAILABLE' }));
    await wrap(<VehicleScreen />);

    await fireEvent.press(await screen.findByText('Hide from the marketplace'));
    expect(owner.setListed).toHaveBeenCalledWith('v1', false);
  });

  it('asks for the expiry date before uploading a licence disc', async () => {
    mocked(owner.getMyVehicle).mockResolvedValue(vehicle());
    await wrap(<VehicleScreen />);
    await screen.findByText('Licence disc');

    // Rows in order: registration certificate, licence disc, insurance, roadworthy.
    await fireEvent.press(screen.getAllByText('Upload')[1]);
    await fireEvent.press(screen.getByText('PDF or file'));
    expect(screen.getByText('Enter the expiry date as YYYY-MM-DD (in the future).')).toBeTruthy();
    expect(owner.uploadVehicleDocument).not.toHaveBeenCalled();

    await fireEvent.changeText(screen.getByLabelText('Expiry date'), '2099-05-01');
    await fireEvent.press(screen.getByText('PDF or file'));
    expect(owner.uploadVehicleDocument).toHaveBeenCalledWith('v1', 'LICENCE_DISC', expect.objectContaining({ name: 'disc.pdf' }), '2099-05-01');
  });

  it('blocks whole days', async () => {
    mocked(owner.listBlocks).mockResolvedValue([]);
    await wrap(<AvailabilityScreen />);
    await fireEvent.changeText(await screen.findByLabelText('First day'), '2099-03-01');
    await fireEvent.changeText(screen.getByLabelText('Last day'), '2099-03-02');
    await fireEvent.press(screen.getByText('Block these days'));
    expect(owner.addBlock).toHaveBeenCalledWith('v1', {
      start_at: '2099-03-01T00:00:00+02:00',
      end_at: '2099-03-03T00:00:00+02:00',
      reason: null,
    });
  });
});

describe('bookings and earnings', () => {
  it('switches between upcoming and on-the-road bookings', async () => {
    mockRouter.params = {};
    mocked(owner.listOwnerBookings).mockResolvedValue([]);
    await wrap(<OwnerBookingsScreen />);
    expect(await screen.findByText('Paid bookings of your cars appear here.')).toBeTruthy();
    await fireEvent.press(screen.getByText('On the road'));
    expect(owner.listOwnerBookings).toHaveBeenLastCalledWith('active');
  });

  it('explains that earnings are gross', async () => {
    mocked(owner.getEarnings).mockResolvedValue({
      year: 2026, currency: 'ZAR', basis: 'Gross: before any platform commission.',
      collected: '3600.00', refunded: '1200.00', net: '2400.00',
      months: [{ month: '2026-03', bookings: 1, collected: '1500.00', refunded: '1200.00', net: '300.00' }],
      bookings: [],
    });
    await wrap(<EarningsScreen />);
    expect(await screen.findByText('R 2 400.00')).toBeTruthy();
    expect(screen.getByText('Gross: before any platform commission.')).toBeTruthy();
    expect(screen.getByText('Mar · 1 booking')).toBeTruthy();
  });
});

describe('delivery actions', () => {
  function delivery(overrides: Partial<AssignedDelivery> = {}): AssignedDelivery {
    return {
      id: 'd1', booking_id: 'b1', booking_reference: 'BK1', booking_status: 'CONFIRMED', status: 'PENDING_SCHEDULE',
      scheduled_for: null, dropoff_address: '12 Long Street', started_at: null, delivered_at: null,
      delivery_person_first_name: 'Thabo', handover: null, return_record: null, exceptions: [],
      vehicle: { make: 'Toyota', model: 'Corolla', year: 2022 }, registration_number: 'CA123456',
      rental_start_at: '2099-10-20T08:00:00Z', rental_end_at: '2099-10-23T08:00:00Z',
      renter: { full_name: 'Naledi Dlamini', phone_number: '+27821234567' },
      ...overrides,
    };
  }

  beforeEach(() => {
    mockRouter.params = { id: 'd1' };
  });

  it('confirms a delivery time', async () => {
    mocked(deliveries.getMyDelivery).mockResolvedValue(delivery());
    await wrap(<DeliveryScreen />);
    await fireEvent.press(await screen.findByText(/^1 h before/));
    await fireEvent.press(screen.getByText('Confirm delivery time'));
    expect(deliveries.scheduleDelivery).toHaveBeenCalledWith('d1', '2099-10-20T07:00:00.000Z');
  });

  it('records the handover after checking the form', async () => {
    mocked(deliveries.getMyDelivery).mockResolvedValue(delivery({ status: 'EN_ROUTE', booking_status: 'IN_TRANSIT', scheduled_for: '2099-10-20T08:00:00Z' }));
    await wrap(<DeliveryScreen />);
    await fireEvent.press(await screen.findByText('Record handover'));
    expect(screen.getByText('Enter the odometer reading in km.')).toBeTruthy();

    await fireEvent.changeText(screen.getByLabelText('Odometer (km)'), '41200');
    await fireEvent.press(screen.getByText('Full'));
    await fireEvent.press(screen.getByText('Record handover'));
    expect(deliveries.recordHandover).toHaveBeenCalledWith('d1', { odometer_km: 41200, fuel_level: 'FULL', condition_notes: null });
  });

  it('will not record a return below the handover odometer', async () => {
    const handover = {
      kind: 'HANDOVER' as const, recorded_at: '2099-10-20T08:00:00Z', odometer_km: 41200, fuel_level: 'FULL' as const,
      condition_notes: null, renter_acknowledged_at: '2099-10-20T08:10:00Z', renter_notes: null, photos: [],
    };
    mocked(deliveries.getMyDelivery).mockResolvedValue(delivery({ status: 'DELIVERED', booking_status: 'RETURN_PENDING', handover }));
    await wrap(<DeliveryScreen />);
    expect(await screen.findByText(/The renter is ready to return the car/)).toBeTruthy();

    await fireEvent.changeText(screen.getByLabelText('Odometer (km)'), '41000');
    await fireEvent.press(screen.getByText('½'));
    await fireEvent.press(screen.getByText('Record return'));
    expect(screen.getByText('The odometer cannot be lower than at handover (41200 km).')).toBeTruthy();
    expect(deliveries.recordReturn).not.toHaveBeenCalled();
  });

  it('explains what a problem report does', async () => {
    mocked(deliveries.getMyDelivery).mockResolvedValue(delivery({ status: 'SCHEDULED', scheduled_for: '2099-10-20T08:00:00Z' }));
    await wrap(<DeliveryScreen />);
    await fireEvent.press(await screen.findByText('Report a problem'));
    expect(screen.getByText('The renter sees your note; the delivery continues.')).toBeTruthy();
    await fireEvent.press(screen.getByText('Address problem'));
    expect(screen.getByText(/This stops the delivery/)).toBeTruthy();

    await fireEvent.changeText(screen.getByLabelText('What happened?'), 'Gate code does not work');
    await fireEvent.press(screen.getByText('Send'));
    expect(deliveries.reportProblem).toHaveBeenCalledWith('d1', 'ADDRESS_PROBLEM', 'Gate code does not work');
  });
});
