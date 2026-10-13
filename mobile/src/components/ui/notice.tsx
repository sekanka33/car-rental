import Ionicons from '@expo/vector-icons/Ionicons';
import { Text, View } from 'react-native';

import { COLORS } from '@/constants/brand';

const TONES = {
  info: { box: 'bg-brand-50', text: 'text-brand-700', icon: 'information-circle-outline', color: COLORS.brand },
  danger: { box: 'bg-red-50', text: 'text-danger', icon: 'alert-circle-outline', color: COLORS.danger },
  success: { box: 'bg-green-50', text: 'text-success', icon: 'checkmark-circle-outline', color: '#15803D' },
} as const;

/** Inline banner for information, success or a form-level error. */
export function Notice({ message, tone = 'info' }: { message: string; tone?: keyof typeof TONES }) {
  const style = TONES[tone];
  return (
    <View className={`mb-5 flex-row items-start rounded-xl p-3 ${style.box}`} accessibilityRole="alert">
      <Ionicons name={style.icon} size={20} color={style.color} />
      <Text className={`ml-2 flex-1 text-sm ${style.text}`}>{message}</Text>
    </View>
  );
}
