import type { MarketplaceVehicle, MarketplaceVehicleDetail } from '@/types/vehicle';

export function vehicle(overrides: Partial<MarketplaceVehicle> = {}): MarketplaceVehicle {
  return {
    id: 'v1',
    make: 'Toyota',
    model: 'Corolla Cross',
    year: 2023,
    transmission: 'AUTOMATIC',
    fuel_type: 'PETROL',
    seats: 5,
    colour: null,
    city: 'Johannesburg',
    province: 'Gauteng',
    price: { daily_rate: '750.00', delivery_fee: '150.00', deposit_amount: '2000.00', currency: 'ZAR' },
    owner: { first_name: 'Thabo', city: 'Johannesburg', province: 'Gauteng' },
    primary_photo_url: '/api/v1/vehicles/v1/photos/p1',
    photo_count: 1,
    ...overrides,
  };
}

export function vehicleDetail(overrides: Partial<MarketplaceVehicleDetail> = {}): MarketplaceVehicleDetail {
  return {
    ...vehicle(),
    description: 'Clean and reliable.',
    photos: [{ id: 'p1', url: '/api/v1/vehicles/v1/photos/p1' }],
    ...overrides,
  };
}
