'use client';

import React from 'react';
import { useRouter, useParams } from 'next/navigation';
import { useGeofence, useUpdateGeofence } from '@/hooks/useGeofences';
import { PageContainer } from '@/components/layout/PageContainer';
import { GeofenceForm } from '@/components/geofences/GeofenceForm';
import { Card } from '@/components/ui/Card';
import { Spinner } from '@/components/ui/Spinner';
import { CreateGeofenceInput } from '@/types/geofence';
import { ArrowLeft } from 'lucide-react';
import Link from 'next/link';
import { Button } from '@/components/ui/Button';

export default function EditGeofencePage() {
  const params = useParams();
  const id = params?.id as string;
  const router = useRouter();

  const { data: geofence, isLoading } = useGeofence(id);
  const updateMutation = useUpdateGeofence();

  const handleSubmit = async (data: CreateGeofenceInput) => {
    if (!id) return;
    await updateMutation.mutateAsync({ id, input: data });
    router.push('/admin/geofences');
  };

  if (isLoading) {
    return (
      <PageContainer className="flex items-center justify-center min-h-[400px]">
        <Spinner size="lg" />
      </PageContainer>
    );
  }

  if (!geofence) {
    return (
      <PageContainer className="text-center py-12">
        <h2 className="text-lg font-bold text-slate-800">Geofence Not Found</h2>
        <Link href="/admin/geofences" className="mt-4 inline-block">
          <Button size="sm">Return to List</Button>
        </Link>
      </PageContainer>
    );
  }

  return (
    <PageContainer className="max-w-4xl space-y-6">
      <div className="flex items-center space-x-3">
        <Link href="/admin/geofences">
          <Button size="sm" variant="ghost">
            <ArrowLeft className="w-4 h-4 mr-1" />
            Back
          </Button>
        </Link>
        <div>
          <h1 className="text-2xl font-bold text-slate-900 tracking-tight">Edit Geofence</h1>
          <p className="text-xs text-slate-500">Update parameters for "{geofence.name}".</p>
        </div>
      </div>

      <Card className="p-6">
        <GeofenceForm
          initialValues={geofence}
          onSubmit={handleSubmit}
          isLoading={updateMutation.isPending}
        />
      </Card>
    </PageContainer>
  );
}
