import { router, Stack } from 'expo-router';

import { Screen } from '@/components/ui/screen';
import { VehicleForm } from '@/components/vehicle-form';
import { registerVehicle } from '@/services/owner';

export default function RegisterVehicleScreen() {
  return (
    <Screen scroll>
      <Stack.Screen options={{ title: 'Register a car' }} />
      <VehicleForm
        submitLabel="Save and continue"
        note="Your car is saved as a draft. Next you add at least 3 photos and the registration certificate, licence disc and proof of insurance, then submit it for review. Prices are set by CarHire SA."
        onSubmit={async (input) => {
          const vehicle = await registerVehicle(input);
          router.replace({ pathname: '/owner/vehicles/[id]', params: { id: vehicle.id } });
        }}
      />
    </Screen>
  );
}
