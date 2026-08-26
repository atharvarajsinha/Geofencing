'use client';

import React from 'react';
import { useGeofences, useDeleteGeofence } from '@/hooks/useGeofences';
import { PageContainer } from '@/components/layout/PageContainer';
import { GeofenceList } from '@/components/geofences/GeofenceList';

export default function AdminGeofencesPage() {
  const { data: geofences = [], isLoading } = useGeofences();
  const deleteMutation = useDeleteGeofence();

  const handleDelete = async (id: number) => {
    if (confirm('Are you sure you want to delete this geofence?')) {
      await deleteMutation.mutateAsync(id);
    }
  };

  return (
    <PageContainer>
      <GeofenceList geofences={geofences} onDelete={handleDelete} isLoading={isLoading} />
    </PageContainer>
  );
}
