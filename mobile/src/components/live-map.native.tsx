import MapView, { Marker } from 'react-native-maps';

import type { TrackedLocation } from '@/types/tracking';

/** Native map centred on the car (Apple Maps on iOS, Google Maps on Android). */
export function LiveMap({ location }: { location: TrackedLocation }) {
  const coordinate = { latitude: location.latitude, longitude: location.longitude };
  return (
    <MapView
      style={{ height: 220, borderRadius: 12 }}
      region={{ ...coordinate, latitudeDelta: 0.02, longitudeDelta: 0.02 }}
      accessibilityLabel="Map showing where your car is"
    >
      <Marker coordinate={coordinate} title="Your car" />
    </MapView>
  );
}
