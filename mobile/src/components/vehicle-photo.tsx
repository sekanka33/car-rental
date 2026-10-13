import Ionicons from '@expo/vector-icons/Ionicons';
import { Text, View } from 'react-native';

import { COLORS } from '@/constants/brand';

/**
 * Placeholder until vehicle photographs are served by the backend (Stage 07/09).
 */
export function VehiclePhoto({ className = 'h-44' }: { className?: string }) {
  return (
    <View className={`w-full items-center justify-center rounded-2xl bg-surface-muted ${className}`}>
      <Ionicons name="car-sport-outline" size={56} color={COLORS.inkSubtle} />
      <Text className="mt-1 text-xs text-ink-subtle">Photo coming soon</Text>
    </View>
  );
}
