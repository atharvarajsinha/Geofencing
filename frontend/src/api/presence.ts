import { apiClient } from './client';
import { ApiResponse } from '@/types/api';
import { UserPresenceData, AttendanceRecord } from '@/types/presence';

function toNumberOrNull(value: unknown): number | null {
  return typeof value === 'number' && Number.isFinite(value) ? value : null;
}

/**
 * `GET /api/presence/me/` returns `{date, effective_status, geofences: [...]}`.
 * The dashboard needs one flat row, so the geofence the backend considers
 * effective is folded in.
 */
export async function getPresenceMe(): Promise<UserPresenceData> {
  const response = await apiClient.get<ApiResponse<any>>('/presence/me/');
  const data = response.data?.data ?? response.data ?? {};
  const rows: any[] = Array.isArray(data.geofences) ? data.geofences : [];

  // Prefer the row that matches the effective status, so a user inside one
  // geofence and outside another shows the geofence they are actually in.
  const activeRow =
    rows.find((row) => row?.status === data.effective_status) ?? rows[0] ?? null;

  return {
    status: data.effective_status || activeRow?.status || 'UNKNOWN',
    check_in_time: activeRow?.check_in_at ?? null,
    check_out_time: activeRow?.check_out_at ?? null,
    last_seen: activeRow?.last_seen_at ?? null,
    geofence_name: activeRow?.geofence_name ?? null,
    // Accuracy lives inside the nested current_location object.
    gps_accuracy: toNumberOrNull(activeRow?.current_location?.accuracy),
    latitude: toNumberOrNull(activeRow?.current_location?.latitude),
    longitude: toNumberOrNull(activeRow?.current_location?.longitude),
    seconds_since_last_seen: toNumberOrNull(activeRow?.seconds_since_last_seen),
  };
}

export async function getPresenceHistory(): Promise<AttendanceRecord[]> {
  const response = await apiClient.get<ApiResponse<any>>('/presence/me/history/');
  const rawData = response.data?.data ?? response.data;
  const list = Array.isArray(rawData) ? rawData : rawData?.results || [];

  return list.map((item: any) => ({
    id: item.id,
    date: item.date,
    check_in: item.check_in_at ?? item.check_in ?? null,
    check_out: item.check_out_at ?? item.check_out ?? null,
    status: item.status || 'UNKNOWN',
    geofence_name: item.geofence_name ?? null,
  }));
}
