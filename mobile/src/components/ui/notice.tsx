import Ionicons from '@expo/vector-icons/Ionicons';
import { Text, View } from 'react-native';

import { COLORS } from '@/constants/brand';

/** Inline information banner, e.g. to flag preview-only behaviour. */
export function Notice({ message }: { message: string }) {
  return (
    <View className="mb-5 flex-row items-start rounded-xl bg-brand-50 p-3">
      <Ionicons name="information-circle-outline" size={20} color={COLORS.brand} />
      <Text className="ml-2 flex-1 text-sm text-brand-700">{message}</Text>
    </View>
  );
}
