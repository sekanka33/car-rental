import { Text, View } from 'react-native';

export type BadgeTone = 'neutral' | 'info' | 'success' | 'warning' | 'danger';

const TONES: Record<BadgeTone, { container: string; label: string }> = {
  neutral: { container: 'bg-surface-muted', label: 'text-ink-muted' },
  info: { container: 'bg-brand-50', label: 'text-brand-700' },
  success: { container: 'bg-green-50', label: 'text-success' },
  warning: { container: 'bg-amber-50', label: 'text-warning' },
  danger: { container: 'bg-red-50', label: 'text-danger' },
};

export function Badge({ label, tone = 'neutral' }: { label: string; tone?: BadgeTone }) {
  return (
    <View className={`self-start rounded-full px-3 py-1 ${TONES[tone].container}`}>
      <Text className={`text-xs font-semibold ${TONES[tone].label}`}>{label}</Text>
    </View>
  );
}
