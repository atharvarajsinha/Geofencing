import React from 'react';
import Link from 'next/link';
import { Geofence, RectangleGeofence } from '@/types/geofence';
import { boundsSizeMetres, isValidBounds } from '@/lib/location/bounds';
import { Badge } from '@/components/ui/Badge';
import { Button } from '@/components/ui/Button';
import { Plus, Edit2, Trash2, MapPin, Layers } from 'lucide-react';

/** "200m x 130m", or a dash when the stored edges are unusable. */
function formatRectangleSize(fence: RectangleGeofence): string {
  if (!isValidBounds(fence)) return '-';
  const { width, height } = boundsSizeMetres(fence);
  return `${Math.round(width)}m x ${Math.round(height)}m`;
}

interface GeofenceListProps {
  geofences: Geofence[];
  onDelete: (id: number) => void;
  isLoading?: boolean;
}

export function GeofenceList({ geofences, onDelete, isLoading = false }: GeofenceListProps) {
  const safeGeofences = Array.isArray(geofences) ? geofences : [];

  if (isLoading) {
    return (
      <div className="space-y-4">
        {[1, 2, 3].map((i) => (
          <div key={i} className="h-20 bg-slate-100 animate-pulse rounded-xl" />
        ))}
      </div>
    );
  }

  return (
    <div className="space-y-4">
      <div className="flex items-center justify-between">
        <div>
          <h2 className="text-xl font-bold text-slate-900">Geofences</h2>
          <p className="text-sm text-slate-500">Manage geographic boundaries and tracking zones.</p>
        </div>
        <Link href="/admin/geofences/new">
          <Button size="sm">
            <Plus className="w-4 h-4 mr-1.5" />
            Create Geofence
          </Button>
        </Link>
      </div>

      {safeGeofences.length === 0 ? (
        <div className="text-center py-12 bg-slate-50 rounded-2xl border border-dashed border-slate-300">
          <MapPin className="w-10 h-10 text-slate-400 mx-auto mb-2" />
          <h3 className="text-base font-semibold text-slate-800">No Geofences Defined</h3>
          <p className="text-sm text-slate-500 mb-4 max-w-sm mx-auto">
            Create a circle or rectangle geofence to start tracking user presence automatically.
          </p>
          <Link href="/admin/geofences/new">
            <Button size="sm">
              <Plus className="w-4 h-4 mr-1.5" />
              Create First Geofence
            </Button>
          </Link>
        </div>
      ) : (
        <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
          {safeGeofences.map((fence) => (
            <div
              key={fence.id}
              className="bg-white p-5 rounded-2xl border border-slate-200 shadow-sm flex flex-col justify-between"
            >
              <div>
                <div className="flex items-center justify-between mb-2">
                  <div className="flex items-center space-x-2">
                    <span className="p-2 rounded-lg bg-sky-50 text-sky-600 border border-sky-100">
                      {fence.type === 'CIRCLE' ? (
                        <MapPin className="w-4 h-4" />
                      ) : (
                        <Layers className="w-4 h-4" />
                      )}
                    </span>
                    <h3 className="font-bold text-slate-900">{fence.name}</h3>
                  </div>
                  <Badge variant={fence.is_active ? 'success' : 'neutral'}>
                    {fence.is_active ? 'ACTIVE' : 'INACTIVE'}
                  </Badge>
                </div>

                <div className="text-xs text-slate-600 space-y-1 mb-4">
                  <p>
                    <span className="font-semibold">Type:</span> {fence.type}
                  </p>
                  {fence.type === 'CIRCLE' && (
                    <>
                      <p>
                        <span className="font-semibold">Radius:</span> {fence.radius}m
                      </p>
                      <p>
                        <span className="font-semibold">Hysteresis:</span> Entry {fence.entry_radius}m / Exit {fence.exit_radius}m
                      </p>
                    </>
                  )}
                  {fence.type === 'RECTANGLE' && (
                    <>
                      <p>
                        <span className="font-semibold">Size:</span>{' '}
                        {formatRectangleSize(fence)}
                      </p>
                      <p>
                        <span className="font-semibold">Hysteresis:</span> Inset{' '}
                        {fence.entry_radius ?? 0}m / Outset {fence.exit_radius ?? 0}m
                      </p>
                    </>
                  )}
                </div>
              </div>

              <div className="flex items-center justify-end space-x-2 pt-3 border-t border-slate-100">
                <Link href={`/admin/geofences/${fence.id}`}>
                  <Button size="sm" variant="outline">
                    <Edit2 className="w-3.5 h-3.5 mr-1" />
                    Edit
                  </Button>
                </Link>
                <Button
                  size="sm"
                  variant="danger"
                  onClick={() => onDelete(fence.id)}
                >
                  <Trash2 className="w-3.5 h-3.5" />
                </Button>
              </div>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}
