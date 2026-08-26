import { apiClient } from './client';
import { ApiResponse } from '@/types/api';
import { AdminPresenceSummary } from '@/types/presence';

/** Number if it is a usable one, otherwise null. Keeps 0 as a valid value. */
function toNumberOrNull(value: unknown): number | null {
  return typeof value === 'number' && Number.isFinite(value) ? value : null;
}

export async function getAdminLivePresence(params?: {
  status?: string;
  geofence_id?: number | string;
  page?: number;
  page_size?: number;
}): Promise<AdminPresenceSummary[]> {
  const response = await apiClient.get<ApiResponse<any>>('/admin/presence/', { params });
  const rawData = response.data?.data ?? response.data;
  const list = Array.isArray(rawData) ? rawData : rawData?.results || [];

  return list.map((item: any) => {
    // The API nests the position under `current_location` so a coordinate can
    // never be read without the accuracy that qualifies it.
    const location = item.current_location ?? null;

    return {
      user_id: item.user_id ?? item.user ?? item.id,
      name: item.user_name || item.name || item.user_email || 'User',
      email: item.user_email || item.email || '',
      status: item.status || 'UNKNOWN',
      last_seen: item.last_seen_at ?? item.last_seen ?? null,
      latitude: toNumberOrNull(location?.latitude),
      longitude: toNumberOrNull(location?.longitude),
      accuracy: toNumberOrNull(location?.accuracy),
      geofence_name: item.geofence_name ?? item.geofence?.name ?? null,
      geofence_id: item.geofence_id ?? null,
      seconds_since_last_seen: toNumberOrNull(item.seconds_since_last_seen),
    };
  });
}
