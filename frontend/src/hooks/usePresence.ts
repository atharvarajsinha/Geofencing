import { useQuery } from '@tanstack/react-query';
import { getPresenceMe, getPresenceHistory } from '@/api/presence';
import { UserPresenceData, AttendanceRecord } from '@/types/presence';

export function usePresence() {
  return useQuery<UserPresenceData>({
    queryKey: ['presence', 'me'],
    queryFn: getPresenceMe,
    staleTime: 10000, // 10s stale time
    refetchInterval: 30000, // 30s background refetch
    retry: 2,
  });
}

export function usePresenceHistory() {
  return useQuery<AttendanceRecord[]>({
    queryKey: ['presence', 'me', 'history'],
    queryFn: getPresenceHistory,
    staleTime: 30000,
    retry: 2,
  });
}
