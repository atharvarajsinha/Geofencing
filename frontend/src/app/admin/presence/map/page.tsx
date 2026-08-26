'use client';

import React, { useState } from 'react';
import { useAdminPresence } from '@/hooks/useAdminPresence';
import { useGeofences } from '@/hooks/useGeofences';
import { PageContainer } from '@/components/layout/PageContainer';
import { DynamicMapView } from '@/components/maps/DynamicMap';
import { Button } from '@/components/ui/Button';
import { Card } from '@/components/ui/Card';
import { RefreshCw, Radio, Users, Layers, Info } from 'lucide-react';

export default function AdminLivePresenceMapPage() {
  const [pollingInterval, setPollingInterval] = useState<number>(15000); // 15 seconds default

  const { data: geofences = [] } = useGeofences();
  const { data: users = [], isLoading, refetch, isFetching } = useAdminPresence(
    undefined,
    pollingInterval
  );

  const plottedUsers = users.filter(
    (user) => user.latitude !== null && user.longitude !== null
  ).length;

  return (
    <PageContainer className="space-y-6">
      {/* Header Bar */}
      <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-4">
        <div>
          <h1 className="text-2xl font-bold text-slate-900 tracking-tight">Live Presence Map</h1>
          <p className="text-xs text-slate-500">
            Real-time visual map of geofences and active user locations.
          </p>
        </div>

        {/* Polling & Refresh Controls */}
        <div className="flex items-center space-x-3">
          <div className="flex items-center space-x-2 text-xs text-slate-600 bg-white px-3 py-1.5 rounded-lg border border-slate-200">
            <span className="font-semibold">Polling:</span>
            <select
              value={pollingInterval}
              onChange={(e) => setPollingInterval(Number(e.target.value))}
              className="bg-transparent font-medium focus:outline-none text-sky-600 cursor-pointer"
            >
              <option value={5000}>5 seconds</option>
              <option value={15000}>15 seconds</option>
              <option value={30000}>30 seconds</option>
              <option value={60000}>60 seconds</option>
            </select>
          </div>

          <Button size="sm" variant="outline" onClick={() => refetch()} isLoading={isFetching}>
            <RefreshCw className="w-4 h-4 mr-1.5" />
            Refresh
          </Button>
        </div>
      </div>

      {/* Map Display */}
      <Card className="p-2">
        {/* userLocation is intentionally omitted: the map locates the admin's
            own device itself and does not enrol them in presence tracking. */}
        <DynamicMapView
          geofences={geofences}
          userMarkers={users}
          className="h-[550px] w-full rounded-xl overflow-hidden"
        />
      </Card>

      {/* Polling Disclosure Notice */}
      <div className="bg-slate-100 border border-slate-200 rounded-xl p-3.5 text-xs text-slate-600 flex items-center justify-between">
        <div className="flex items-center space-x-2">
          <Info className="w-4 h-4 text-slate-500" />
          <span>
            Map updates via background HTTP polling every <strong>{pollingInterval / 1000}s</strong>.
          </span>
        </div>
        <span className="text-slate-500 font-medium">
          {plottedUsers} of {users.length} users have a plottable position
        </span>
      </div>
    </PageContainer>
  );
}
