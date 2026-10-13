/**
 * Public marketplace vehicle shape. Mirrors what the backend will return for
 * approved listings (Stage 09). Money is a decimal string, never a float.
 */
export type Transmission = 'AUTOMATIC' | 'MANUAL';
export type FuelType = 'PETROL' | 'DIESEL' | 'HYBRID' | 'ELECTRIC';

export interface Vehicle {
  id: string;
  make: string;
  model: string;
  year: number;
  transmission: Transmission;
  fuelType: FuelType;
  seats: number;
  city: string;
  province: string;
  /** Official daily rate set by the administrator, e.g. "650.00". */
  dailyRate: string;
  currency: 'ZAR';
  /** Owners are shown by first name only for privacy. */
  ownerFirstName: string;
  description: string;
  features: string[];
}
