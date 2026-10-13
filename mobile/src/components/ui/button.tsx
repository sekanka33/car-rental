import { ActivityIndicator, Pressable, Text } from 'react-native';

import { COLORS } from '@/constants/brand';

type Variant = 'primary' | 'secondary' | 'ghost';

interface ButtonProps {
  label: string;
  onPress?: () => void;
  variant?: Variant;
  disabled?: boolean;
  loading?: boolean;
  className?: string;
}

const CONTAINER: Record<Variant, string> = {
  primary: 'bg-brand-500 active:bg-brand-600',
  secondary: 'border border-brand-500 bg-white active:bg-brand-50',
  ghost: 'bg-transparent active:bg-surface-muted',
};

const LABEL: Record<Variant, string> = {
  primary: 'text-white',
  secondary: 'text-brand-600',
  ghost: 'text-brand-600',
};

export function Button({
  label,
  onPress,
  variant = 'primary',
  disabled = false,
  loading = false,
  className = '',
}: ButtonProps) {
  const inactive = disabled || loading;
  return (
    <Pressable
      accessibilityRole="button"
      accessibilityState={{ disabled: inactive, busy: loading }}
      disabled={inactive}
      onPress={onPress}
      className={`h-12 flex-row items-center justify-center rounded-xl px-5 ${CONTAINER[variant]} ${
        inactive ? 'opacity-50' : ''
      } ${className}`}>
      {loading ? (
        <ActivityIndicator color={variant === 'primary' ? COLORS.white : COLORS.brand} />
      ) : (
        <Text className={`text-base font-semibold ${LABEL[variant]}`}>{label}</Text>
      )}
    </Pressable>
  );
}
