'use client';

import React from 'react';
import { useAuth } from '@/hooks/useAuth';
import { useLocationTracking } from '@/hooks/useLocationTracking';
import { PageContainer } from '@/components/layout/PageContainer';
import { Card, CardHeader, CardTitle } from '@/components/ui/Card';
import { Badge } from '@/components/ui/Badge';
import { Button } from '@/components/ui/Button';
import { formatRole } from '@/lib/utils/formatters';
import { User, Mail, Shield, Building, MapPin, Radio, Lock, HelpCircle } from 'lucide-react';

export default function ProfilePage() {
  const { user } = useAuth();
  const {
    isTracking,
    isLocating,
    startTracking,
    stopTracking,
    latitude,
    longitude,
    accuracy,
    error,
    forceLocationUpdate,
  } = useLocationTracking({ autoStart: true });

  const hasFix = latitude !== null && longitude !== null;

  return (
    <PageContainer className="space-y-6">
      <div>
        <h1 className="text-2xl font-bold text-slate-900 tracking-tight">User Profile</h1>
        <p className="text-xs text-slate-500">Account settings and location permission status.</p>
      </div>

      {/* User Information Card */}
      <Card className="p-6">
        <div className="flex items-center space-x-4 mb-6">
          <div className="w-14 h-14 rounded-full bg-sky-100 text-sky-600 flex items-center justify-center font-bold text-xl border border-sky-200">
            {user?.name?.[0] || 'U'}
          </div>
          <div>
            <h2 className="text-lg font-bold text-slate-900">{user?.name || 'User'}</h2>
            <div className="flex items-center space-x-2 mt-1">
              <Badge variant={user?.role === 'ADMIN' || user?.role === 'SUPER_ADMIN' ? 'info' : 'neutral'}>
                {formatRole(user?.role)}
              </Badge>
              {user?.organization && (
                <span className="text-xs text-slate-500">{user.organization}</span>
              )}
            </div>
          </div>
        </div>

        <div className="space-y-3 pt-4 border-t border-slate-100 text-sm">
          <div className="flex items-center text-slate-700">
            <Mail className="w-4 h-4 mr-2.5 text-slate-400" />
            <span className="font-semibold w-24">Email:</span>
            <span>{user?.email || '--'}</span>
          </div>

          <div className="flex items-center text-slate-700">
            <Shield className="w-4 h-4 mr-2.5 text-slate-400" />
            <span className="font-semibold w-24">Role:</span>
            <span>{formatRole(user?.role)}</span>
          </div>

          {user?.organization && (
            <div className="flex items-center text-slate-700">
              <Building className="w-4 h-4 mr-2.5 text-slate-400" />
              <span className="font-semibold w-24">Organization:</span>
              <span>{user.organization}</span>
            </div>
          )}
        </div>
      </Card>

      {/* Location Permission & Monitoring Control */}
      <Card className="p-6 space-y-4">
        <CardHeader>
          <CardTitle className="text-base flex items-center">
            <MapPin className="w-5 h-5 mr-2 text-sky-600" />
            Location Permission Status
          </CardTitle>
        </CardHeader>

        <div className="flex flex-col sm:flex-row items-start sm:items-center justify-between gap-4 bg-slate-50 p-4 rounded-xl border border-slate-200">
          <div>
            <div className="flex items-center space-x-2">
              <span
                className={`w-2.5 h-2.5 rounded-full ${
                  isTracking ? 'bg-emerald-500' : 'bg-rose-500'
                }`}
              />
              <span className="font-semibold text-slate-900">
                {isTracking ? 'Location Active' : 'Location Inactive'}
              </span>
            </div>
            <p className="text-xs text-slate-500 mt-1">
              {!isTracking
                ? 'Click "Enable Location" to prompt browser for location access.'
                : hasFix
                  ? `Active: Lat ${latitude.toFixed(4)}, Lng ${longitude.toFixed(4)}${
                      accuracy !== null ? ` (±${Math.round(accuracy)}m)` : ''
                    }`
                  : isLocating
                    ? 'Acquiring a GPS fix…'
                    : 'Geolocation watchPosition is active.'}
            </p>
          </div>

          <div className="flex items-center space-x-2">
            {!isTracking && (
              <Button size="sm" variant="outline" onClick={forceLocationUpdate}>
                Force Fix
              </Button>
            )}
            <Button
              size="sm"
              variant={isTracking ? 'outline' : 'primary'}
              onClick={isTracking ? stopTracking : startTracking}
            >
              {isTracking ? 'Pause Tracking' : 'Enable Location'}
            </Button>
          </div>
        </div>

        {error && (
          <div className="p-3 bg-red-50 border border-red-200 rounded-xl text-xs text-red-700 font-medium space-y-1">
            <div className="font-bold flex items-center space-x-1">
              <Lock className="w-4 h-4 mr-1 text-red-600 inline" />
              <span>{error}</span>
            </div>
            <p className="text-slate-600 leading-relaxed">
              If location was blocked, click the <strong>lock icon (🔒)</strong> or <strong>tune icon</strong> on the left side of your browser address bar, set <strong>Location</strong> to <strong>Allow</strong>, and click Enable Location again.
            </p>
          </div>
        )}
      </Card>

      {/* Location Privacy Disclosure */}
      <Card className="p-6 bg-slate-50 border-slate-200">
        <div className="flex items-center space-x-2 text-slate-900 font-bold mb-3">
          <HelpCircle className="w-5 h-5 text-sky-600" />
          <h3>Why do we need your location?</h3>
        </div>

        <ul className="space-y-2 text-xs text-slate-600 list-disc list-inside leading-relaxed">
          <li>Location data is used exclusively to determine presence status relative to designated geofences.</li>
          <li>Location updates are transmitted to the backend server only while active monitoring is enabled.</li>
          <li>The backend Django server is the sole authoritative engine for presence decisions.</li>
          <li>Location permissions can be paused or revoked anytime from browser or device settings.</li>
        </ul>
      </Card>
    </PageContainer>
  );
}
