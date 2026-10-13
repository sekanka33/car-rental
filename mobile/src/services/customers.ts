import { apiRequest } from '@/lib/api';
import type { CustomerProfile } from '@/types/profile';

export function getCustomerProfile(): Promise<CustomerProfile> {
  return apiRequest<CustomerProfile>('GET', '/api/v1/customers/me/profile', { auth: true });
}
