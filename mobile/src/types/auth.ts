export type Role = 'ADMIN' | 'OWNER' | 'RENTER';

export interface CurrentUser {
  id: string;
  email: string;
  full_name: string;
  phone_number: string | null;
  status: 'ACTIVE' | 'SUSPENDED' | 'DEACTIVATED';
  roles: Role[];
  email_verified: boolean;
  created_at: string;
}

export interface RegisterInput {
  email: string;
  password: string;
  full_name: string;
  phone_number?: string;
  account_type: 'RENTER' | 'OWNER';
}
