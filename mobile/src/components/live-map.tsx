import { Linking, Pressable, Text, View } from 'react-native';

import type { TrackedLocation } from '@/types/tracking';

/** Web fallback (react-native-maps has no web support): a link to the position in Google Maps. */
export function LiveMap({ location }: { location: TrackedLocation }) {
  const url = `https://www.google.com/maps/search/?api=1&query=${location.latitude},${location.longitude}`;
  return (
    <View className="rounded-xl bg-surface-muted p-4">
      <Text className="text-sm text-ink-muted">
        Car position: {location.latitude.toFixed(5)}, {location.longitude.toFixed(5)}
      </Text>
      <Pressable accessibilityRole="link" onPress={() => Linking.openURL(url)}>
        <Text className="mt-1 text-base font-semibold text-brand-600">Open in Google Maps</Text>
      </Pressable>
    </View>
  );
}
