'use client';

import React, { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import {
  MapContainer,
  TileLayer,
  Marker,
  Circle,
  Rectangle,
  useMapEvents,
  useMap,
} from 'react-leaflet';
import L from 'leaflet';
import 'leaflet/dist/leaflet.css';
import { GeofenceBounds } from '@/types/geofence';
import { FALLBACK_ZOOM, getFallbackCenter, isValidCoordinate } from '@/lib/location/geolocation';
import {
  boundsCenter,
  boundsFromCorners,
  boundsSizeMetres,
  boundsToLeaflet,
  isValidBounds,
  offsetBounds,
} from '@/lib/location/bounds';

/**
 * Pans when the edited shape actually moves. Comparing coordinates rather than
 * object identity stops the map from snapping back mid-drag.
 */
function MapRecenter({ center }: { center: [number, number] | null }) {
  const map = useMap();
  const lastAppliedRef = useRef<string | null>(null);

  useEffect(() => {
    if (!center) return;
    const key = `${center[0].toFixed(6)},${center[1].toFixed(6)}`;
    if (lastAppliedRef.current === key) return;
    lastAppliedRef.current = key;
    map.setView(center, map.getZoom(), { animate: true });
  }, [center, map]);

  useEffect(() => {
    const timer = window.setTimeout(() => map.invalidateSize(), 200);
    return () => window.clearTimeout(timer);
  }, [map]);

  return null;
}

const centerPinIcon = L.divIcon({
  html: `<svg xmlns="http://www.w3.org/2000/svg" width="32" height="32" viewBox="0 0 24 24" fill="#0284c7" stroke="#ffffff" stroke-width="2"><path d="M12 2C8.13 2 5 5.13 5 9c0 5.25 7 13 7 13s7-7.75 7-13c0-3.87-3.13-7-7-7zm0 9.5c-1.38 0-2.5-1.12-2.5-2.5s1.12-2.5 2.5-2.5 2.5 1.12 2.5 2.5-1.12 2.5-2.5 2.5z"/></svg>`,
  className: 'custom-pin-icon',
  iconSize: [32, 32],
  iconAnchor: [16, 32],
});

// Plain HTML, so the attribute is `class` - `className` is a JSX-only alias and
// renders nothing.
const cornerIcon = L.divIcon({
  html: `<div style="width:14px;height:14px;border-radius:3px;background:#7c3aed;border:2px solid #ffffff;box-shadow:0 1px 3px rgba(0,0,0,.4)"></div>`,
  className: 'custom-corner-icon',
  iconSize: [18, 18],
  iconAnchor: [9, 9],
});

export type EditorMode = 'CIRCLE' | 'RECTANGLE';

interface GeofenceEditorMapProps {
  mode: EditorMode;
  // Circle state. Null means "not positioned yet".
  centerLat: number | null;
  centerLng: number | null;
  radius: number;
  entryRadius: number;
  exitRadius: number;
  onCenterChange: (lat: number, lng: number) => void;
  // Rectangle state. Null means "not drawn yet".
  bounds: GeofenceBounds | null;
  onBoundsChange: (bounds: GeofenceBounds) => void;
  className?: string;
}

/**
 * Click handling.
 *
 * CIRCLE: a click moves the centre.
 * RECTANGLE: the first click drops one corner, the second completes the box;
 * afterwards a click starts a fresh box. Corners stay draggable throughout, so
 * fine adjustment never requires redrawing.
 */
function MapClickHandler({
  mode,
  onCenterChange,
  onCornerClick,
}: {
  mode: EditorMode;
  onCenterChange: (lat: number, lng: number) => void;
  onCornerClick: (point: [number, number]) => void;
}) {
  useMapEvents({
    click(event) {
      if (mode === 'CIRCLE') {
        onCenterChange(event.latlng.lat, event.latlng.lng);
      } else {
        onCornerClick([event.latlng.lat, event.latlng.lng]);
      }
    },
  });
  return null;
}

export default function GeofenceEditorMap({
  mode,
  centerLat,
  centerLng,
  radius,
  entryRadius,
  exitRadius,
  onCenterChange,
  bounds,
  onBoundsChange,
  className = 'h-[450px] w-full rounded-2xl overflow-hidden shadow-sm border border-slate-200 relative',
}: GeofenceEditorMapProps) {
  const hasCenter = isValidCoordinate(centerLat, centerLng);
  const center: [number, number] | null = hasCenter
    ? [centerLat as number, centerLng as number]
    : null;

  const hasBounds = isValidBounds(bounds);

  /** The corner waiting for its opposite, while a new box is being drawn. */
  const [pendingCorner, setPendingCorner] = useState<[number, number] | null>(null);

  // MapContainer ignores prop changes after mount, so pick the opening view
  // once and let MapRecenter handle everything after that.
  const initialView = useMemo(() => {
    if (hasCenter) {
      return { center: [centerLat as number, centerLng as number] as [number, number], zoom: 16 };
    }
    if (hasBounds && bounds) return { center: boundsCenter(bounds), zoom: 16 };
    return { center: getFallbackCenter(), zoom: FALLBACK_ZOOM };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  const handleCornerClick = useCallback(
    (point: [number, number]) => {
      if (pendingCorner === null) {
        setPendingCorner(point);
        return;
      }
      onBoundsChange(boundsFromCorners(pendingCorner, point));
      setPendingCorner(null);
    },
    [pendingCorner, onBoundsChange]
  );

  const handleCenterDragEnd = useCallback(
    (event: L.LeafletEvent) => {
      const position = (event.target as L.Marker).getLatLng();
      onCenterChange(position.lat, position.lng);
    },
    [onCenterChange]
  );

  /**
   * Dragging one corner keeps the diagonally opposite one fixed, which is what
   * makes a rectangle feel like a rectangle rather than four loose points.
   */
  const handleCornerDragEnd = useCallback(
    (corner: 'sw' | 'se' | 'nw' | 'ne') => (event: L.LeafletEvent) => {
      if (!bounds) return;
      const position = (event.target as L.Marker).getLatLng();
      const anchor: [number, number] =
        corner === 'sw'
          ? [bounds.max_latitude, bounds.max_longitude]
          : corner === 'ne'
            ? [bounds.min_latitude, bounds.min_longitude]
            : corner === 'nw'
              ? [bounds.min_latitude, bounds.max_longitude]
              : [bounds.max_latitude, bounds.min_longitude];
      onBoundsChange(boundsFromCorners(anchor, [position.lat, position.lng]));
    },
    [bounds, onBoundsChange]
  );

  const safeRadius = Number.isFinite(radius) && radius > 0 ? radius : null;
  const safeEntry = Number.isFinite(entryRadius) && entryRadius > 0 ? entryRadius : null;
  const safeExit = Number.isFinite(exitRadius) && exitRadius > 0 ? exitRadius : null;

  // Preview the boundaries the backend will actually apply to the rectangle.
  const entryBounds = hasBounds && bounds && safeEntry ? offsetBounds(bounds, -safeEntry) : null;
  const exitBounds = hasBounds && bounds && safeExit ? offsetBounds(bounds, safeExit) : null;
  const size = hasBounds && bounds ? boundsSizeMetres(bounds) : null;

  const cornerHandles: Array<{ key: 'sw' | 'se' | 'nw' | 'ne'; position: [number, number] }> =
    hasBounds && bounds
      ? [
          { key: 'sw', position: [bounds.min_latitude, bounds.min_longitude] },
          { key: 'se', position: [bounds.min_latitude, bounds.max_longitude] },
          { key: 'nw', position: [bounds.max_latitude, bounds.min_longitude] },
          { key: 'ne', position: [bounds.max_latitude, bounds.max_longitude] },
        ]
      : [];

  const recenterTarget: [number, number] | null =
    mode === 'CIRCLE' ? center : hasBounds && bounds ? boundsCenter(bounds) : null;

  return (
    <div className={className}>
      <MapContainer
        center={initialView.center}
        zoom={initialView.zoom}
        scrollWheelZoom={true}
        className="h-full w-full z-10 cursor-crosshair"
      >
        <TileLayer
          attribution='&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a> contributors'
          url="https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png"
          maxZoom={19}
        />

        <MapRecenter center={recenterTarget} />

        <MapClickHandler
          mode={mode}
          onCenterChange={onCenterChange}
          onCornerClick={handleCornerClick}
        />

        {/* Circle geofence preview */}
        {mode === 'CIRCLE' && center && (
          <>
            <Marker
              position={center}
              icon={centerPinIcon}
              draggable={true}
              eventHandlers={{ dragend: handleCenterDragEnd }}
            />

            {/* Nominal geofence radius */}
            {safeRadius !== null && (
              <Circle
                center={center}
                radius={safeRadius}
                pathOptions={{ color: '#0284c7', fillColor: '#0284c7', fillOpacity: 0.15, weight: 2 }}
              />
            )}
            {/* Entry radius */}
            {safeEntry !== null && (
              <Circle
                center={center}
                radius={safeEntry}
                pathOptions={{
                  color: '#10b981',
                  fillColor: '#10b981',
                  fillOpacity: 0.1,
                  weight: 1.5,
                  dashArray: '4, 4',
                }}
              />
            )}
            {/* Exit radius */}
            {safeExit !== null && (
              <Circle
                center={center}
                radius={safeExit}
                pathOptions={{
                  color: '#f59e0b',
                  fillColor: '#f59e0b',
                  fillOpacity: 0.05,
                  weight: 1.5,
                  dashArray: '6, 6',
                }}
              />
            )}
          </>
        )}

        {/* Rectangle geofence preview */}
        {mode === 'RECTANGLE' && (
          <>
            {exitBounds && (
              <Rectangle
                bounds={boundsToLeaflet(exitBounds)}
                pathOptions={{
                  color: '#f59e0b',
                  fillColor: '#f59e0b',
                  fillOpacity: 0.05,
                  weight: 1.5,
                  dashArray: '6, 6',
                }}
              />
            )}

            {hasBounds && bounds && (
              <Rectangle
                bounds={boundsToLeaflet(bounds)}
                pathOptions={{
                  color: '#8b5cf6',
                  fillColor: '#8b5cf6',
                  fillOpacity: 0.2,
                  weight: 2,
                }}
              />
            )}

            {entryBounds && (
              <Rectangle
                bounds={boundsToLeaflet(entryBounds)}
                pathOptions={{
                  color: '#10b981',
                  fillColor: '#10b981',
                  fillOpacity: 0.1,
                  weight: 1.5,
                  dashArray: '4, 4',
                }}
              />
            )}

            {cornerHandles.map((handle) => (
              <Marker
                key={handle.key}
                position={handle.position}
                icon={cornerIcon}
                draggable={true}
                eventHandlers={{ dragend: handleCornerDragEnd(handle.key) }}
              />
            ))}

            {/* The first corner of a box still being drawn. */}
            {pendingCorner && <Marker position={pendingCorner} icon={cornerIcon} />}
          </>
        )}
      </MapContainer>

      {/* Instructional badge overlay */}
      <div className="absolute top-3 right-3 z-[1000] max-w-[70%] bg-white/90 backdrop-blur-md px-3 py-1.5 rounded-lg border border-slate-200 shadow-md text-xs font-semibold text-slate-700">
        {mode === 'CIRCLE'
          ? 'Click or drag the pin to set the centre'
          : pendingCorner
            ? 'Now click the opposite corner'
            : hasBounds && size
              ? `${Math.round(size.width)}m x ${Math.round(size.height)}m - drag a corner, or click to redraw`
              : 'Click two opposite corners to draw the rectangle'}
      </div>
    </div>
  );
}
