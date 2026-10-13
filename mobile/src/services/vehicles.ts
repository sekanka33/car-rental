/**
 * Vehicle data access. Stage 02 reads PROTOTYPE sample data; Stage 09 replaces
 * these functions with calls to the FastAPI backend, keeping the same signatures.
 */
import { SAMPLE_VEHICLES } from '@/data/sample-vehicles';
import type { Vehicle } from '@/types/vehicle';

export async function listVehicles(): Promise<Vehicle[]> {
  return SAMPLE_VEHICLES;
}

export async function getVehicle(id: string): Promise<Vehicle | null> {
  return SAMPLE_VEHICLES.find((vehicle) => vehicle.id === id) ?? null;
}
