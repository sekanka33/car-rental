/// <reference types="jest" />
/**
 * Test-only setup. Icon fonts are native assets that do not exist under Jest, so the
 * icon component is replaced by a plain element that renders the icon's name.
 */
jest.mock('@expo/vector-icons/Ionicons', () => {
  const React = jest.requireActual('react');
  const { Text } = jest.requireActual('react-native');
  const Icon = ({ name }: { name: string }) => React.createElement(Text, null, `icon:${name}`);
  return { __esModule: true, default: Icon };
});

// expo-secure-store is native-only; tests use an in-memory stand-in.
jest.mock('expo-secure-store', () => {
  const store = new Map<string, string>();
  return {
    getItemAsync: jest.fn(async (key: string) => store.get(key) ?? null),
    setItemAsync: jest.fn(async (key: string, value: string) => void store.set(key, value)),
    deleteItemAsync: jest.fn(async (key: string) => void store.delete(key)),
  };
});
