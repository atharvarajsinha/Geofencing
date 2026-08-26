'use client';

import dynamic from 'next/dynamic';
import React from 'react';
import { Spinner } from '@/components/ui/Spinner';

export const DynamicMapView = dynamic(() => import('./MapView'), {
  ssr: false,
  loading: () => (
    <div className="h-[400px] w-full bg-slate-100 rounded-2xl flex flex-col items-center justify-center border border-slate-200">
      <Spinner size="lg" />
      <span className="mt-2 text-xs font-medium text-slate-500">Loading Leaflet Map...</span>
    </div>
  ),
});

export const DynamicGeofenceEditorMap = dynamic(() => import('./GeofenceEditorMap'), {
  ssr: false,
  loading: () => (
    <div className="h-[450px] w-full bg-slate-100 rounded-2xl flex flex-col items-center justify-center border border-slate-200">
      <Spinner size="lg" />
      <span className="mt-2 text-xs font-medium text-slate-500">Loading Map Drawing Studio...</span>
    </div>
  ),
});
