import Ionicons from '@expo/vector-icons/Ionicons';
import { Image } from 'expo-image';
import { useState } from 'react';
import { Text, View } from 'react-native';

import { COLORS } from '@/constants/brand';
import { resolveApiUrl } from '@/lib/api';

interface VehiclePhotoProps {
  /** Photo path returned by the API, or null when the vehicle has no photos. */
  url: string | null;
  className?: string;
  accessibilityLabel?: string;
}

export function VehiclePhoto({ url, className = 'h-44', accessibilityLabel }: VehiclePhotoProps) {
  const [failed, setFailed] = useState(false);

  if (!url || failed) {
    return (
      <View className={`w-full items-center justify-center rounded-2xl bg-surface-muted ${className}`}>
        <Ionicons name="car-sport-outline" size={56} color={COLORS.inkSubtle} />
        <Text className="mt-1 text-xs text-ink-subtle">{url ? 'Photo unavailable' : 'No photo yet'}</Text>
      </View>
    );
  }
  return (
    <View className={`w-full overflow-hidden rounded-2xl bg-surface-muted ${className}`}>
      <Image
        source={{ uri: resolveApiUrl(url) }}
        style={{ width: '100%', height: '100%' }}
        contentFit="cover"
        transition={150}
        accessibilityLabel={accessibilityLabel}
        onError={() => setFailed(true)}
      />
    </View>
  );
}
