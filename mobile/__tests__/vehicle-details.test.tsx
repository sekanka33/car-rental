import { render, screen } from '@testing-library/react-native';
import { SafeAreaProvider } from 'react-native-safe-area-context';

import VehicleDetailsScreen from '@/app/vehicles/[id]';
import { ApiError } from '@/lib/api';
import { getAvailability, getVehicle } from '@/services/vehicles';

import { vehicleDetail } from './fixtures';

jest.mock('@/services/vehicles', () => ({ getVehicle: jest.fn(), getAvailability: jest.fn() }));
jest.mock('expo-router', () => ({
  Stack: { Screen: () => null },
  router: { back: jest.fn() },
  useLocalSearchParams: () => ({ id: 'v1' }),
}));

// The app's root layout provides safe-area insets; give the screen fixed phone metrics.
const METRICS = { frame: { x: 0, y: 0, width: 390, height: 844 }, insets: { top: 0, left: 0, right: 0, bottom: 0 } };
const renderScreen = () =>
  render(
    <SafeAreaProvider initialMetrics={METRICS}>
      <VehicleDetailsScreen />
    </SafeAreaProvider>,
  );

const mockGetVehicle = getVehicle as jest.MockedFunction<typeof getVehicle>;
const mockGetAvailability = getAvailability as jest.MockedFunction<typeof getAvailability>;

it('shows details, official price breakdown, owner first name and unavailable dates', async () => {
  mockGetVehicle.mockResolvedValue(vehicleDetail());
  mockGetAvailability.mockResolvedValue({
    window_start: '2026-10-13T00:00:00Z',
    window_end: '2026-12-12T00:00:00Z',
    unavailable: [{ start_at: '2026-10-20T08:00:00Z', end_at: '2026-10-23T08:00:00Z' }],
  });

  await renderScreen();

  expect(await screen.findByText('Toyota Corolla Cross')).toBeTruthy();
  expect(screen.getAllByText('R 750.00').length).toBeGreaterThan(0);
  expect(screen.getByText('R 150.00')).toBeTruthy();
  expect(screen.getByText('R 2 000.00')).toBeTruthy();
  expect(screen.getByText('Thabo · Johannesburg')).toBeTruthy();
  expect(await screen.findByText('20 Oct – 23 Oct 2026')).toBeTruthy();
  expect(mockGetVehicle).toHaveBeenCalledWith('v1');
});

it('shows a not-found state for unlisted vehicles', async () => {
  mockGetVehicle.mockRejectedValue(new ApiError('Vehicle not found.', 404, 'not_found'));
  mockGetAvailability.mockRejectedValue(new ApiError('Vehicle not found.', 404, 'not_found'));

  await renderScreen();

  expect(await screen.findByText('Vehicle not found')).toBeTruthy();
});
