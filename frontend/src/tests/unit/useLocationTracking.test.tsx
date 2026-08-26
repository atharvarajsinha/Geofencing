import React from 'react';
import { describe, it, expect, beforeEach, afterEach, vi } from 'vitest';
import { render, act, waitFor } from '@testing-library/react';
import { useLocationTracking } from '@/hooks/useLocationTracking';
import { LAST_LOCATION_KEY, TRACKING_ACTIVE_KEY } from '@/lib/location/geolocation';

vi.mock('@/api/location', () => ({
  sendLocationUpdate: vi.fn().mockResolvedValue(undefined),
}));
vi.mock('@/lib/db/offlineDb', () => ({
  queueOfflineLocation: vi.fn().mockResolvedValue(1),
}));

import { sendLocationUpdate } from '@/api/location';

const geo = navigator.geolocation as unknown as {
  getCurrentPosition: ReturnType<typeof vi.fn>;
  watchPosition: ReturnType<typeof vi.fn>;
  clearWatch: ReturnType<typeof vi.fn>;
};

function fix(latitude: number, longitude: number, accuracy = 10, timestamp = 1_000) {
  return { coords: { latitude, longitude, accuracy }, timestamp } as GeolocationPosition;
}

/** Renders the hook and re-renders on demand, exposing the latest result. */
function renderTracking(options: Parameters<typeof useLocationTracking>[0] = {}) {
  const result: { current: ReturnType<typeof useLocationTracking> | null } = { current: null };
  let renderCount = 0;

  function Probe() {
    renderCount += 1;
    // A fresh object literal every render: previously this alone was enough to
    // retrigger the subscription effect.
    result.current = useLocationTracking({ ...options, throttlerConfig: { minIntervalMs: 15_000 } });
    return null;
  }

  const utils = render(<Probe />);
  return { result, utils, getRenderCount: () => renderCount };
}

describe('useLocationTracking subscription lifecycle', () => {
  beforeEach(() => {
    window.localStorage.clear();
    geo.getCurrentPosition.mockReset();
    geo.watchPosition.mockReset();
    geo.clearWatch.mockReset();
    geo.watchPosition.mockReturnValue(42);
    vi.mocked(sendLocationUpdate).mockClear();
  });

  afterEach(() => {
    window.localStorage.clear();
  });

  it('opens exactly one geolocation watch and keeps it across re-renders', async () => {
    geo.getCurrentPosition.mockImplementation((success: PositionCallback) => {
      success(fix(12.9716, 77.5946));
    });

    const { utils, result } = renderTracking({ autoStart: true });

    await waitFor(() => expect(result.current?.latitude).toBe(12.9716));

    expect(geo.watchPosition).toHaveBeenCalledTimes(1);
    expect(geo.clearWatch).not.toHaveBeenCalled();

    // Force several extra render passes; the watch must survive all of them.
    for (let i = 0; i < 5; i += 1) {
      await act(async () => {
        utils.rerender(<div />);
      });
    }
    const { rerender } = utils;
    await act(async () => {
      rerender(<div />);
    });

    expect(geo.watchPosition).toHaveBeenCalledTimes(1);
  });

  it('does not thrash: a state update from a fix must not re-subscribe', async () => {
    let watchSuccess: PositionCallback | null = null;
    geo.watchPosition.mockImplementation((success: PositionCallback) => {
      watchSuccess = success;
      return 42;
    });
    geo.getCurrentPosition.mockImplementation((success: PositionCallback) => {
      success(fix(12.9716, 77.5946, 10, 1_000));
    });

    const { result } = renderTracking({ autoStart: true });
    await waitFor(() => expect(result.current?.latitude).toBe(12.9716));

    // Deliver several more fixes through the watch.
    for (let i = 1; i <= 3; i += 1) {
      await act(async () => {
        watchSuccess?.(fix(12.9716 + i * 0.001, 77.5946, 10, 1_000 + i * 20_000));
      });
    }

    expect(geo.watchPosition).toHaveBeenCalledTimes(1);
    expect(geo.clearWatch).not.toHaveBeenCalled();
    expect(result.current?.latitude).toBeCloseTo(12.9746, 4);
  });

  it('clears the watch on unmount', async () => {
    geo.getCurrentPosition.mockImplementation((success: PositionCallback) => {
      success(fix(12.9716, 77.5946));
    });

    const { utils, result } = renderTracking({ autoStart: true });
    await waitFor(() => expect(result.current?.latitude).toBe(12.9716));

    utils.unmount();
    expect(geo.clearWatch).toHaveBeenCalledWith(42);
  });

  it('reports a denied permission as a structured, terminal failure', async () => {
    const denied = {
      code: 1,
      message: 'denied',
      PERMISSION_DENIED: 1,
      POSITION_UNAVAILABLE: 2,
      TIMEOUT: 3,
    } as GeolocationPositionError;

    geo.getCurrentPosition.mockImplementation((_s: PositionCallback, error: PositionErrorCallback) => {
      error(denied);
    });

    const { result } = renderTracking({ autoStart: true });

    await waitFor(() => expect(result.current?.failure?.reason).toBe('denied'));
    expect(result.current?.isTracking).toBe(false);
    expect(result.current?.error).toMatch(/permission/i);
  });

  it('persists a fix so the next map mount opens near the user', async () => {
    geo.getCurrentPosition.mockImplementation((success: PositionCallback) => {
      success(fix(12.9716, 77.5946, 8, 5_000));
    });

    const { result } = renderTracking({ autoStart: true });
    await waitFor(() => expect(result.current?.latitude).toBe(12.9716));

    expect(JSON.parse(window.localStorage.getItem(LAST_LOCATION_KEY) as string)).toEqual({
      latitude: 12.9716,
      longitude: 77.5946,
      accuracy: 8,
      timestamp: 5_000,
    });
    expect(window.localStorage.getItem(TRACKING_ACTIVE_KEY)).toBe('true');
  });

  it('sends telemetry with an idempotency key', async () => {
    geo.getCurrentPosition.mockImplementation((success: PositionCallback) => {
      success(fix(12.9716, 77.5946, 8, 5_000));
    });

    const { result } = renderTracking({ autoStart: true });
    await waitFor(() => expect(vi.mocked(sendLocationUpdate)).toHaveBeenCalled());

    const payload = vi.mocked(sendLocationUpdate).mock.calls[0][0];
    expect(payload.latitude).toBe(12.9716);
    expect(payload.client_event_id).toBeTruthy();
    expect((payload.client_event_id as string).length).toBeLessThanOrEqual(64);
    // The client must never assert a presence decision.
    expect(payload).not.toHaveProperty('status');
    expect(result.current?.isTracking).toBe(true);
  });

  it('stays inert when autoStart is false and nothing was resumed', async () => {
    renderTracking({ autoStart: false });
    await act(async () => {});
    expect(geo.watchPosition).not.toHaveBeenCalled();
  });

  it('resumes tracking that a previous session left active', async () => {
    window.localStorage.setItem(TRACKING_ACTIVE_KEY, 'true');
    geo.getCurrentPosition.mockImplementation((success: PositionCallback) => {
      success(fix(12.9716, 77.5946));
    });

    const { result } = renderTracking({ autoStart: false });
    await waitFor(() => expect(result.current?.isTracking).toBe(true));
    expect(geo.watchPosition).toHaveBeenCalledTimes(1);
  });
});
