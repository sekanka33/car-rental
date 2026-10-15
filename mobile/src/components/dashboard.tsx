import Ionicons from '@expo/vector-icons/Ionicons';
import type { ComponentProps } from 'react';
import { Pressable, Text, View } from 'react-native';

import { COLORS } from '@/constants/brand';

type IconName = ComponentProps<typeof Ionicons>['name'];

export function SectionTitle({ title }: { title: string }) {
  return <Text className="mb-2 mt-6 text-sm font-semibold uppercase text-ink-subtle">{title}</Text>;
}

/** A number with a caption, e.g. "3 / Upcoming bookings". Tappable when `onPress` is given. */
export function StatTile({ value, label, onPress }: { value: string; label: string; onPress?: () => void }) {
  return (
    <Pressable
      accessibilityRole={onPress ? 'button' : undefined}
      accessibilityLabel={`${label}: ${value}`}
      disabled={!onPress}
      onPress={onPress}
      className="flex-1 rounded-2xl border border-surface-border bg-white p-4 active:bg-surface-muted">
      <Text className="text-2xl font-bold text-ink">{value}</Text>
      <Text className="mt-1 text-sm text-ink-muted">{label}</Text>
    </Pressable>
  );
}

/** A row that leads somewhere: an icon, a title, an optional detail and a chevron. */
export function ActionRow({
  icon,
  title,
  detail,
  tone = 'normal',
  onPress,
}: {
  icon: IconName;
  title: string;
  detail?: string;
  tone?: 'normal' | 'attention';
  onPress: () => void;
}) {
  const color = tone === 'attention' ? COLORS.warning : COLORS.brand;
  return (
    <Pressable
      accessibilityRole="button"
      onPress={onPress}
      className="mb-2 flex-row items-center rounded-2xl border border-surface-border bg-white p-4 active:bg-surface-muted">
      <Ionicons name={icon} size={22} color={color} />
      <View className="ml-3 flex-1">
        <Text className="text-base font-semibold text-ink">{title}</Text>
        {detail ? <Text className="mt-0.5 text-sm text-ink-muted">{detail}</Text> : null}
      </View>
      <Ionicons name="chevron-forward" size={18} color={COLORS.inkSubtle} />
    </Pressable>
  );
}
