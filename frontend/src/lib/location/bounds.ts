/**
 * Bounding-box maths, mirroring `backend/common/utils/geo.py`.
 *
 * The backend is the authority on every presence decision; these helpers exist
 * only so the map can *draw* the same shapes the backend will evaluate - the
 * fence itself plus its entry (inset) and exit (outset) boundaries.
 *
 * Same sphere as the backend, so a distance shown here matches a distance the
 * API reports.
 */

import { GeofenceBounds } from '@/types/geofence';
import { isValidCoordinate } from './geolocation';

/** Mean Earth radius in metres (IUGG), identical to the backend constant. */
export const EARTH_RADIUS_M = 6_371_008.8;

/** Metres per degree of latitude; constant everywhere on a sphere. */
export const METRES_PER_DEGREE_LATITUDE = (EARTH_RADIUS_M * Math.PI) / 180;

/** Metres in one degree of longitude at a given latitude. */
export function metresPerDegreeLongitude(latitude: number): number {
  return METRES_PER_DEGREE_LATITUDE * Math.cos((latitude * Math.PI) / 180);
}

/** Leaflet's `[[southWest], [northEast]]` corner pair for a bounds object. */
export type LatLngBoundsTuple = [[number, number], [number, number]];

export function boundsToLeaflet(bounds: GeofenceBounds): LatLngBoundsTuple {
  return [
    [bounds.min_latitude, bounds.min_longitude],
    [bounds.max_latitude, bounds.max_longitude],
  ];
}

export function isValidBounds(bounds: Partial<GeofenceBounds> | null | undefined): boolean {
  if (!bounds) return false;
  const { min_latitude, max_latitude, min_longitude, max_longitude } = bounds;
  if (!isValidCoordinate(min_latitude, min_longitude)) return false;
  if (!isValidCoordinate(max_latitude, max_longitude)) return false;
  return (max_latitude as number) > (min_latitude as number) &&
    (max_longitude as number) > (min_longitude as number);
}

/**
 * Grow (positive) or shrink (negative) a box by a distance in metres.
 *
 * Used to draw the entry and exit boundaries: the backend requires a device to
 * be `entry_radius` metres *inside* the box to count as inside, and
 * `exit_radius` metres *outside* it to count as outside.
 *
 * Returns null when shrinking would collapse the box - there is no meaningful
 * inset boundary to draw for a fence smaller than twice its entry inset.
 */
export function offsetBounds(
  bounds: GeofenceBounds,
  metres: number
): GeofenceBounds | null {
  if (!Number.isFinite(metres)) return null;
  if (metres === 0) return { ...bounds };

  const latPad = metres / METRES_PER_DEGREE_LATITUDE;
  // Scale longitude at the box's mid-latitude, matching the backend's choice.
  const midLatitude = (bounds.min_latitude + bounds.max_latitude) / 2;
  const scale = metresPerDegreeLongitude(midLatitude);
  const lonPad = scale <= 0 ? 0 : metres / scale;

  const next: GeofenceBounds = {
    min_latitude: bounds.min_latitude - latPad,
    max_latitude: bounds.max_latitude + latPad,
    min_longitude: bounds.min_longitude - lonPad,
    max_longitude: bounds.max_longitude + lonPad,
  };

  if (next.max_latitude <= next.min_latitude) return null;
  if (next.max_longitude <= next.min_longitude) return null;
  return next;
}

/** Width and height of a box in metres, for display. */
export function boundsSizeMetres(bounds: GeofenceBounds): { width: number; height: number } {
  const midLatitude = (bounds.min_latitude + bounds.max_latitude) / 2;
  return {
    height: (bounds.max_latitude - bounds.min_latitude) * METRES_PER_DEGREE_LATITUDE,
    width:
      (bounds.max_longitude - bounds.min_longitude) * metresPerDegreeLongitude(midLatitude),
  };
}

export function boundsAreaKm2(bounds: GeofenceBounds): number {
  const { width, height } = boundsSizeMetres(bounds);
  return (Math.max(width, 0) * Math.max(height, 0)) / 1_000_000;
}

/** Centre of a box. */
export function boundsCenter(bounds: GeofenceBounds): [number, number] {
  return [
    (bounds.min_latitude + bounds.max_latitude) / 2,
    (bounds.min_longitude + bounds.max_longitude) / 2,
  ];
}

/**
 * Normalise two arbitrary corners into an ordered box.
 *
 * The map editor hands over whichever two corners the admin clicked, in
 * whatever order; the API requires min < max on both axes.
 */
export function boundsFromCorners(
  a: [number, number],
  b: [number, number]
): GeofenceBounds {
  return {
    min_latitude: Math.min(a[0], b[0]),
    max_latitude: Math.max(a[0], b[0]),
    min_longitude: Math.min(a[1], b[1]),
    max_longitude: Math.max(a[1], b[1]),
  };
}

/** A box of a given size in metres, centred on a point. */
export function boundsAround(
  latitude: number,
  longitude: number,
  halfSideMetres: number
): GeofenceBounds {
  const latPad = halfSideMetres / METRES_PER_DEGREE_LATITUDE;
  const scale = metresPerDegreeLongitude(latitude);
  const lonPad = scale <= 0 ? latPad : halfSideMetres / scale;
  return {
    min_latitude: latitude - latPad,
    max_latitude: latitude + latPad,
    min_longitude: longitude - lonPad,
    max_longitude: longitude + lonPad,
  };
}

/**
 * Signed distance in metres from a point to a box boundary; negative inside.
 * A direct port of the backend's `signed_distance_to_bbox_m`, used to show the
 * admin how far a location sits from the fence they are drawing.
 */
export function signedDistanceToBounds(
  latitude: number,
  longitude: number,
  bounds: GeofenceBounds
): number {
  const southOf = (bounds.min_latitude - latitude) * METRES_PER_DEGREE_LATITUDE;
  const northOf = (latitude - bounds.max_latitude) * METRES_PER_DEGREE_LATITUDE;
  const dy = Math.max(southOf, northOf);

  const referenceLatitude = Math.min(
    Math.max(latitude, bounds.min_latitude),
    bounds.max_latitude
  );
  const scale = metresPerDegreeLongitude(referenceLatitude);
  const westOf = (bounds.min_longitude - longitude) * scale;
  const eastOf = (longitude - bounds.max_longitude) * scale;
  const dx = Math.max(westOf, eastOf);

  if (dx > 0 && dy > 0) return Math.hypot(dx, dy);
  return Math.max(dx, dy);
}
