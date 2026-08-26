import { apiClient } from './client';
import { ApiResponse } from '@/types/api';
import { Geofence, CreateGeofenceInput, UpdateGeofenceInput } from '@/types/geofence';

export async function getGeofences(): Promise<Geofence[]> {
  const response = await apiClient.get<ApiResponse<any>>('/geofences/');
  const rawData = response.data?.data || response.data;
  if (Array.isArray(rawData)) return rawData;
  if (rawData && Array.isArray(rawData.results)) return rawData.results;
  return [];
}

export async function getGeofenceById(id: number | string): Promise<Geofence> {
  const response = await apiClient.get<ApiResponse<Geofence>>(`/geofences/${id}/`);
  return response.data.data;
}

export async function createGeofence(input: CreateGeofenceInput): Promise<Geofence> {
  const response = await apiClient.post<ApiResponse<Geofence>>('/geofences/', input);
  return response.data.data;
}

export async function updateGeofence(id: number | string, input: UpdateGeofenceInput): Promise<Geofence> {
  const response = await apiClient.patch<ApiResponse<Geofence>>(`/geofences/${id}/`, input);
  return response.data.data;
}

export async function deleteGeofence(id: number | string): Promise<void> {
  await apiClient.delete<ApiResponse<void>>(`/geofences/${id}/`);
}
