import { useState } from 'react';
import { ScrollView, Text, View } from 'react-native';

import { Button } from '@/components/ui/button';
import { Chip } from '@/components/ui/chip';
import { Notice } from '@/components/ui/notice';
import { TextField } from '@/components/ui/text-field';
import { formatFuelType, formatTransmission } from '@/lib/format';
import { fieldErrors, formMessage } from '@/lib/form-errors';
import { PROVINCES, type VehicleInput } from '@/types/owner';
import type { FuelType, Transmission } from '@/types/vehicle';

const TRANSMISSIONS: Transmission[] = ['AUTOMATIC', 'MANUAL'];
const FUELS: FuelType[] = ['PETROL', 'DIESEL', 'HYBRID', 'ELECTRIC'];

type Draft = Record<
  'make' | 'model' | 'year' | 'registration_number' | 'vin' | 'colour' | 'seats' | 'city' | 'description',
  string
> & { transmission: Transmission | null; fuel_type: FuelType | null; province: string | null };

function toDraft(initial?: VehicleInput): Draft {
  return {
    make: initial?.make ?? '',
    model: initial?.model ?? '',
    year: initial ? String(initial.year) : '',
    registration_number: initial?.registration_number ?? '',
    vin: initial?.vin ?? '',
    colour: initial?.colour ?? '',
    seats: initial ? String(initial.seats) : '5',
    city: initial?.city ?? '',
    description: initial?.description ?? '',
    transmission: initial?.transmission ?? null,
    fuel_type: initial?.fuel_type ?? null,
    province: initial?.province ?? null,
  };
}

/** Checks what the phone can check; the backend validates everything again. */
export function validateVehicle(draft: Draft): { input: VehicleInput | null; errors: Record<string, string> } {
  const errors: Record<string, string> = {};
  const required = ['make', 'model', 'registration_number', 'vin', 'city'] as const;
  for (const key of required) if (!draft[key].trim()) errors[key] = 'Required.';
  const year = Number(draft.year);
  if (!/^\d{4}$/.test(draft.year) || year < 1981) errors.year = 'Enter a year like 2021.';
  const seats = Number(draft.seats);
  if (!/^\d{1,2}$/.test(draft.seats) || seats < 2 || seats > 16) errors.seats = 'Between 2 and 16.';
  const vin = draft.vin.replace(/\s/g, '').toUpperCase();
  if (draft.vin.trim() && !/^[A-HJ-NPR-Z0-9]{17}$/.test(vin)) {
    errors.vin = 'The VIN has 17 letters and digits (no I, O or Q).';
  }
  if (!draft.transmission) errors.transmission = 'Choose one.';
  if (!draft.fuel_type) errors.fuel_type = 'Choose one.';
  if (!draft.province) errors.province = 'Choose a province.';
  if (Object.keys(errors).length > 0) return { input: null, errors };
  return {
    errors,
    input: {
      make: draft.make.trim(),
      model: draft.model.trim(),
      year,
      registration_number: draft.registration_number.replace(/[\s-]/g, '').toUpperCase(),
      vin,
      colour: draft.colour.trim() || null,
      transmission: draft.transmission!,
      fuel_type: draft.fuel_type!,
      seats,
      city: draft.city.trim(),
      province: draft.province!,
      description: draft.description.trim() || null,
    },
  };
}

/**
 * Register or edit a car. No price fields: official prices are set by administrators.
 * `note` explains what saving does (e.g. that some changes need a new review).
 */
