'use client';

import React from 'react';
import { useRouter } from 'next/navigation';
import { useCreateGeofence } from '@/hooks/useGeofences';
import { PageContainer } from '@/components/layout/PageContainer';
import { GeofenceForm } from '@/components/geofences/GeofenceForm';
import { Card, CardHeader, CardTitle, CardDescription } from '@/components/ui/Card';
import { CreateGeofenceInput } from '@/types/geofence';
import { ArrowLeft } from 'lucide-react';
import Link from 'next/link';
import { Button } from '@/components/ui/Button';

export default function CreateGeofencePage() {
  const createMutation = useCreateGeofence();
  const router = useRouter();

  const handleSubmit = async (data: CreateGeofenceInput) => {
    await createMutation.mutateAsync(data);
    router.push('/admin/geofences');
  };

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
          <h1 className="text-2xl font-bold text-slate-900 tracking-tight">Create Geofence</h1>
          <p className="text-xs text-slate-500">Visually define a circular or rectangular geographic area on the map.</p>
        </div>
      </div>

      <Card className="p-6">
        <GeofenceForm onSubmit={handleSubmit} isLoading={createMutation.isPending} />
      </Card>
    </PageContainer>
  );
}
