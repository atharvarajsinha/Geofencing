/**
 * Haversine formula to compute great-circle distance between two geographic points in meters.
 */
export function calculateDistanceMeters(
  lat1: number,
  lon1: number,
  lat2: number,
  lon2: number
): number {
  const R = 6371000; // Earth radius in meters
  const dLat = ((lat2 - lat1) * Math.PI) / 180;
  const dLon = ((lon2 - lon1) * Math.PI) / 180;

  const a =
    Math.sin(dLat / 2) * Math.sin(dLat / 2) +
    Math.cos((lat1 * Math.PI) / 180) *
      Math.cos((lat2 * Math.PI) / 180) *
      Math.sin(dLon / 2) *
      Math.sin(dLon / 2);

  const c = 2 * Math.atan2(Math.sqrt(a), Math.sqrt(1 - a));
  return R * c;
}

export interface ThrottlerConfig {
  minDistanceMeters: number;
  minIntervalMs: number;
  heartbeatIntervalMs: number;
  maxAcceptableAccuracyMeters: number;
}

export const DEFAULT_THROTTLER_CONFIG: ThrottlerConfig = {
  minDistanceMeters: 5,
  minIntervalMs: 15000, // 15 seconds
  heartbeatIntervalMs: 60000, // 60 seconds
  maxAcceptableAccuracyMeters: 150,
};

export interface LastSentPoint {
  latitude: number;
  longitude: number;
  timestamp: number;
}

/**
 * Determines whether a location update should be sent to the backend.
 */
export function shouldSendLocationUpdate(
  current: { latitude: number; longitude: number; accuracy: number; timestamp: number },
  lastSent: LastSentPoint | null,
  config: ThrottlerConfig = DEFAULT_THROTTLER_CONFIG
): { shouldSend: boolean; reason: string } {
  // Reject low accuracy readings unless emergency heartbeat
  if (current.accuracy > config.maxAcceptableAccuracyMeters) {
    if (!lastSent || current.timestamp - lastSent.timestamp >= config.heartbeatIntervalMs * 3) {
      return { shouldSend: true, reason: 'accuracy_fallback_heartbeat' };
    }
    return { shouldSend: false, reason: 'low_accuracy' };
  }

  if (!lastSent) {
    return { shouldSend: true, reason: 'initial_point' };
  }

  const timeDelta = current.timestamp - lastSent.timestamp;

  // Rate limit: prevent updates faster than minIntervalMs
  if (timeDelta < config.minIntervalMs) {
    return { shouldSend: false, reason: 'rate_limited' };
  }

  // Heartbeat check: send if enough time has passed even if position changed minimally
  if (timeDelta >= config.heartbeatIntervalMs) {
    return { shouldSend: true, reason: 'heartbeat' };
  }

  // Distance check: send if moved more than minDistanceMeters
  const distanceMoved = calculateDistanceMeters(
    lastSent.latitude,
    lastSent.longitude,
    current.latitude,
    current.longitude
  );

  if (distanceMoved >= config.minDistanceMeters) {
    return { shouldSend: true, reason: 'distance_moved' };
  }

  return { shouldSend: false, reason: 'insignificant_movement' };
}