export function VehicleForm({
  initial,
  submitLabel,
  note,
  onSubmit,
}: {
  initial?: VehicleInput;
  submitLabel: string;
  note?: string;
  onSubmit: (input: VehicleInput) => Promise<void>;
}) {
  const [draft, setDraft] = useState<Draft>(() => toDraft(initial));
  const [errors, setErrors] = useState<Record<string, string>>({});
  const [message, setMessage] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const set = (key: keyof Draft) => (value: string) => setDraft((d) => ({ ...d, [key]: value }));

  const save = async () => {
    const { input, errors: found } = validateVehicle(draft);
    setErrors(found);
    if (!input) {
      setMessage('Please correct the highlighted fields.');
      return;
    }
    setBusy(true);
    setMessage(null);
    try {
      await onSubmit(input);
    } catch (e) {
      setErrors(fieldErrors(e));
      setMessage(formMessage(e, 'Could not save the car.'));
      setBusy(false);
    }
  };

  return (
    <View>
      {note ? (
        <View className="mb-4">
          <Notice tone="info" message={note} />
        </View>
      ) : null}
      <TextField label="Make" value={draft.make} onChangeText={set('make')} placeholder="Toyota" error={errors.make} />
      <TextField label="Model" value={draft.model} onChangeText={set('model')} placeholder="Corolla Cross" error={errors.model} />
      <View className="flex-row gap-3">
        <View className="flex-1">
          <TextField label="Year" value={draft.year} onChangeText={set('year')} keyboardType="number-pad" maxLength={4} error={errors.year} />
        </View>
        <View className="flex-1">
          <TextField label="Seats" value={draft.seats} onChangeText={set('seats')} keyboardType="number-pad" maxLength={2} error={errors.seats} />
        </View>
      </View>
      <TextField
        label="Registration number"
        value={draft.registration_number}
        onChangeText={set('registration_number')}
        autoCapitalize="characters"
        placeholder="CA 123-456"
        error={errors.registration_number}
      />
      <TextField label="VIN" value={draft.vin} onChangeText={set('vin')} autoCapitalize="characters" maxLength={20} error={errors.vin} />
      <TextField label="Colour (optional)" value={draft.colour} onChangeText={set('colour')} error={errors.colour} />

      <Text className="mb-1.5 text-sm font-medium text-ink">Transmission</Text>
      <View className="mb-1 flex-row">
        {TRANSMISSIONS.map((t) => (
          <Chip key={t} label={formatTransmission(t)} selected={draft.transmission === t} onPress={() => setDraft((d) => ({ ...d, transmission: t }))} />
        ))}
      </View>
      {errors.transmission ? <Text className="mb-2 text-sm text-danger">{errors.transmission}</Text> : <View className="mb-3" />}

      <Text className="mb-1.5 text-sm font-medium text-ink">Fuel</Text>
      <View className="mb-1 flex-row flex-wrap gap-y-2">
        {FUELS.map((f) => (
          <Chip key={f} label={formatFuelType(f)} selected={draft.fuel_type === f} onPress={() => setDraft((d) => ({ ...d, fuel_type: f }))} />
        ))}
      </View>
      {errors.fuel_type ? <Text className="mb-2 text-sm text-danger">{errors.fuel_type}</Text> : <View className="mb-3" />}

      <TextField label="City or town" value={draft.city} onChangeText={set('city')} placeholder="Cape Town" error={errors.city} />
      <Text className="mb-1.5 text-sm font-medium text-ink">Province</Text>
      <ScrollView horizontal showsHorizontalScrollIndicator={false} className="mb-1">
        {PROVINCES.map((p) => (
          <Chip key={p} label={p} selected={draft.province === p} onPress={() => setDraft((d) => ({ ...d, province: p }))} />
        ))}
      </ScrollView>
      {errors.province ? <Text className="mb-2 text-sm text-danger">{errors.province}</Text> : <View className="mb-3" />}

      <TextField
        label="Description (optional)"
        value={draft.description}
        onChangeText={set('description')}
        multiline
        style={{ height: 96, paddingTop: 12, textAlignVertical: 'top' }}
        error={errors.description}
      />
      {message ? (
        <View className="mb-3">
          <Notice tone="danger" message={message} />
        </View>
      ) : null}
      <Button label={submitLabel} loading={busy} onPress={save} />
    </View>
  );
}
