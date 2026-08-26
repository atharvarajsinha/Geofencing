'use client';

import { useCallback, useEffect, useRef, useState } from 'react';
import axios from 'axios';
import { getUnsyncedLocations, markLocationSynced } from '@/lib/db/offlineDb';
import { sendLocationUpdate } from '@/api/location';

/**
 * A queued fix the server refused on its merits (malformed, or older than the
 * backend's accepted age) will be refused again forever. Dropping it keeps one
 * poison entry from wedging every later update behind it. Auth, timeout and
 * rate-limit responses are retryable, so they stop the run instead.
 */
const RETRYABLE_STATUSES = new Set([401, 403, 408, 409, 429]);

function isPermanentRejection(err: unknown): boolean {
  if (!axios.isAxiosError(err)) return false;
  const status = err.response?.status;
  if (status === undefined) return false; // network failure - retry later
  return status >= 400 && status < 500 && !RETRYABLE_STATUSES.has(status);
}

export function useOfflineQueue() {
  const [isOnline, setIsOnline] = useState<boolean>(true);
  const [isSyncing, setIsSyncing] = useState<boolean>(false);
  const [pendingCount, setPendingCount] = useState<number>(0);
  const [droppedCount, setDroppedCount] = useState<number>(0);

  // Guards re-entrancy without putting isSyncing in the callback deps, which
  // would re-create the listeners on every sync.
  const syncingRef = useRef<boolean>(false);

  const updatePendingCount = useCallback(async () => {
    const unsynced = await getUnsyncedLocations();
    setPendingCount(unsynced.length);
  }, []);

  const syncQueue = useCallback(async () => {
    if (typeof navigator !== 'undefined' && !navigator.onLine) return;
    if (syncingRef.current) return;

    syncingRef.current = true;
    setIsSyncing(true);
    let dropped = 0;

    try {
      const unsynced = await getUnsyncedLocations();
      for (const item of unsynced) {
        if (!item.id) continue;
        try {
          await sendLocationUpdate({
            latitude: item.latitude,
            longitude: item.longitude,
            accuracy: item.accuracy,
            recorded_at: item.recorded_at,
            // Replaying with the original key lets the backend deduplicate.
            client_event_id: item.client_event_id,
          });
          await markLocationSynced(item.id);
        } catch (err) {
          if (isPermanentRejection(err)) {
            console.warn('Dropping permanently rejected offline location:', err);
            await markLocationSynced(item.id);
            dropped += 1;
            continue;
          }
          console.error('Failed to sync offline location item:', err);
          // Stop on a transient failure to preserve chronological order.
          break;
        }
      }
    } finally {
      syncingRef.current = false;
      setIsSyncing(false);
      if (dropped > 0) setDroppedCount((prev) => prev + dropped);
      await updatePendingCount();
    }
  }, [updatePendingCount]);

  useEffect(() => {
    if (typeof window === 'undefined') return;

    setIsOnline(navigator.onLine);

    const handleOnline = () => {
      setIsOnline(true);
      syncQueue();
    };
    const handleOffline = () => setIsOnline(false);

    window.addEventListener('online', handleOnline);
    window.addEventListener('offline', handleOffline);

    updatePendingCount();
    // Flush anything left over from a previous session.
    if (navigator.onLine) syncQueue();

    return () => {
      window.removeEventListener('online', handleOnline);
      window.removeEventListener('offline', handleOffline);
    };
  }, [syncQueue, updatePendingCount]);

  return {
    isOnline,
    isSyncing,
    pendingCount,
    droppedCount,
    syncQueue,
    updatePendingCount,
  };
}
