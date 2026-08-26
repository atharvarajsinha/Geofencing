import React, { useState } from 'react';
import { AdminPresenceSummary, PresenceStatusType } from '@/types/presence';
import { Badge } from '@/components/ui/Badge';
import { Input } from '@/components/ui/Input';
import { formatTime } from '@/lib/utils/formatters';
import { Search, Filter } from 'lucide-react';

interface AdminPresenceTableProps {
  users: AdminPresenceSummary[];
  isLoading?: boolean;
}

export function AdminPresenceTable({ users, isLoading = false }: AdminPresenceTableProps) {
  const [search, setSearch] = useState('');
  const [statusFilter, setStatusFilter] = useState<string>('ALL');

  const safeUsers = Array.isArray(users) ? users : [];
  const filtered = safeUsers.filter((u) => {
    const matchesSearch =
      (u.name || '').toLowerCase().includes(search.toLowerCase()) ||
      (u.email || '').toLowerCase().includes(search.toLowerCase());
    const matchesStatus = statusFilter === 'ALL' || u.status === statusFilter;
    return matchesSearch && matchesStatus;
  });

  const getBadge = (status: PresenceStatusType) => {
    switch (status) {
      case 'PRESENT':
        return <Badge variant="success">PRESENT</Badge>;
      case 'GONE':
      case 'OUTSIDE':
        return <Badge variant="warning">GONE</Badge>;
      case 'STALE':
        return <Badge variant="neutral">STALE</Badge>;
      default:
        return <Badge variant="neutral">{status}</Badge>;
    }
  };

  return (
    <div className="space-y-4">
      {/* Search & Filter Bar */}
      <div className="flex flex-col sm:flex-row gap-3 justify-between items-center">
        <div className="relative w-full sm:w-72">
          <Input
            placeholder="Search by user name or email..."
            value={search}
            onChange={(e) => setSearch(e.target.value)}
            className="pl-9"
          />
          <Search className="w-4 h-4 text-slate-400 absolute left-3 top-3.5" />
        </div>

        <div className="flex items-center space-x-2 w-full sm:w-auto">
          <Filter className="w-4 h-4 text-slate-500" />
          <select
            value={statusFilter}
            onChange={(e) => setStatusFilter(e.target.value)}
            className="px-3 py-2 bg-white border border-slate-300 rounded-lg text-sm font-medium text-slate-700 focus:outline-none focus:ring-2 focus:ring-sky-500 min-h-[44px]"
          >
            <option value="ALL">All Statuses</option>
            <option value="PRESENT">PRESENT</option>
            <option value="GONE">GONE</option>
            <option value="STALE">STALE</option>
          </select>
        </div>
      </div>

      {/* Table */}
      <div className="overflow-x-auto rounded-xl border border-slate-200 shadow-sm bg-white">
        <table className="w-full text-left text-sm text-slate-700">
          <thead className="bg-slate-50 text-xs uppercase font-semibold text-slate-500 border-b border-slate-200">
            <tr>
              <th className="px-4 py-3">User</th>
              <th className="px-4 py-3">Status</th>
              <th className="px-4 py-3">Geofence</th>
              <th className="px-4 py-3">Last Seen</th>
              <th className="px-4 py-3">GPS Accuracy</th>
            </tr>
          </thead>
          <tbody className="divide-y divide-slate-200">
            {isLoading ? (
              <tr>
                <td colSpan={5} className="text-center py-8 text-slate-500">
                  Loading live presence records...
                </td>
              </tr>
            ) : filtered.length === 0 ? (
              <tr>
                <td colSpan={5} className="text-center py-8 text-slate-500">
                  No user presence records matching filters.
                </td>
              </tr>
            ) : (
              filtered.map((user) => (
                <tr key={user.user_id} className="hover:bg-slate-50 transition-colors">
                  <td className="px-4 py-3">
                    <div className="font-semibold text-slate-900">{user.name}</div>
                    <div className="text-xs text-slate-500">{user.email}</div>
                  </td>
                  <td className="px-4 py-3">{getBadge(user.status)}</td>
                  <td className="px-4 py-3 text-slate-600">
                    {user.geofence_name || '--'}
                  </td>
                  <td className="px-4 py-3 text-slate-600">{formatTime(user.last_seen)}</td>
                  <td className="px-4 py-3 text-slate-600">
                    {user.accuracy ? `±${Math.round(user.accuracy)}m` : '--'}
                  </td>
                </tr>
              ))
            )}
          </tbody>
        </table>
      </div>
    </div>
  );
}
