import React from 'react';
import { useOfflineQueue } from '@/hooks/useOfflineQueue';
import { Wifi, WifiOff, RefreshCw } from 'lucide-react';
import { Button } from '@/components/ui/Button';

export function NetworkStatusBanner() {
  const { isOnline, isSyncing, pendingCount, syncQueue } = useOfflineQueue();

  if (isOnline && pendingCount === 0) {
    return (
      <div className="flex items-center justify-between bg-slate-50 border border-slate-200 rounded-xl px-4 py-2 text-xs text-slate-600">
        <div className="flex items-center space-x-2">
          <span className="w-2 h-2 rounded-full bg-emerald-500" />
          <span className="font-medium text-slate-700">Online</span>
        </div>
        <span className="text-slate-500">Network Connected</span>
      </div>
    );
  }

  return (
    <div
      className={`rounded-xl border p-3 text-xs ${
        !isOnline
          ? 'bg-amber-50 border-amber-200 text-amber-900'
          : 'bg-sky-50 border-sky-200 text-sky-900'
      }`}
    >
      <div className="flex items-center justify-between">
        <div className="flex items-center space-x-2">
          {!isOnline ? (
            <WifiOff className="w-4 h-4 text-amber-600" />
          ) : (
            <Wifi className="w-4 h-4 text-sky-600" />
          )}
          <div>
            <span className="font-semibold">
              {!isOnline ? 'Offline Mode' : 'Network Restored'}
            </span>
            {pendingCount > 0 && (
              <span className="ml-1 text-slate-600">
                ({pendingCount} queued location update{pendingCount > 1 ? 's' : ''})
              </span>
            )}
          </div>
        </div>

        {isOnline && pendingCount > 0 && (
          <Button size="sm" variant="outline" onClick={syncQueue} isLoading={isSyncing}>
            <RefreshCw className="w-3 h-3 mr-1" />
            Sync Now
          </Button>
        )}
      </div>
    </div>
  );
}
