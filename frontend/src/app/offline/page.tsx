'use client';

import React, { useEffect, useState } from 'react';
import { WifiOff, RefreshCw } from 'lucide-react';
import { Button } from '@/components/ui/Button';

/**
 * Shown by the service worker when a navigation is attempted with no network
 * and no cached copy of the target page.
 *
 * Without this the installed app falls back to the browser's own error page,
 * which breaks the illusion of an application - and on a standalone window it
 * looks broken rather than merely offline.
 *
 * Location tracking itself keeps working while offline: fixes are queued in
 * IndexedDB and flushed when the connection returns, so a user who goes through
 * a dead spot does not lose attendance.
 */
export default function OfflinePage() {
  const [isOnline, setIsOnline] = useState<boolean>(true);

  useEffect(() => {
    const update = () => setIsOnline(navigator.onLine);
    update();
    window.addEventListener('online', update);
    window.addEventListener('offline', update);
    return () => {
      window.removeEventListener('online', update);
      window.removeEventListener('offline', update);
    };
  }, []);

  return (
    <div className="flex min-h-[80vh] flex-col items-center justify-center px-6 text-center">
      <div className="flex h-16 w-16 items-center justify-center rounded-2xl bg-slate-100 text-slate-500">
        <WifiOff className="h-8 w-8" />
      </div>

      <h1 className="mt-5 text-xl font-bold tracking-tight text-slate-900">
        {isOnline ? 'This page isn’t available offline' : 'You’re offline'}
      </h1>

      <p className="mt-2 max-w-sm text-sm leading-relaxed text-slate-600">
        {isOnline
          ? 'The connection is back. Retry to load the page.'
          : 'GeoPresence needs a connection to load this screen. Any location fixes recorded in the meantime are queued on this device and will sync automatically.'}
      </p>

      <Button className="mt-6" onClick={() => window.location.reload()}>
        <RefreshCw className="mr-1.5 h-4 w-4" />
        Retry
      </Button>

      <p className="mt-8 text-xs text-slate-400">
        {isOnline ? 'Connected' : 'Waiting for a network connection…'}
      </p>
    </div>
  );
}
