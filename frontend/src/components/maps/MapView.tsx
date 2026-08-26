'use client';

import React, { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import { MapContainer, TileLayer, Marker, Circle, Rectangle, Popup, useMap } from 'react-leaflet';
import L from 'leaflet';
import 'leaflet/dist/leaflet.css';
import { Geofence } from '@/types/geofence';
import { AdminPresenceSummary } from '@/types/presence';
import { useDeviceLocation } from '@/hooks/useDeviceLocation';
import {
  FALLBACK_ZOOM,
  LOCATED_ZOOM,
  getFallbackCenter,
  isValidCoordinate,
  readStoredLocation,
} from '@/lib/location/geolocation';
import {
  boundsSizeMetres,
  boundsToLeaflet,
  isValidBounds,
  offsetBounds,
} from '@/lib/location/bounds';
import { Crosshair, LocateFixed, AlertTriangle } from 'lucide-react';

// Custom marker icons as inline SVG, so no Leaflet image asset paths are needed.
const createCustomIcon = (color: string) => {
  const svg = `<svg xmlns="http://www.w3.org/2000/svg" width="32" height="32" viewBox="0 0 24 24" fill="${color}" stroke="#ffffff" stroke-width="1.5"><path d="M12 2C8.13 2 5 5.13 5 9c0 5.25 7 13 7 13s7-7.75 7-13c0-3.87-3.13-7-7-7zm0 9.5c-1.38 0-2.5-1.12-2.5-2.5s1.12-2.5 2.5-2.5 2.5 1.12 2.5 2.5-1.12 2.5-2.5 2.5z"/></svg>`;
  return L.divIcon({
    html: svg,
    className: 'custom-leaflet-marker',
    iconSize: [32, 32],
    iconAnchor: [16, 32],
    popupAnchor: [0, -32],
  });
};

const userIcon = createCustomIcon('#0284c7'); // Sky blue for self
const presentIcon = createCustomIcon('#10b981'); // Green for present users
const goneIcon = createCustomIcon('#f59e0b'); // Amber for gone/outside users
const staleIcon = createCustomIcon('#6b7280'); // Grey for stale users

export interface MapPoint {
  latitude: number;
  longitude: number;
  accuracy?: number | null;
}

/**
 * Pans the map when the target moves, and stops following as soon as the user
 * takes over. Comparing the numeric coordinates (rather than the array
 * identity) is what keeps the map from snapping back on every re-render.
 */
function MapController({
  target,
  zoom,
  follow,
  onUserInteraction,
}: {
  target: [number, number] | null;
  zoom: number;
  follow: boolean;
  onUserInteraction: () => void;
}) {
  const map = useMap();
  const lastAppliedRef = useRef<string | null>(null);

  useEffect(() => {
    const handleUserMove = () => onUserInteraction();
    // Only gestures count as taking over; programmatic setView does not fire these.
    map.on('dragstart', handleUserMove);
    map.on('zoomstart', handleUserMove);
    return () => {
      map.off('dragstart', handleUserMove);
      map.off('zoomstart', handleUserMove);
    };
  }, [map, onUserInteraction]);

  useEffect(() => {
    if (!target || !follow) return;
    const key = `${target[0].toFixed(6)},${target[1].toFixed(6)}`;
    if (lastAppliedRef.current === key) return;
    lastAppliedRef.current = key;
    map.setView(target, Math.max(map.getZoom(), zoom), { animate: true });
  }, [target, zoom, follow, map]);

  // Leaflet mis-sizes itself when it mounts inside a container that is still
  // being laid out (a common cause of a grey half-rendered map).
  useEffect(() => {
    const timer = window.setTimeout(() => map.invalidateSize(), 200);
    return () => window.clearTimeout(timer);
  }, [map]);

  return null;
}

interface MapViewProps {
  /** Explicit centre. Only used when no device position is known. */
  center?: [number, number];
  zoom?: number;
  /**
   * Position of the signed-in user. When omitted (undefined) the map asks the
   * browser for the device position itself; pass `null` to disable that.
   */
  userLocation?: MapPoint | null;
  geofences?: Geofence[];
  userMarkers?: AdminPresenceSummary[];
  className?: string;
}

/** First finite number in the list, or null. */
function firstFinite(...values: Array<number | null | undefined>): number | null {
  for (const value of values) {
    if (typeof value === 'number' && Number.isFinite(value) && value > 0) return value;
  }
  return null;
}

export default function MapView({
  center,
  zoom = LOCATED_ZOOM,
  userLocation,
  geofences = [],
  userMarkers = [],
  className = 'h-[400px] w-full rounded-2xl overflow-hidden shadow-sm border border-slate-200',
}: MapViewProps) {
  // Self-locate only when the parent did not take responsibility for it.
  const selfLocate = userLocation === undefined;
  const {
    location: deviceLocation,
    status: deviceStatus,
    failure: deviceFailure,
    refresh: refreshDeviceLocation,
  } = useDeviceLocation({ enabled: selfLocate, watch: true });

  const [follow, setFollow] = useState<boolean>(true);

  const resolvedUserPoint: MapPoint | null = useMemo(() => {
    if (userLocation && isValidCoordinate(userLocation.latitude, userLocation.longitude)) {
      return userLocation;
    }
    if (deviceLocation && isValidCoordinate(deviceLocation.latitude, deviceLocation.longitude)) {
      return deviceLocation;
    }
    return null;
  }, [userLocation, deviceLocation]);

  // Where the map should open. Computed once, because MapContainer ignores
  // later changes to its `center` prop - live panning is MapController's job.
  const initialView = useMemo(() => {
    if (resolvedUserPoint) {
      return { center: [resolvedUserPoint.latitude, resolvedUserPoint.longitude] as [number, number], zoom };
    }
    const cached = readStoredLocation();
    if (cached) return { center: [cached.latitude, cached.longitude] as [number, number], zoom };
    if (center && isValidCoordinate(center[0], center[1])) return { center, zoom };
    // Nothing is known about the device: open wide rather than pretend.
    return { center: getFallbackCenter(), zoom: FALLBACK_ZOOM };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  const followTarget: [number, number] | null = resolvedUserPoint
    ? [resolvedUserPoint.latitude, resolvedUserPoint.longitude]
    : null;

  const handleUserInteraction = useCallback(() => setFollow(false), []);

  const recenterOnMe = useCallback(() => {
    setFollow(true);
    if (!resolvedUserPoint && selfLocate) {
      refreshDeviceLocation();
    }
  }, [resolvedUserPoint, selfLocate, refreshDeviceLocation]);

  const isLocating = selfLocate && deviceStatus === 'locating' && !resolvedUserPoint;
  const locationError = selfLocate && !resolvedUserPoint ? deviceFailure : null;

  // Admin rows are one per (user, geofence), so a user inside two geofences
  // appears twice. Keep the most recently seen row per user.
  const dedupedMarkers = useMemo(() => {
    const byUser = new Map<number | string, AdminPresenceSummary>();
    for (const marker of userMarkers) {
      if (!isValidCoordinate(marker.latitude, marker.longitude)) continue;
      const existing = byUser.get(marker.user_id);
      if (!existing) {
        byUser.set(marker.user_id, marker);
        continue;
      }
      const existingSeen = existing.last_seen ? Date.parse(existing.last_seen) : 0;
      const candidateSeen = marker.last_seen ? Date.parse(marker.last_seen) : 0;
      if (candidateSeen >= existingSeen) byUser.set(marker.user_id, marker);
    }
    return Array.from(byUser.values());
  }, [userMarkers]);

  return (
    <div className={`relative ${className}`}>
      <MapContainer
        center={initialView.center}
        zoom={initialView.zoom}
        scrollWheelZoom={true}
        className="h-full w-full z-10"
      >
        <TileLayer
          attribution='&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a> contributors'
          url="https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png"
          maxZoom={19}
        />

        <MapController
          target={followTarget}
          zoom={zoom}
          follow={follow}
          onUserInteraction={handleUserInteraction}
        />

        {/* Current device position and its accuracy bubble */}
        {resolvedUserPoint && (
          <>
            <Marker
              position={[resolvedUserPoint.latitude, resolvedUserPoint.longitude]}
              icon={userIcon}
            >
              <Popup>
                <div className="text-xs">
                  <strong className="block text-sky-700">Your Current Location</strong>
                  <span>Lat: {resolvedUserPoint.latitude.toFixed(5)}</span>
                  <br />
                  <span>Lng: {resolvedUserPoint.longitude.toFixed(5)}</span>
                  {typeof resolvedUserPoint.accuracy === 'number' && (
                    <span className="block text-slate-500 mt-1">
                      Accuracy: &plusmn;{Math.round(resolvedUserPoint.accuracy)}m
                    </span>
                  )}
                </div>
              </Popup>
            </Marker>
            {typeof resolvedUserPoint.accuracy === 'number' && resolvedUserPoint.accuracy > 0 && (
              <Circle
                center={[resolvedUserPoint.latitude, resolvedUserPoint.longitude]}
                radius={resolvedUserPoint.accuracy}
                pathOptions={{ color: '#0284c7', fillColor: '#0284c7', fillOpacity: 0.15, weight: 1 }}
              />
            )}
          </>
        )}

        {/* Admin-created geofences */}
        {geofences.map((fence) => {
          if (!fence.is_active) return null;

          if (fence.type === 'CIRCLE') {
            if (!isValidCoordinate(fence.center_latitude, fence.center_longitude)) return null;
            const fenceCenter: [number, number] = [
              fence.center_latitude,
              fence.center_longitude,
            ];
            // entry_radius/exit_radius are nullable on the API; fall back to the
            // thresholds the backend actually applies, then to the nominal radius.
            const nominal = firstFinite(fence.radius);
            const entry = firstFinite(
              fence.entry_radius,
              fence.effective_thresholds?.entry_threshold_m,
              nominal
            );
            const exit = firstFinite(
              fence.exit_radius,
              fence.effective_thresholds?.exit_threshold_m,
              entry,
              nominal
            );
            if (entry === null && exit === null) return null;

            return (
              <React.Fragment key={fence.id}>
                {exit !== null && (
                  /* Exit radius: outer hysteresis boundary */
                  <Circle
                    center={fenceCenter}
                    radius={exit}
                    pathOptions={{
                      color: '#f59e0b',
                      fillColor: '#f59e0b',
                      fillOpacity: 0.08,
                      dashArray: '6, 6',
                    }}
                  />
                )}
                {entry !== null && (
                  /* Entry radius: the core fence */
                  <Circle
                    center={fenceCenter}
                    radius={entry}
                    pathOptions={{
                      color: '#10b981',
                      fillColor: '#10b981',
                      fillOpacity: 0.2,
                      weight: 2,
                    }}
                  >
                    <Popup>
                      <div className="text-xs">
                        <strong className="block text-emerald-700">{fence.name} (Circle)</strong>
                        {nominal !== null && <span>Radius: {nominal}m</span>}
                        <br />
                        <span>
                          Entry: {entry}m | Exit: {exit ?? entry}m
                        </span>
                      </div>
                    </Popup>
                  </Circle>
                )}
              </React.Fragment>
            );
          }

          if (fence.type === 'RECTANGLE') {
            if (!isValidBounds(fence)) return null;
            const size = boundsSizeMetres(fence);

            // The backend requires a device to be entry_radius metres *inside*
            // the box, and exit_radius metres *outside* it, so draw all three.
            //
            // A rectangle's effective entry threshold is expressed as a
            // *negative* signed distance (the inset), so take its magnitude
            // rather than discarding it for not being positive.
            const effectiveInset = fence.effective_thresholds?.entry_threshold_m;
            const entryInset = firstFinite(
              fence.entry_radius,
              typeof effectiveInset === 'number' ? Math.abs(effectiveInset) : null
            );
            const exitOutset = firstFinite(
              fence.exit_radius,
              fence.effective_thresholds?.exit_threshold_m
            );
            const entryBounds = entryInset ? offsetBounds(fence, -entryInset) : null;
            const exitBounds = exitOutset ? offsetBounds(fence, exitOutset) : null;

            return (
              <React.Fragment key={fence.id}>
                {exitBounds && (
                  /* Exit boundary: cross this and the backend checks you out. */
                  <Rectangle
                    bounds={boundsToLeaflet(exitBounds)}
                    pathOptions={{
                      color: '#f59e0b',
                      fillColor: '#f59e0b',
                      fillOpacity: 0.06,
                      weight: 1.5,
                      dashArray: '6, 6',
                    }}
                  />
                )}
                {/* The fence as drawn by the admin. */}
                <Rectangle
                  bounds={boundsToLeaflet(fence)}
                  pathOptions={{
                    color: '#8b5cf6',
                    fillColor: '#8b5cf6',
                    fillOpacity: 0.18,
                    weight: 2,
                  }}
                >
                  <Popup>
                    <div className="text-xs">
                      <strong className="block text-purple-700">{fence.name} (Rectangle)</strong>
                      <span>
                        {Math.round(size.width)}m x {Math.round(size.height)}m
                      </span>
                      <br />
                      <span className="text-slate-500">
                        Entry inset: {entryInset ?? 0}m | Exit outset: {exitOutset ?? 0}m
                      </span>
                    </div>
                  </Popup>
                </Rectangle>
                {entryBounds && (
                  /* Entry boundary: get inside this and the backend checks you in. */
                  <Rectangle
                    bounds={boundsToLeaflet(entryBounds)}
                    pathOptions={{
                      color: '#10b981',
                      fillColor: '#10b981',
                      fillOpacity: 0.12,
                      weight: 1.5,
                      dashArray: '4, 4',
                    }}
                  />
                )}
              </React.Fragment>
            );
          }

          return null;
        })}

        {/* Live user markers for the admin view */}
        {dedupedMarkers.map((user) => {
          let markerIcon = staleIcon;
          if (user.status === 'PRESENT') markerIcon = presentIcon;
          if (user.status === 'GONE' || user.status === 'OUTSIDE') markerIcon = goneIcon;

          return (
            <Marker
              key={user.user_id}
              position={[user.latitude as number, user.longitude as number]}
              icon={markerIcon}
            >
              <Popup>
                <div className="text-xs">
                  <strong className="block text-slate-900">{user.name}</strong>
                  <span className="font-semibold text-slate-600">Status: {user.status}</span>
                  <br />
                  <span>Last seen: {user.last_seen || 'Unknown'}</span>
                  {typeof user.accuracy === 'number' && (
                    <span className="block text-slate-500">
                      Accuracy: &plusmn;{Math.round(user.accuracy)}m
                    </span>
                  )}
                </div>
              </Popup>
            </Marker>
          );
        })}
      </MapContainer>

      {/* Recentre control */}
      <button
        type="button"
        onClick={recenterOnMe}
        title={resolvedUserPoint ? 'Centre on my location' : 'Find my location'}
        className="absolute bottom-4 right-4 z-[1000] flex items-center gap-1.5 rounded-lg border border-slate-200 bg-white/95 px-3 py-2 text-xs font-semibold text-slate-700 shadow-md backdrop-blur transition-colors hover:bg-white disabled:opacity-60"
      >
        {follow && resolvedUserPoint ? (
          <LocateFixed className="h-4 w-4 text-sky-600" />
        ) : (
          <Crosshair className="h-4 w-4 text-slate-500" />
        )}
        My location
      </button>

      {/* Locating / error status strip */}
      {isLocating && (
        <div className="absolute left-1/2 top-3 z-[1000] -translate-x-1/2 rounded-lg border border-sky-200 bg-white/95 px-3 py-1.5 text-xs font-medium text-sky-800 shadow-md backdrop-blur">
          Locating you&hellip;
        </div>
      )}

      {locationError && (
        <div className="absolute left-3 right-3 top-3 z-[1000] flex items-start gap-2 rounded-lg border border-amber-200 bg-amber-50/95 px-3 py-2 text-xs text-amber-900 shadow-md backdrop-blur">
          <AlertTriangle className="mt-0.5 h-4 w-4 shrink-0 text-amber-600" />
          <div className="flex-1">
            <p className="font-semibold">Showing a default view &mdash; your location is unavailable</p>
            <p className="mt-0.5 leading-relaxed text-amber-800">{locationError.message}</p>
          </div>
          <button
            type="button"
            onClick={refreshDeviceLocation}
            className="shrink-0 rounded-md border border-amber-300 bg-white px-2 py-1 font-semibold text-amber-800 hover:bg-amber-100"
          >
            Retry
          </button>
        </div>
      )}
    </div>
  );
}
