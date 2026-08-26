'use client';

import { useCallback, useEffect, useRef, useState } from 'react';
import {
  GeolocationFailure,
  StoredLocation,
  checkGeolocationSupport,
  describeGeolocationError,
  getCurrentPositionOnce,
  HIGH_ACCURACY_OPTIONS,
  readStoredLocation,
  toStoredLocation,
  writeStoredLocation,
} from '@/lib/location/geolocation';

export type DeviceLocationStatus = 'idle' | 'locating' | 'ready' | 'error';

interface UseDeviceLocationOptions {
  /** Set false to keep the hook inert (e.g. a parent already supplies a position). */
  enabled?: boolean;
  /** Keep a `watchPosition` subscription open instead of taking a single fix. */
  watch?: boolean;
}

/**
 * Read-only "where is this device" hook, for centring maps.
 *
 * Deliberately separate from `useLocationTracking`: this one never posts
 * telemetry to the backend, so a screen can show the user where they are
 * without also enrolling them in presence tracking.
 */
export function useDeviceLocation({ enabled = true, watch = false }: UseDeviceLocationOptions = {}) {
  const [location, setLocation] = useState<StoredLocation | null>(null);
  const [isCached, setIsCached] = useState<boolean>(false);
  const [status, setStatus] = useState<DeviceLocationStatus>('idle');
  const [failure, setFailure] = useState<GeolocationFailure | null>(null);

  const watchIdRef = useRef<number | null>(null);
  const mountedRef = useRef<boolean>(true);

  const applyPosition = useCallback((position: GeolocationPosition) => {
    if (!mountedRef.current) return;
    const stored = toStoredLocation(position);
    writeStoredLocation(stored);
    setLocation(stored);
    setIsCached(false);
    setFailure(null);
    setStatus('ready');
  }, []);

  const refresh = useCallback(async () => {
    const unsupported = checkGeolocationSupport();
    if (unsupported) {
      setFailure(unsupported);
      setStatus('error');
      return;
    }
    setStatus('locating');
    try {
      applyPosition(await getCurrentPositionOnce());
    } catch (err) {
      if (!mountedRef.current) return;
      setFailure(err as GeolocationFailure);
      setStatus('error');
    }
  }, [applyPosition]);

  // Seed from the cache synchronously so the map opens near the user instead
  // of jumping continents once the first fix lands.
  useEffect(() => {
    const cached = readStoredLocation();
    if (cached) {
      setLocation(cached);
      setIsCached(true);
    }
  }, []);

  useEffect(() => {
    mountedRef.current = true;
    if (!enabled) return;

    const unsupported = checkGeolocationSupport();
    if (unsupported) {
      setFailure(unsupported);
      setStatus('error');
      return;
    }

    setStatus('locating');

    if (watch) {
      watchIdRef.current = navigator.geolocation.watchPosition(
        applyPosition,
        (error) => {
          if (!mountedRef.current) return;
          setFailure(describeGeolocationError(error));
          // A watch that times out once may still deliver later; only a hard
          // denial is terminal.
          setStatus((prev) => (prev === 'ready' ? 'ready' : 'error'));
        },
        HIGH_ACCURACY_OPTIONS
      );
    }

    // Always take one immediate fix: `watchPosition` alone can stay silent
    // until the device moves.
    getCurrentPositionOnce()
      .then(applyPosition)
      .catch((err: GeolocationFailure) => {
        if (!mountedRef.current) return;
        setFailure(err);
        setStatus((prev) => (prev === 'ready' ? 'ready' : 'error'));
      });

    return () => {
      mountedRef.current = false;
      if (watchIdRef.current !== null) {
        navigator.geolocation.clearWatch(watchIdRef.current);
        watchIdRef.current = null;
      }
    };
    // `applyPosition` is stable; only the caller's intent should re-subscribe.
  }, [enabled, watch, applyPosition]);

  return { location, isCached, status, failure, refresh };
}
