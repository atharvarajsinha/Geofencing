import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import {
  getGeofences,
  getGeofenceById,
  createGeofence,
  updateGeofence,
  deleteGeofence,
} from '@/api/geofences';
import { Geofence, CreateGeofenceInput, UpdateGeofenceInput } from '@/types/geofence';

export function useGeofences() {
  return useQuery<Geofence[]>({
    queryKey: ['geofences'],
    queryFn: getGeofences,
    staleTime: 30000,
  });
}

export function useGeofence(id: number | string | null) {
  return useQuery<Geofence>({
    queryKey: ['geofences', id],
    queryFn: () => getGeofenceById(id!),
    enabled: !!id,
  });
}

export function useCreateGeofence() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (input: CreateGeofenceInput) => createGeofence(input),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['geofences'] });
    },
  });
}

export function useUpdateGeofence() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: ({ id, input }: { id: number | string; input: UpdateGeofenceInput }) =>
      updateGeofence(id, input),
    onSuccess: (_, { id }) => {
      queryClient.invalidateQueries({ queryKey: ['geofences'] });
      queryClient.invalidateQueries({ queryKey: ['geofences', id] });
    },
  });
}

export function useDeleteGeofence() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (id: number | string) => deleteGeofence(id),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['geofences'] });
    },
  });
}
