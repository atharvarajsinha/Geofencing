export type PresenceStatusType =
  | 'PRESENT'
  | 'GONE'
  | 'OUTSIDE'
  | 'STALE'
  | 'UNKNOWN'
  | 'LOCATION_REQUIRED'
  | 'LOCATION_ERROR'
  | 'SYNCING';

export interface UserPresenceData {
  status: PresenceStatusType;
  check_in_time: string | null;
  check_out_time: string | null;
  last_seen: string | null;
  geofence_name?: string | null;
  gps_accuracy?: number | null;
  latitude?: number | null;
  longitude?: number | null;
  seconds_since_last_seen?: number | null;
}

export interface AttendanceRecord {
  id?: number | string;
  date: string;
  check_in: string | null;
  check_out: string | null;
  status: PresenceStatusType;
  geofence_name?: string | null;
  total_duration?: string | null;
}

export interface AdminPresenceSummary {
  user_id: number;
  name: string;
  email: string;
  status: PresenceStatusType;
  last_seen: string | null;
  latitude: number | null;
  longitude: number | null;
  accuracy: number | null;
  geofence_name?: string | null;
  geofence_id?: number | null;
  seconds_since_last_seen?: number | null;
}

export interface AdminStats {
  total_users: number;
  present: number;
  gone: number;
  stale: number;
  unknown: number;
}
