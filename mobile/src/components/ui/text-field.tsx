import { Text, TextInput, View, type TextInputProps } from 'react-native';

import { COLORS } from '@/constants/brand';

interface TextFieldProps extends Omit<TextInputProps, 'className'> {
  label: string;
  error?: string | null;
}

export function TextField({ label, error, ...inputProps }: TextFieldProps) {
  return (
    <View className="mb-4">
      <Text className="mb-1.5 text-sm font-medium text-ink">{label}</Text>
      <TextInput
        accessibilityLabel={label}
        placeholderTextColor={COLORS.inkSubtle}
        className={`h-12 rounded-xl border bg-white px-4 text-base text-ink ${
          error ? 'border-danger' : 'border-surface-border'
        }`}
        {...inputProps}
      />
      {error ? <Text className="mt-1 text-sm text-danger">{error}</Text> : null}
    </View>
  );
}
