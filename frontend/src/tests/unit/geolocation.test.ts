import { describe, it, expect, beforeEach, afterEach, vi } from 'vitest';
import {
  isValidCoordinate,
  getFallbackCenter,
  readStoredLocation,
  writeStoredLocation,
  describeGeolocationError,
  LAST_LOCATION_KEY,
} from '@/lib/location/geolocation';

describe('isValidCoordinate', () => {
  it('accepts ordinary coordinates', () => {
    expect(isValidCoordinate(29.5976, 79.6591)).toBe(true);
    expect(isValidCoordinate(-33.86, 151.2)).toBe(true);
  });

  it('accepts a zero component - the old truthiness check dropped these', () => {
    expect(isValidCoordinate(0, 79.6591)).toBe(true);
    expect(isValidCoordinate(29.5976, 0)).toBe(true);
  });

  it('rejects null island, which is always a bug rather than a place', () => {
    expect(isValidCoordinate(0, 0)).toBe(false);
  });

  it('rejects non-numbers, NaN and out-of-range values', () => {
    expect(isValidCoordinate(null, 10)).toBe(false);
    expect(isValidCoordinate(undefined, undefined)).toBe(false);
    expect(isValidCoordinate('29.5', '79.6')).toBe(false);
    expect(isValidCoordinate(Number.NaN, 10)).toBe(false);
    expect(isValidCoordinate(91, 10)).toBe(false);
    expect(isValidCoordinate(10, 181)).toBe(false);
  });
});

describe('getFallbackCenter', () => {
  const original = process.env.NEXT_PUBLIC_DEFAULT_MAP_CENTER;

  afterEach(() => {
    process.env.NEXT_PUBLIC_DEFAULT_MAP_CENTER = original;
  });

  it('reads a configured centre', () => {
    process.env.NEXT_PUBLIC_DEFAULT_MAP_CENTER = '12.9716, 77.5946';
    expect(getFallbackCenter()).toEqual([12.9716, 77.5946]);
  });

  it('ignores a malformed value and uses the wide default', () => {
    process.env.NEXT_PUBLIC_DEFAULT_MAP_CENTER = 'not-a-coordinate';
    expect(getFallbackCenter()).toEqual([20.5937, 78.9629]);
  });
});

describe('stored location round trip', () => {
  beforeEach(() => {
    window.localStorage.clear();
  });

  it('returns null when nothing is stored', () => {
    expect(readStoredLocation()).toBeNull();
  });

  it('round trips a fix', () => {
    writeStoredLocation({ latitude: 12.5, longitude: 77.5, accuracy: 8, timestamp: 1000 });
    expect(readStoredLocation()).toEqual({
      latitude: 12.5,
      longitude: 77.5,
      accuracy: 8,
      timestamp: 1000,
    });
  });

  it('discards a stored entry with unusable coordinates', () => {
    window.localStorage.setItem(
      LAST_LOCATION_KEY,
      JSON.stringify({ latitude: null, longitude: 77.5, accuracy: 8, timestamp: 1000 })
    );
    expect(readStoredLocation()).toBeNull();
  });

  it('survives corrupt JSON', () => {
    window.localStorage.setItem(LAST_LOCATION_KEY, '{not json');
    expect(readStoredLocation()).toBeNull();
  });

  it('normalises a missing accuracy to null rather than NaN', () => {
    writeStoredLocation({
      latitude: 12.5,
      longitude: 77.5,
      accuracy: null,
      timestamp: 1000,
    });
    expect(readStoredLocation()?.accuracy).toBeNull();
  });
});

describe('describeGeolocationError', () => {
  const makeError = (code: number): GeolocationPositionError =>
    ({
      code,
      message: 'raw',
      PERMISSION_DENIED: 1,
      POSITION_UNAVAILABLE: 2,
      TIMEOUT: 3,
    }) as GeolocationPositionError;

  it('maps each browser code to a stable reason', () => {
    expect(describeGeolocationError(makeError(1)).reason).toBe('denied');
    expect(describeGeolocationError(makeError(2)).reason).toBe('unavailable');
    expect(describeGeolocationError(makeError(3)).reason).toBe('timeout');
    expect(describeGeolocationError(makeError(99)).reason).toBe('unknown');
  });

  it('explains what the user should do about a denial', () => {
    expect(describeGeolocationError(makeError(1)).message).toMatch(/permission/i);
  });
});
