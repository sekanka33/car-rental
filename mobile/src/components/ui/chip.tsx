import { Pressable, Text } from 'react-native';

interface ChipProps {
  label: string;
  selected: boolean;
  onPress: () => void;
}

export function Chip({ label, selected, onPress }: ChipProps) {
  return (
    <Pressable
      accessibilityRole="button"
      accessibilityState={{ selected }}
      onPress={onPress}
      className={`mr-2 rounded-full border px-4 py-2 ${
        selected ? 'border-brand-500 bg-brand-500' : 'border-surface-border bg-white active:bg-surface-muted'
      }`}>
      <Text className={`text-sm font-medium ${selected ? 'text-white' : 'text-ink'}`}>{label}</Text>
    </Pressable>
  );
}
