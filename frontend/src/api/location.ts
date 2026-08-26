import { apiClient } from './client';
import { ApiResponse } from '@/types/api';
import { LocationUpdate } from '@/types/location';

/**
 * Post one GPS observation.
 *
 * The frontend never sends a status or a presence decision - only raw
 * telemetry. `client_event_id` makes retries (including offline replays)
 * idempotent on the backend.
 */
export async function sendLocationUpdate(payload: LocationUpdate): Promise<void> {
  await apiClient.post<ApiResponse<void>>('/location/update/', payload);
}
