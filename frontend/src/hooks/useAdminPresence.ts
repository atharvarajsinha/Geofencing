import { useQuery } from '@tanstack/react-query';
import { getAdminLivePresence } from '@/api/admin';
import { AdminPresenceSummary } from '@/types/presence';

export function useAdminPresence(
  params?: { status?: string; geofence_id?: number | string; page?: number },
  refetchInterval = 15000
) {
  return useQuery<AdminPresenceSummary[]>({
    queryKey: ['admin', 'presence', params],
    queryFn: () => getAdminLivePresence(params),
    refetchInterval,
    staleTime: 10000,
  });
}
