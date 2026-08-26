'use client';

import { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import { LocationState, LocationUpdate } from '@/types/location';
import {
  shouldSendLocationUpdate,
  LastSentPoint,
  DEFAULT_THROTTLER_CONFIG,
  ThrottlerConfig,
} from '@/lib/location/haversine';
import { sendLocationUpdate } from '@/api/location';
import { queueOfflineLocation } from '@/lib/db/offlineDb';
import {
  GeolocationFailure,
  HIGH_ACCURACY_OPTIONS,
  TRACKING_ACTIVE_KEY,
  checkGeolocationSupport,
  describeGeolocationError,
  getCurrentPositionOnce,
  readStoredLocation,
  writeStoredLocation,
} from '@/lib/location/geolocation';

interface UseLocationTrackingOptions {
  autoStart?: boolean;
  throttlerConfig?: Partial<ThrottlerConfig>;
  onLocationUpdateSuccess?: () => void;
}

function newClientEventId(): string {
  if (typeof crypto !== 'undefined' && typeof crypto.randomUUID === 'function') {
    return crypto.randomUUID();
  }
  return `evt-${Date.now()}-${Math.random().toString(16).slice(2)}`;
}

/**
 * Owns the device's GPS subscription and forwards throttled fixes to the API.
 *
 * The watch must outlive re-renders: every identity change in the effect's
 * dependencies used to tear the subscription down and rebuild it, so the
 * browser never had time to produce a fix. Callbacks are therefore held in
 * refs and the subscription effect depends only on the caller's intent.
 */
export function useLocationTracking(options: UseLocationTrackingOptions = {}) {
  const { autoStart = true, throttlerConfig, onLocationUpdateSuccess } = options;

  const [state, setState] = useState<LocationState>({
    latitude: null,
    longitude: null,
    accuracy: null,
    timestamp: null,
    isTracking: false,
    error: null,
  });
  const [isLocating, setIsLocating] = useState<boolean>(false);
  const [failure, setFailure] = useState<GeolocationFailure | null>(null);

  const watchIdRef = useRef<number | null>(null);
  const lastSentRef = useRef<LastSentPoint | null>(null);
  const mountedRef = useRef<boolean>(true);

  // Keep the latest callback/config without making the subscription effect
  // depend on their identity.
  const successCallbackRef = useRef(onLocationUpdateSuccess);
  successCallbackRef.current = onLocationUpdateSuccess;

  const effectiveConfig = useMemo<ThrottlerConfig>(
    () => ({ ...DEFAULT_THROTTLER_CONFIG, ...throttlerConfig }),
    [
      throttlerConfig?.minDistanceMeters,
      throttlerConfig?.minIntervalMs,
      throttlerConfig?.heartbeatIntervalMs,
      throttlerConfig?.maxAcceptableAccuracyMeters,
    ]
  );
  const configRef = useRef<ThrottlerConfig>(effectiveConfig);
  configRef.current = effectiveConfig;

  // Restore the last known position on mount only, so the server and first
  // client render agree and hydration does not mismatch.
  useEffect(() => {
    const cached = readStoredLocation();
    if (!cached) return;
    setState((prev) =>
      prev.latitude === null
        ? {
            ...prev,
            latitude: cached.latitude,
            longitude: cached.longitude,
            accuracy: cached.accuracy,
            timestamp: cached.timestamp,
          }
        : prev
    );
  }, []);

  const deliver = useCallback(async (payload: LocationUpdate) => {
    if (typeof navigator !== 'undefined' && navigator.onLine === false) {
      await queueOfflineLocation(payload);
      return;
    }
    try {
      await sendLocationUpdate(payload);
      successCallbackRef.current?.();
    } catch (err) {
      console.error('Failed to send live location, falling back to offline queue:', err);
      await queueOfflineLocation(payload);
    }
  }, []);

  const handlePosition = useCallback(
    async (position: GeolocationPosition) => {
      if (!mountedRef.current) return;

      const { latitude, longitude } = position.coords;
      const accuracy = Number.isFinite(position.coords.accuracy) ? position.coords.accuracy : null;
      const timestamp = position.timestamp;

      writeStoredLocation({ latitude, longitude, accuracy, timestamp });

      setIsLocating(false);
      setFailure(null);
      setState((prev) => ({
        ...prev,
        latitude,
        longitude,
        accuracy,
        timestamp,
        error: null,
      }));

      const { shouldSend } = shouldSendLocationUpdate(
        { latitude, longitude, accuracy: accuracy ?? Number.POSITIVE_INFINITY, timestamp },
        lastSentRef.current,
        configRef.current
      );
      if (!shouldSend) return;

      lastSentRef.current = { latitude, longitude, timestamp };
      await deliver({
        latitude,
        longitude,
        accuracy: accuracy ?? 0,
        recorded_at: new Date(timestamp).toISOString(),
        client_event_id: newClientEventId(),
      });
    },
    [deliver]
  );

  const handleFailure = useCallback((next: GeolocationFailure) => {
    if (!mountedRef.current) return;
    const terminal =
      next.reason === 'denied' || next.reason === 'unsupported' || next.reason === 'insecure_context';
    setIsLocating(false);
    setFailure(next);
    setState((prev) => ({
      ...prev,
      error: next.message,
      // A blocked permission means tracking is genuinely off; a timeout does not.
      isTracking: terminal ? false : prev.isTracking,
    }));
  }, []);

  const handlePositionError = useCallback(
    (error: GeolocationPositionError) => handleFailure(describeGeolocationError(error)),
    [handleFailure]
  );

  const stopTracking = useCallback(() => {
    if (watchIdRef.current !== null && typeof navigator !== 'undefined' && navigator.geolocation) {
      navigator.geolocation.clearWatch(watchIdRef.current);
    }
    watchIdRef.current = null;
    if (typeof window !== 'undefined') {
      try {
        window.localStorage.setItem(TRACKING_ACTIVE_KEY, 'false');
      } catch {}
    }
    setIsLocating(false);
    if (mountedRef.current) {
      setState((prev) => (prev.isTracking ? { ...prev, isTracking: false } : prev));
    }
  }, []);

  const startTracking = useCallback(() => {
    const unsupported = checkGeolocationSupport();
    if (unsupported) {
      handleFailure(unsupported);
      return;
    }

    // Already watching: nothing to rebuild.
    if (watchIdRef.current !== null) {
      setState((prev) => (prev.isTracking ? prev : { ...prev, isTracking: true }));
      return;
    }

    try {
      window.localStorage.setItem(TRACKING_ACTIVE_KEY, 'true');
    } catch {}

    setFailure(null);
    setIsLocating(true);
    setState((prev) => ({ ...prev, isTracking: true, error: null }));

    watchIdRef.current = navigator.geolocation.watchPosition(
      handlePosition,
      handlePositionError,
      HIGH_ACCURACY_OPTIONS
    );

    // watchPosition can stay silent until the device moves, so ask for one fix
    // immediately (the helper retries coarsely on timeout).
    getCurrentPositionOnce().then(handlePosition).catch(handleFailure);
  }, [handleFailure, handlePosition, handlePositionError]);

  /** Take a fix now and send it, bypassing the throttler. */
  const forceLocationUpdate = useCallback(async () => {
    setIsLocating(true);
    try {
      const position = await getCurrentPositionOnce();
      if (!mountedRef.current) return;

      const { latitude, longitude } = position.coords;
      const accuracy = Number.isFinite(position.coords.accuracy) ? position.coords.accuracy : null;
      const timestamp = position.timestamp;

      writeStoredLocation({ latitude, longitude, accuracy, timestamp });
      setIsLocating(false);
      setFailure(null);
      setState((prev) => ({ ...prev, latitude, longitude, accuracy, timestamp, error: null }));

      lastSentRef.current = { latitude, longitude, timestamp };
      await deliver({
        latitude,
        longitude,
        accuracy: accuracy ?? 0,
        recorded_at: new Date(timestamp).toISOString(),
        client_event_id: newClientEventId(),
      });
    } catch (err) {
      handleFailure(err as GeolocationFailure);
    }
  }, [deliver, handleFailure]);

  const setManualLocation = useCallback(
    async (latitude: number, longitude: number, accuracy: number = 10) => {
      const timestamp = Date.now();
      writeStoredLocation({ latitude, longitude, accuracy, timestamp });
      setState((prev) => ({ ...prev, latitude, longitude, accuracy, timestamp, error: null }));
      lastSentRef.current = { latitude, longitude, timestamp };
      await deliver({
        latitude,
        longitude,
        accuracy,
        recorded_at: new Date(timestamp).toISOString(),
        client_event_id: newClientEventId(),
      });
    },
    [deliver]
  );

  // One subscription for the lifetime of the consumer. startTracking and
  // stopTracking are stable, so this runs on mount/unmount only - it must
  // never re-run on an unrelated state change, or the watch is destroyed
  // before the browser can answer.
  useEffect(() => {
    mountedRef.current = true;

    const resumeRequested =
      typeof window !== 'undefined' && window.localStorage.getItem(TRACKING_ACTIVE_KEY) === 'true';

    if (autoStart || resumeRequested) {
      startTracking();
    }

    return () => {
      mountedRef.current = false;
      if (watchIdRef.current !== null && typeof navigator !== 'undefined' && navigator.geolocation) {
        navigator.geolocation.clearWatch(watchIdRef.current);
        watchIdRef.current = null;
      }
    };
  }, [autoStart, startTracking]);

  return {
    latitude: state.latitude,
    longitude: state.longitude,
    accuracy: state.accuracy,
    timestamp: state.timestamp,
    isTracking: state.isTracking,
    isLocating,
    error: state.error,
    failure,
    startTracking,
    stopTracking,
    forceLocationUpdate,
    setManualLocation,
  };
}
