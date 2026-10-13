/** Marketplace data from the FastAPI backend (/api/v1/vehicles). */
import { apiGet } from '@/lib/api';
import type {
  Availability,
  MarketplaceVehicleDetail,
  SearchFilters,
  SearchResponse,
} from '@/types/vehicle';

export const PAGE_SIZE = 20;

export function searchVehicles(filters: SearchFilters, offset = 0): Promise<SearchResponse> {
  return apiGet<SearchResponse>('/api/v1/vehicles', { ...filters, limit: PAGE_SIZE, offset });
}

export function getVehicle(id: string): Promise<MarketplaceVehicleDetail> {
  return apiGet<MarketplaceVehicleDetail>(`/api/v1/vehicles/${encodeURIComponent(id)}`);
}

export function getAvailability(id: string): Promise<Availability> {
  return apiGet<Availability>(`/api/v1/vehicles/${encodeURIComponent(id)}/availability`);
}
