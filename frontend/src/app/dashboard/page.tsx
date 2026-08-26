'use client';

import React, { useEffect } from 'react';
import { usePresence } from '@/hooks/usePresence';
import { useLocationTracking } from '@/hooks/useLocationTracking';
import { PageContainer } from '@/components/layout/PageContainer';
import { PresenceStatus } from '@/components/presence/PresenceStatus';
import { NetworkStatusBanner } from '@/components/presence/NetworkStatusBanner';
import { Card, CardHeader, CardTitle } from '@/components/ui/Card';
import { DynamicMapView } from '@/components/maps/DynamicMap';
import { useGeofences } from '@/hooks/useGeofences';
import { formatTime } from '@/lib/utils/formatters';
import { Radio, RefreshCw, AlertCircle, Info } from 'lucide-react';
import { Button } from '@/components/ui/Button';

export default function UserDashboardPage() {
  const { data: presence, isLoading: isPresenceLoading, refetch } = usePresence();
  const { data: geofences = [] } = useGeofences();

  const {
    isTracking,
    isLocating,
    error: trackingError,
    failure,
    startTracking,
    stopTracking,
    forceLocationUpdate,
    latitude,
    longitude,
    accuracy,
  } = useLocationTracking({
    autoStart: true,
    onLocationUpdateSuccess: () => {
      refetch();
    },
  });

  const hasFix = latitude !== null && longitude !== null;

  // Determine presence status display state. Keyed off the structured failure
  // reason rather than substring-matching a human-readable message.
  const getOverrideStatus = () => {
    if (failure) {
      const needsPermission =
        failure.reason === 'denied' ||
        failure.reason === 'unsupported' ||
        failure.reason === 'insecure_context';
      return needsPermission ? 'LOCATION_REQUIRED' : 'LOCATION_ERROR';
    }
    if (!isTracking) return 'LOCATION_REQUIRED';
    // Tracking is on but no fix has arrived yet: don't claim the backend's
    // stale/unknown verdict is the whole story.
    if (!hasFix) return 'SYNCING';
    return undefined; // use backend presence status
  };

  return (
    <PageContainer className="space-y-6">
      {/* Header Banner */}
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-bold text-slate-900 tracking-tight">MY PRESENCE</h1>
          <p className="text-xs text-slate-500">Live GPS Presence Verification</p>
        </div>
        <Button size="sm" variant="ghost" onClick={() => refetch()}>
          <RefreshCw className="w-4 h-4 mr-1" />
          Refresh
        </Button>
      </div>

      {/* Network Status & Offline Queue Monitor */}
      <NetworkStatusBanner />

      {/* Location Tracking Control Card */}
      <Card className="flex flex-col sm:flex-row items-start sm:items-center justify-between bg-slate-900 text-white p-4 gap-4">
        <div className="flex items-center space-x-3">
          <div className="relative shrink-0">
            <span
              className={`w-3 h-3 rounded-full inline-block ${
                isTracking ? 'bg-emerald-400 animate-ping absolute top-0 left-0 opacity-75' : 'bg-rose-500'
              }`}
            />
            <span
              className={`w-3 h-3 rounded-full inline-block ${
                isTracking ? 'bg-emerald-500' : 'bg-rose-500'
              }`}
            />
          </div>
          <div>
            <h3 className="font-semibold text-sm">Location Monitoring</h3>
            <p className="text-xs text-slate-400">
              {!isTracking
                ? 'Inactive'
                : hasFix
                  ? `Lat: ${latitude.toFixed(4)}, Lng: ${longitude.toFixed(4)}${
                      accuracy !== null ? ` (±${Math.round(accuracy)}m)` : ''
                    }`
                  : isLocating
                    ? 'Acquiring GPS fix…'
                    : 'Active & waiting for GPS fix…'}
            </p>
          </div>
        </div>

        <div className="flex items-center space-x-2 w-full sm:w-auto shrink-0">
          <Button
            size="sm"
            variant="outline"
            onClick={forceLocationUpdate}
            className="border-slate-700 text-slate-200 hover:bg-slate-800"
          >
            <Radio className="w-3.5 h-3.5 mr-1 text-sky-400" />
            Force GPS Fix
          </Button>

          <Button
            size="sm"
            variant={isTracking ? 'outline' : 'primary'}
            onClick={isTracking ? stopTracking : startTracking}
            className={isTracking ? 'border-slate-700 text-slate-200 hover:bg-slate-800' : ''}
          >
            {isTracking ? 'Pause' : 'Start Tracking'}
          </Button>
        </div>
      </Card>

      {/* Main Presence Status Display */}
      <PresenceStatus
        data={presence}
        statusOverride={getOverrideStatus()}
        errorMessage={trackingError}
        onEnableLocation={startTracking}
        onRetryLocation={startTracking}
        isLoading={isPresenceLoading}
      />

      {/* Live Position & Geofences */}
      <Card className="p-2">
        <DynamicMapView
          geofences={geofences}
          userLocation={hasFix ? { latitude, longitude, accuracy } : null}
          className="h-[320px] w-full rounded-xl overflow-hidden"
        />
      </Card>

      {/* Today's Attendance Summary Card */}
      <Card>
        <CardHeader>
          <CardTitle className="text-base">Today's Attendance</CardTitle>
        </CardHeader>

        <div className="grid grid-cols-2 gap-4">
          <div className="p-3 bg-slate-50 rounded-xl border border-slate-200">
            <span className="text-xs text-slate-500 block mb-1">Check-in</span>
            <span className="text-lg font-bold text-slate-900">
              {formatTime(presence?.check_in_time)}
            </span>
          </div>

          <div className="p-3 bg-slate-50 rounded-xl border border-slate-200">
            <span className="text-xs text-slate-500 block mb-1">Last Seen</span>
            <span className="text-lg font-bold text-slate-900">
              {formatTime(presence?.last_seen)}
            </span>
          </div>
        </div>
      </Card>

      {/* Transparent Location Privacy Notice */}
      <div className="bg-sky-50 border border-sky-200 rounded-xl p-4 text-xs text-sky-900 space-y-1">
        <div className="flex items-center font-semibold space-x-1 text-sky-800">
          <Info className="w-4 h-4 text-sky-600" />
          <span>Background Tracking Notice</span>
        </div>
        <p className="text-sky-800/90 leading-relaxed">
          Location monitoring requires this PWA or browser tab to remain active. The backend is the authoritative decider for presence status.
        </p>
      </div>
    </PageContainer>
  );
}
