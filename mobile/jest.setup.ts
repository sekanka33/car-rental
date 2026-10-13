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
