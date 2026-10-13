/**
 * Public marketplace types. They mirror the backend's /api/v1/vehicles responses
 * (snake_case kept as returned). Money is always a decimal string, never a float.
 */
export type Transmission = 'AUTOMATIC' | 'MANUAL';
export type FuelType = 'PETROL' | 'DIESEL' | 'HYBRID' | 'ELECTRIC';
export type SortOrder = 'price_asc' | 'price_desc' | 'newest';

export interface PublicPrice {
  /** Official daily rate set by an administrator, e.g. "650.00" (ZAR, VAT-inclusive). */
  daily_rate: string;
  delivery_fee: string;
  deposit_amount: string;
  currency: 'ZAR';
}

export interface PublicOwner {
  /** Owners are shown by first name and area only, for privacy. */
  first_name: string;
  city: string;
  province: string;
}

export interface MarketplaceVehicle {
  id: string;
  make: string;
  model: string;
  year: number;
  transmission: Transmission;
  fuel_type: FuelType;
  seats: number;
  colour: string | null;
  city: string;
  province: string;
  price: PublicPrice;
  owner: PublicOwner;
  primary_photo_url: string | null;
  photo_count: number;
}

export interface MarketplaceVehicleDetail extends MarketplaceVehicle {
  description: string | null;
  photos: { id: string; url: string }[];
}

export interface SearchResponse {
  items: MarketplaceVehicle[];
  total: number;
  limit: number;
  offset: number;
}

export interface UnavailablePeriod {
  start_at: string;
  end_at: string;
}

export interface Availability {
  window_start: string;
  window_end: string;
  unavailable: UnavailablePeriod[];
}

export interface SearchFilters {
  q?: string;
  transmission?: Transmission;
  fuel_type?: FuelType;
  max_daily_rate?: string;
  sort?: SortOrder;
}
