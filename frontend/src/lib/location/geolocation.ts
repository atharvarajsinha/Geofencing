/**
 * Single source of truth for "where is this device?".
 *
 * Every screen that needs a position (the live map, the geofence editor, the
 * background tracker) goes through here so that permission handling, timeout
 * fallbacks and the last-known-position cache behave identically everywhere.
 */

export const LAST_LOCATION_KEY = 'geo_presence_last_location';
export const TRACKING_ACTIVE_KEY = 'geo_presence_tracking_active';

export interface StoredLocation {
  latitude: number;
  longitude: number;
  accuracy: number | null;
  timestamp: number;
}

/** A coordinate is valid only if it is a real number in range. 0 is valid. */
export function isValidCoordinate(lat: unknown, lng: unknown): boolean {
  return (
    typeof lat === 'number' &&
    typeof lng === 'number' &&
    Number.isFinite(lat) &&
    Number.isFinite(lng) &&
    Math.abs(lat) <= 90 &&
    Math.abs(lng) <= 180 &&
    // (0, 0) is in the Gulf of Guinea and is almost always a null-island bug.
    !(lat === 0 && lng === 0)
  );
}

/**
 * Fallback map centre, used only when the device position is unknown.
 *
 * Configurable through `NEXT_PUBLIC_DEFAULT_MAP_CENTER="lat,lng"` so no
 * arbitrary city is baked into the bundle. The default is the centroid of
 * India at a deliberately wide zoom, which reads as "we don't know yet"
 * instead of falsely claiming a precise location.
 */
export const FALLBACK_ZOOM = 5;
export const LOCATED_ZOOM = 16;

export function getFallbackCenter(): [number, number] {
  const raw = process.env.NEXT_PUBLIC_DEFAULT_MAP_CENTER;
  if (raw) {
    const [lat, lng] = raw.split(',').map((part) => Number(part.trim()));
    if (isValidCoordinate(lat, lng)) return [lat, lng];
  }
  return [20.5937, 78.9629];
}

/** Read the cached last-known position, or null when there isn't a usable one. */
export function readStoredLocation(): StoredLocation | null {
  if (typeof window === 'undefined') return null;
  try {
    const raw = window.localStorage.getItem(LAST_LOCATION_KEY);
    if (!raw) return null;
    const parsed = JSON.parse(raw);
    if (!isValidCoordinate(parsed?.latitude, parsed?.longitude)) return null;
    return {
      latitude: parsed.latitude,
      longitude: parsed.longitude,
      accuracy: Number.isFinite(parsed?.accuracy) ? parsed.accuracy : null,
      timestamp: Number.isFinite(parsed?.timestamp) ? parsed.timestamp : 0,
    };
  } catch {
    return null;
  }
}

export function writeStoredLocation(location: StoredLocation): void {
  if (typeof window === 'undefined') return;
  try {
    window.localStorage.setItem(LAST_LOCATION_KEY, JSON.stringify(location));
  } catch {
    /* quota or private mode - the position is still held in React state */
  }
}

export type GeolocationUnavailableReason =
  | 'unsupported'
  | 'insecure_context'
  | 'denied'
  | 'unavailable'
  | 'timeout'
  | 'unknown';

export interface GeolocationFailure {
  reason: GeolocationUnavailableReason;
  message: string;
}

/**
 * Geolocation is only exposed to secure contexts. `localhost` and `127.0.0.1`
 * count as secure, but a LAN IP over plain HTTP does not - the single most
 * common reason the map "won't find me" during development.
 */
export function checkGeolocationSupport(): GeolocationFailure | null {
  if (typeof window === 'undefined') {
    return { reason: 'unsupported', message: 'Geolocation is unavailable during server rendering.' };
  }
  if (!('geolocation' in navigator)) {
    return { reason: 'unsupported', message: 'This browser does not support geolocation.' };
  }
  if (window.isSecureContext === false) {
    return {
      reason: 'insecure_context',
      message:
        'Location needs a secure context. Open the app on http://localhost:3000 or serve it over HTTPS.',
    };
  }
  return null;
}

export function describeGeolocationError(error: GeolocationPositionError): GeolocationFailure {
  switch (error.code) {
    case error.PERMISSION_DENIED:
      return {
        reason: 'denied',
        message:
          'Location permission is blocked. Allow location for this site in your browser settings, then retry.',
      };
    case error.POSITION_UNAVAILABLE:
      return {
        reason: 'unavailable',
        message: 'No position could be determined. Check that device location/GPS is switched on.',
      };
    case error.TIMEOUT:
      return { reason: 'timeout', message: 'The location request timed out.' };
    default:
      return { reason: 'unknown', message: error.message || 'Could not determine your location.' };
  }
}

export const HIGH_ACCURACY_OPTIONS: PositionOptions = {
  enableHighAccuracy: true,
  maximumAge: 30_000,
  timeout: 15_000,
};

/** Coarse retry: network positioning, happy with a cached fix. */
export const COARSE_OPTIONS: PositionOptions = {
  enableHighAccuracy: false,
  maximumAge: 300_000,
  timeout: 20_000,
};

/**
 * Resolve one position, retrying without high accuracy when the GPS attempt
 * times out or reports no fix. Rejects with a {@link GeolocationFailure}.
 */
export function getCurrentPositionOnce(
  options: PositionOptions = HIGH_ACCURACY_OPTIONS
): Promise<GeolocationPosition> {
  const unsupported = checkGeolocationSupport();
  if (unsupported) return Promise.reject(unsupported);

  return new Promise((resolve, reject) => {
    navigator.geolocation.getCurrentPosition(
      resolve,
      (error) => {
        const failure = describeGeolocationError(error);
        // A denied permission will not resolve on retry; anything else might.
        if (failure.reason === 'denied' || !options.enableHighAccuracy) {
          reject(failure);
          return;
        }
        navigator.geolocation.getCurrentPosition(
          resolve,
          (retryError) => reject(describeGeolocationError(retryError)),
          COARSE_OPTIONS
        );
      },
      options
    );
  });
}

export function toStoredLocation(position: GeolocationPosition): StoredLocation {
  return {
    latitude: position.coords.latitude,
    longitude: position.coords.longitude,
    accuracy: Number.isFinite(position.coords.accuracy) ? position.coords.accuracy : null,
    timestamp: position.timestamp,
  };
}
