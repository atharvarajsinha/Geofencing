export type GeofenceType = 'CIRCLE' | 'RECTANGLE';

/** Thresholds the backend will actually apply, with defaults resolved. */
export interface EffectiveThresholds {
  entry_threshold_m: number;
  exit_threshold_m: number;
  required_inside_readings: number;
  required_outside_readings: number;
  stale_after_seconds: number;
}

/**
 * The four numbers that define a rectangle geofence.
 *
 * Every geofence carries them: for a RECTANGLE they *are* the shape, for a
 * CIRCLE they are the envelope the backend derives from the centre and radius.
 */
export interface GeofenceBounds {
  min_latitude: number;
  max_latitude: number;
  min_longitude: number;
  max_longitude: number;
}

export interface BaseGeofence extends GeofenceBounds {
  id: number;
  organization_id?: number;
  name: string;
  type: GeofenceType;
  is_active: boolean;
  /** Representative point: circle centre, or the centre of the rectangle. */
  latitude: number | null;
  longitude: number | null;
  /** Present on reads; the source of truth when entry/exit radius are null. */
  effective_thresholds?: EffectiveThresholds;
  entry_radius: number | null;
  exit_radius: number | null;
  required_inside_readings?: number | null;
  required_outside_readings?: number | null;
  stale_after_seconds?: number | null;
  created_at?: string;
  updated_at?: string;
}

export interface CircleGeofence extends BaseGeofence {
  type: 'CIRCLE';
  center_latitude: number;
  center_longitude: number;
  radius: number;
}

export interface RectangleGeofence extends BaseGeofence {
  type: 'RECTANGLE';
  center_latitude: null;
  center_longitude: null;
  radius: null;
}

export type Geofence = CircleGeofence | RectangleGeofence;

export interface CreateCircleGeofenceInput {
  name: string;
  type: 'CIRCLE';
  latitude: number;
  longitude: number;
  radius: number;
  entry_radius: number;
  exit_radius: number;
  is_active?: boolean;
}

export interface CreateRectangleGeofenceInput extends GeofenceBounds {
  name: string;
  type: 'RECTANGLE';
  entry_radius?: number;
  exit_radius?: number;
  is_active?: boolean;
}

export type CreateGeofenceInput =
  | CreateCircleGeofenceInput
  | CreateRectangleGeofenceInput;
export type UpdateGeofenceInput = Partial<CreateGeofenceInput> & { is_active?: boolean };
