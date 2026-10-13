import Ionicons from '@expo/vector-icons/Ionicons';
import type { ComponentProps } from 'react';
import { ActivityIndicator, Text, View } from 'react-native';

import { COLORS } from '@/constants/brand';

import { Button } from './button';

type IconName = ComponentProps<typeof Ionicons>['name'];

export function LoadingState({ message = 'Loading…' }: { message?: string }) {
  return (
    <View className="flex-1 items-center justify-center p-8" accessibilityRole="progressbar">
      <ActivityIndicator size="large" color={COLORS.brand} />
      <Text className="mt-3 text-base text-ink-muted">{message}</Text>
    </View>
  );
}

interface MessageStateProps {
  title: string;
  message?: string;
  icon?: IconName;
  actionLabel?: string;
  onAction?: () => void;
}

function MessageState({ title, message, icon, actionLabel, onAction, tone }: MessageStateProps & { tone: string }) {
  return (
    <View className="flex-1 items-center justify-center p-8">
      {icon ? <Ionicons name={icon} size={48} color={tone} /> : null}
      <Text className="mt-4 text-center text-lg font-semibold text-ink">{title}</Text>
      {message ? <Text className="mt-2 text-center text-base text-ink-muted">{message}</Text> : null}
      {actionLabel && onAction ? (
        <Button label={actionLabel} onPress={onAction} variant="secondary" className="mt-6" />
      ) : null}
    </View>
  );
}

export function EmptyState(props: MessageStateProps) {
  return <MessageState icon="file-tray-outline" {...props} tone={COLORS.inkSubtle} />;
}

export function ErrorState({
  title = 'Something went wrong',
  actionLabel = 'Try again',
  ...props
}: Partial<MessageStateProps>) {
  return (
    <MessageState
      icon="alert-circle-outline"
      title={title}
      actionLabel={actionLabel}
      {...props}
      tone={COLORS.danger}
    />
  );
}
