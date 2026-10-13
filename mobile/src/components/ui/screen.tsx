import type { ReactNode } from 'react';
import { ScrollView, View } from 'react-native';
import { useSafeAreaInsets } from 'react-native-safe-area-context';

interface ScreenProps {
  children: ReactNode;
  /** Wrap content in a ScrollView (forms, long details pages). */
  scroll?: boolean;
  /** Apply top safe-area padding (screens without a navigation header). */
  edgeTop?: boolean;
  className?: string;
}

export function Screen({ children, scroll = false, edgeTop = false, className = '' }: ScreenProps) {
  const insets = useSafeAreaInsets();
  const padding = { paddingTop: edgeTop ? insets.top : 0, paddingBottom: insets.bottom };

  if (scroll) {
    return (
      <ScrollView
        className="flex-1 bg-surface"
        contentContainerStyle={padding}
        contentContainerClassName={`px-5 py-6 ${className}`}
        keyboardShouldPersistTaps="handled">
        {children}
      </ScrollView>
    );
  }

  return (
    <View className={`flex-1 bg-surface ${className}`} style={padding}>
      {children}
    </View>
  );
}
