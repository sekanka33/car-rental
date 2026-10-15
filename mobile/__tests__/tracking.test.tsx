import { act, render, renderHook, screen, waitFor } from '@testing-library/react-native';
import * as Location from 'expo-location';

import { LiveTracking } from '@/components/live-tracking';
import { useDeliveryTracking } from '@/hooks/use-delivery-tracking';
import { useLocationSharing } from '@/hooks/use-location-sharing';
import { ApiError, getAccessToken } from '@/lib/api';
import { sendLocation } from '@/services/owner-deliveries';
import type { TrackingState } from '@/types/tracking';

jest.mock('@/lib/api', () => {
  const actual = jest.requireActual('@/lib/api');
  return { ...actual, getAccessToken: jest.fn(), websocketUrl: (path: string) => `ws://api.test${path}` };
});
jest.mock('@/services/owner-deliveries', () => ({ sendLocation: jest.fn() }));
jest.mock('expo-location', () => ({
  Accuracy: { High: 4 },
  requestForegroundPermissionsAsync: jest.fn(),
  watchPositionAsync: jest.fn(),
}));

/** Minimal stand-in for the browser/React Native WebSocket. */
class FakeSocket {
  static all: FakeSocket[] = [];
  sent: string[] = [];
  onopen: (() => void) | null = null;
  onmessage: ((event: { data: string }) => void) | null = null;
  onclose: ((event: { code: number }) => void) | null = null;
  closed = false;
  constructor(readonly url: string) {
    FakeSocket.all.push(this);
  }
  send(data: string) {
    this.sent.push(data);
  }
  close() {
    this.closed = true;
  }
  open() {
    return act(() => this.onopen?.());
  }
  message(body: object) {
    return act(() => this.onmessage?.({ data: JSON.stringify(body) }));
  }
  serverClose(code: number) {
    return act(() => this.onclose?.({ code }));
  }
}

const last = () => FakeSocket.all.at(-1)!;

function tracking(overrides: Partial<TrackingState> = {}): TrackingState {
  return {
    delivery_id: 'd1', status: 'EN_ROUTE', booking_status: 'IN_TRANSIT', scheduled_for: null, tracking_active: true,
    location: {
      latitude: -33.91, longitude: 18.42, accuracy_m: 8, heading: null, speed_mps: null,
      recorded_at: new Date().toISOString(), received_at: new Date().toISOString(),
    },
    eta: { seconds: 720, distance_m: 4200, computed_at: '', arrives_at: '' },
    ...overrides,
  };
}

beforeEach(() => {
  FakeSocket.all = [];
  (globalThis as unknown as { WebSocket: unknown }).WebSocket = FakeSocket;
  (getAccessToken as jest.Mock).mockImplementation(async ({ renew } = {}) => (renew ? 'renewed-token' : 'token'));
});

describe('live tracking socket', () => {
  it('authenticates in the first message, never in the URL', async () => {
    const { result } = await renderHook(() => useDeliveryTracking('d1'));
    await waitFor(() => expect(FakeSocket.all).toHaveLength(1));

    await last().open();
    await last().message({ type: 'snapshot', ...tracking() });

    expect(last().url).toBe('ws://api.test/api/v1/deliveries/d1/live');
    expect(last().url).not.toContain('token');
    expect(JSON.parse(last().sent[0])).toEqual({ type: 'auth', token: 'token' });
    expect(result.current.connection).toBe('live');
    expect(result.current.state?.location?.latitude).toBe(-33.91);
  });

  it('refreshes the session once when the token expired, then reconnects', async () => {
    const { result } = await renderHook(() => useDeliveryTracking('d1'));
    await waitFor(() => expect(FakeSocket.all).toHaveLength(1));

    await last().serverClose(4401);
    await waitFor(() => expect(FakeSocket.all).toHaveLength(2));
    await last().open();

    expect(getAccessToken).toHaveBeenLastCalledWith({ renew: true });
    expect(JSON.parse(last().sent[0]).token).toBe('renewed-token');
    await last().serverClose(4401); // still refused: give up rather than loop
    await waitFor(() => expect(result.current.connection).toBe('unavailable'));
    expect(FakeSocket.all).toHaveLength(2);
  });

  it('stops when tracking ends or access is refused', async () => {
    const ended = await renderHook(() => useDeliveryTracking('d1'));
    await waitFor(() => expect(FakeSocket.all).toHaveLength(1));
    await last().serverClose(4000);
    expect(ended.result.current.connection).toBe('ended');

    const refused = await renderHook(() => useDeliveryTracking('d2'));
    await waitFor(() => expect(FakeSocket.all).toHaveLength(2));
    await last().serverClose(4403);
    expect(refused.result.current.connection).toBe('unavailable');
    expect(FakeSocket.all).toHaveLength(2);
  });

  it('reconnects with backoff after a dropped connection', async () => {
    jest.useFakeTimers();
    try {
      const { result } = await renderHook(() => useDeliveryTracking('d1'));
      await waitFor(() => expect(FakeSocket.all).toHaveLength(1));
      await last().serverClose(1006);
      expect(result.current.connection).toBe('reconnecting');

      await act(async () => jest.advanceTimersByTime(999));
      expect(FakeSocket.all).toHaveLength(1);
      await act(async () => jest.advanceTimersByTime(1));
      await waitFor(() => expect(FakeSocket.all).toHaveLength(2));

      await last().serverClose(1006); // second drop waits twice as long
      await act(async () => jest.advanceTimersByTime(1999));
      expect(FakeSocket.all).toHaveLength(2);
      await act(async () => jest.advanceTimersByTime(1));
      await waitFor(() => expect(FakeSocket.all).toHaveLength(3));
    } finally {
      jest.useRealTimers();
    }
  });

  it('closes the socket when the screen goes away', async () => {
    const { unmount } = await renderHook(() => useDeliveryTracking('d1'));
    await waitFor(() => expect(FakeSocket.all).toHaveLength(1));
    await unmount();
    expect(last().closed).toBe(true);
  });
});

