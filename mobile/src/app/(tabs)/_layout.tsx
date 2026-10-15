import Ionicons from '@expo/vector-icons/Ionicons';
import { Tabs } from 'expo-router';

import { COLORS } from '@/constants/brand';
import { useAuth } from '@/context/auth';
import { useUnreadCount } from '@/hooks/use-unread-count';

export default function TabsLayout() {
  const { state } = useAuth();
  const roles = state.status === 'signedIn' ? state.user.roles : [];
  // Signed-out visitors see Bookings (it asks them to log in); owner-only accounts do not.
  const showBookings = roles.length === 0 || roles.includes('RENTER');
  const showOwner = roles.includes('OWNER');
  const unread = useUnreadCount(state.status === 'signedIn');
  return (
    <Tabs
      screenOptions={{
        tabBarActiveTintColor: COLORS.brand,
        tabBarInactiveTintColor: COLORS.inkMuted,
        headerTitleStyle: { fontWeight: '600' },
      }}>
      <Tabs.Screen
        name="home"
        options={{
          title: 'Find a car',
          tabBarLabel: 'Home',
          tabBarIcon: ({ color, size }) => <Ionicons name="search" size={size} color={color} />,
        }}
      />
      <Tabs.Screen
        name="bookings"
        options={{
          href: showBookings ? undefined : null,
          title: 'My bookings',
          tabBarLabel: 'Bookings',
          tabBarIcon: ({ color, size }) => <Ionicons name="calendar-outline" size={size} color={color} />,
        }}
      />
      <Tabs.Screen
        name="owner"
        options={{
          href: showOwner ? undefined : null,
          title: 'Owner dashboard',
          tabBarLabel: 'My cars',
          tabBarIcon: ({ color, size }) => <Ionicons name="car-sport-outline" size={size} color={color} />,
        }}
      />
      <Tabs.Screen
        name="profile"
        options={{
          title: 'My profile',
          tabBarLabel: 'Profile',
          tabBarBadge: unread > 0 ? (unread > 9 ? '9+' : unread) : undefined,
          tabBarIcon: ({ color, size }) => (
            <Ionicons name="person-circle-outline" size={size} color={color} />
          ),
        }}
      />
    </Tabs>
  );
}
