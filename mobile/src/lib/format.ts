/**
 * Formats a ZAR decimal string (e.g. "1250.00") as "R 1 250.00".
 * Works on the string directly so amounts are never converted to floats.
 */
export function formatZar(amount: string): string {
  const match = /^(-?)(\d+)(?:\.(\d{1,2}))?$/.exec(amount.trim());
  if (!match) {
    throw new Error(`Invalid ZAR amount: ${amount}`);
  }
  const [, sign, whole, fraction = ''] = match;
  const grouped = whole.replace(/\B(?=(\d{3})+(?!\d))/g, ' ');
  return `${sign}R ${grouped}.${fraction.padEnd(2, '0')}`;
}

const TRANSMISSION_LABELS = { AUTOMATIC: 'Automatic', MANUAL: 'Manual' } as const;
const FUEL_LABELS = {
  PETROL: 'Petrol',
  DIESEL: 'Diesel',
  HYBRID: 'Hybrid',
  ELECTRIC: 'Electric',
} as const;

export const formatTransmission = (value: keyof typeof TRANSMISSION_LABELS) =>
  TRANSMISSION_LABELS[value];
export const formatFuelType = (value: keyof typeof FUEL_LABELS) => FUEL_LABELS[value];