describe('live tracking panel', () => {
  it('shows the car, the ETA and how fresh the position is', async () => {
    await render(<LiveTracking deliveryId="d1" status="EN_ROUTE" onStatusChange={jest.fn()} />);
    await waitFor(() => expect(FakeSocket.all).toHaveLength(1));
    await last().message({ type: 'snapshot', ...tracking() });

    expect(await screen.findByText('marker:Your car')).toBeTruthy();
    expect(screen.getByText('Arriving in about 12 min (4.2 km)')).toBeTruthy();
    expect(screen.getByText(/^Updated \d+ s ago$/)).toBeTruthy();
    expect(screen.queryByText(/No new position/)).toBeNull();
  });

  it('warns when the position is stale', async () => {
    await render(<LiveTracking deliveryId="d1" status="EN_ROUTE" onStatusChange={jest.fn()} />);
    await waitFor(() => expect(FakeSocket.all).toHaveLength(1));
    const old = new Date(Date.now() - 3 * 60_000).toISOString();
    await last().message({ type: 'snapshot', ...tracking({ location: { ...tracking().location!, received_at: old } }) });

    expect(await screen.findByText(/No new position for a while/)).toBeTruthy();
    expect(screen.getByText('Updated 3 min ago')).toBeTruthy();
  });

  it('asks the screen to reload when the delivery moves on', async () => {
    const onStatusChange = jest.fn();
    await render(<LiveTracking deliveryId="d1" status="EN_ROUTE" onStatusChange={onStatusChange} />);
    await waitFor(() => expect(FakeSocket.all).toHaveLength(1));

    await last().message({ type: 'status', ...tracking({ status: 'DELIVERED', tracking_active: false, location: null }) });

    await waitFor(() => expect(onStatusChange).toHaveBeenCalled());
  });
});

describe('sharing location (delivery person)', () => {
  const position = { coords: { latitude: -33.9, longitude: 18.4, accuracy: 5, heading: -1, speed: 12.5 }, timestamp: 1_760_000_000_000 };

  it('asks for permission and explains a refusal', async () => {
    (Location.requestForegroundPermissionsAsync as jest.Mock).mockResolvedValue({ status: 'denied' });
    const { result } = await renderHook(() => useLocationSharing('d1'));

    await act(() => result.current.start());

    await waitFor(() => expect(result.current.error).toMatch(/Allow location access/));
    expect(result.current.sharing).toBe(false);
    expect(Location.watchPositionAsync).not.toHaveBeenCalled();
  });

  it('sends positions and stops when the delivery is no longer on its way', async () => {
    (Location.requestForegroundPermissionsAsync as jest.Mock).mockResolvedValue({ status: 'granted' });
    const remove = jest.fn();
    let onPosition: (p: typeof position) => Promise<void> = async () => undefined;
    (Location.watchPositionAsync as jest.Mock).mockImplementation(async (_options, callback) => {
      onPosition = callback;
      return { remove };
    });
    (sendLocation as jest.Mock).mockResolvedValueOnce(undefined).mockRejectedValueOnce(new ApiError('Not on its way', 409, 'tracking_not_active'));
    const { result } = await renderHook(() => useLocationSharing('d1'));

    await act(() => result.current.start());
    await waitFor(() => expect(Location.watchPositionAsync).toHaveBeenCalled());
    await act(() => onPosition(position));

    expect(sendLocation).toHaveBeenCalledWith('d1', {
      latitude: -33.9, longitude: 18.4, accuracy_m: 5, heading: null, speed_mps: 12.5,
      recorded_at: new Date(1_760_000_000_000).toISOString(),
    });
    expect(result.current.lastSentAt).not.toBeNull();

    await act(() => onPosition(position)); // too soon after the last send: skipped
    expect(sendLocation).toHaveBeenCalledTimes(1);

    const realNow = Date.now;
    Date.now = () => realNow() + 11_000;
    try {
      await act(() => onPosition(position));
    } finally {
      Date.now = realNow;
    }
    await waitFor(() => expect(result.current.ended).toBe(true));
    expect(result.current.sharing).toBe(false);
    expect(remove).toHaveBeenCalled();
  });
});
