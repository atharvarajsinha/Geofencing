export interface LocationUpdate {
  latitude: number;
  longitude: number;
  accuracy: number;
  recorded_at: string;
  /** Client-generated id so retries and offline replays stay idempotent. */
  client_event_id?: string;
}

export interface LocationState {
  latitude: number | null;
  longitude: number | null;
  accuracy: number | null;
  timestamp: number | null;
  isTracking: boolean;
  error: string | null;
}

export interface OfflineQueuedLocation extends LocationUpdate {
  id?: number;
  synced: boolean;
  queued_at: string;
}
