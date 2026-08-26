'use client';

import React from 'react';
import { useAdminPresence } from '@/hooks/useAdminPresence';
import { PageContainer } from '@/components/layout/PageContainer';
import { StatsCards } from '@/components/admin/StatsCards';
import { AdminPresenceTable } from '@/components/admin/AdminPresenceTable';
import { Button } from '@/components/ui/Button';
import Link from 'next/link';
import { Map, Layers, RefreshCw, Plus } from 'lucide-react';

export default function AdminDashboardPage() {
  const { data: users = [], isLoading: isUsersLoading, refetch: refetchPresence } = useAdminPresence();

  const safeUsers = Array.isArray(users) ? users : [];

  const computedStats = {
    total_users: safeUsers.length,
    present: safeUsers.filter((u) => u.status === 'PRESENT').length,
    gone: safeUsers.filter((u) => u.status === 'GONE' || u.status === 'OUTSIDE').length,
    stale: safeUsers.filter((u) => u.status === 'STALE').length,
    unknown: safeUsers.filter((u) => u.status === 'UNKNOWN').length,
  };

  const handleRefresh = () => {
    refetchPresence();
  };

  return (
    <PageContainer className="space-y-6">
      {/* Header Bar */}
      <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-4">
        <div>
          <h1 className="text-2xl font-bold text-slate-900 tracking-tight">Admin Dashboard</h1>
          <p className="text-xs text-slate-500">Live organization presence overview and monitoring.</p>
        </div>

        <div className="flex items-center space-x-2">
          <Button size="sm" variant="outline" onClick={handleRefresh}>
            <RefreshCw className="w-4 h-4 mr-1.5" />
            Refresh
          </Button>
          <Link href="/admin/presence/map">
            <Button size="sm" variant="secondary">
              <Map className="w-4 h-4 mr-1.5" />
              Live Map
            </Button>
          </Link>
          <Link href="/admin/geofences/new">
            <Button size="sm">
              <Plus className="w-4 h-4 mr-1.5" />
              New Geofence
            </Button>
          </Link>
        </div>
      </div>

      {/* Summary Cards */}
      <StatsCards stats={computedStats} isLoading={isUsersLoading} />

      {/* Visual Geofence Studio Quick Action Banner */}
      <div className="bg-gradient-to-r from-sky-900 to-slate-900 text-white rounded-2xl p-5 shadow-sm flex flex-col sm:flex-row items-start sm:items-center justify-between gap-4 border border-slate-800">
        <div>
          <div className="flex items-center space-x-2 text-sky-400 text-xs font-semibold uppercase tracking-wider mb-1">
            <Layers className="w-4 h-4" />
            <span>Map Drawing Studio</span>
          </div>
          <h3 className="text-lg font-bold text-white">Visual Geofence Management</h3>
          <p className="text-xs text-slate-300 max-w-xl mt-1">
            Draw circular or rectangular geographic fences directly on an interactive map. Set entry/exit boundaries and debouncing.
          </p>
        </div>
        <div className="flex items-center space-x-2 shrink-0">
          <Link href="/admin/geofences">
            <Button size="sm" variant="outline" className="bg-white/10 text-white border-slate-700 hover:bg-white/20">
              View All Fences
            </Button>
          </Link>
          <Link href="/admin/geofences/new">
            <Button size="sm" className="bg-sky-500 hover:bg-sky-400 text-white border-none font-semibold">
              <Plus className="w-4 h-4 mr-1.5" />
              Draw New Geofence
            </Button>
          </Link>
        </div>
      </div>

      {/* Live Presence Table */}
      <div className="space-y-3">
        <h2 className="text-lg font-bold text-slate-900">User Presence Log</h2>
        <AdminPresenceTable users={users} isLoading={isUsersLoading} />
      </div>
    </PageContainer>
  );
}
