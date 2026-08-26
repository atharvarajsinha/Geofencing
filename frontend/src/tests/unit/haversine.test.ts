import { describe, it, expect } from 'vitest';
import {
  calculateDistanceMeters,
  shouldSendLocationUpdate,
  DEFAULT_THROTTLER_CONFIG,
} from '@/lib/location/haversine';

describe('Location Throttler & Distance Utilities', () => {
  it('calculates great circle distance accurately using Haversine formula', () => {
    // Distance between (29.5976, 79.6591) and (29.5980, 79.6595) is approx 58 meters
    const dist = calculateDistanceMeters(29.5976, 79.6591, 29.598, 79.6595);
    expect(dist).toBeGreaterThan(50);
    expect(dist).toBeLessThan(70);
  });

  it('approves initial location update when no previous location sent', () => {
    const current = { latitude: 29.5976, longitude: 79.6591, accuracy: 10, timestamp: 100000 };
    const res = shouldSendLocationUpdate(current, null);
    expect(res.shouldSend).toBe(true);
    expect(res.reason).toBe('initial_point');
  });

  it('rate limits updates sent faster than minIntervalMs', () => {
    const lastSent = { latitude: 29.5976, longitude: 79.6591, timestamp: 100000 };
    const current = { latitude: 29.6000, longitude: 79.6700, accuracy: 10, timestamp: 105000 }; // 5s gap < 15s min
    const res = shouldSendLocationUpdate(current, lastSent);
    expect(res.shouldSend).toBe(false);
    expect(res.reason).toBe('rate_limited');
  });

  it('sends update when user moves more than minDistanceMeters after interval', () => {
    const lastSent = { latitude: 29.5976, longitude: 79.6591, timestamp: 100000 };
    const current = { latitude: 29.5980, longitude: 79.6595, accuracy: 10, timestamp: 120000 }; // 20s gap, moved ~58m
    const res = shouldSendLocationUpdate(current, lastSent);
    expect(res.shouldSend).toBe(true);
    expect(res.reason).toBe('distance_moved');
  });

  it('triggers periodic heartbeat update when stationary after heartbeatIntervalMs', () => {
    const lastSent = { latitude: 29.5976, longitude: 79.6591, timestamp: 100000 };
    const current = { latitude: 29.5976, longitude: 79.6591, accuracy: 10, timestamp: 170000 }; // 70s gap > 60s
    const res = shouldSendLocationUpdate(current, lastSent);
    expect(res.shouldSend).toBe(true);
    expect(res.reason).toBe('heartbeat');
  });

  it('rejects update with poor GPS accuracy exceeding maxAcceptableAccuracyMeters', () => {
    const lastSent = { latitude: 29.5976, longitude: 79.6591, timestamp: 100000 };
    const current = { latitude: 29.5980, longitude: 79.6595, accuracy: 250, timestamp: 120000 }; // 250m accuracy > 150m
    const res = shouldSendLocationUpdate(current, lastSent);
    expect(res.shouldSend).toBe(false);
    expect(res.reason).toBe('low_accuracy');
  });
});
