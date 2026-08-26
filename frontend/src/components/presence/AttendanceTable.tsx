import React from 'react';
import { AttendanceRecord } from '@/types/presence';
import { formatDate, formatTime } from '@/lib/utils/formatters';
import { Badge } from '@/components/ui/Badge';

interface AttendanceTableProps {
  records: AttendanceRecord[];
  isLoading?: boolean;
}

export function AttendanceTable({ records, isLoading = false }: AttendanceTableProps) {
  const safeRecords = Array.isArray(records) ? records : [];

  if (isLoading) {
    return (
      <div className="space-y-3">
        {[1, 2, 3].map((i) => (
          <div key={i} className="h-12 bg-slate-100 animate-pulse rounded-lg" />
        ))}
      </div>
    );
  }

  if (safeRecords.length === 0) {
    return (
      <div className="text-center py-8 bg-slate-50 rounded-xl border border-dashed border-slate-200">
        <p className="text-sm text-slate-500">No attendance history records found.</p>
      </div>
    );
  }

  const getStatusBadge = (status: string) => {
    switch (status) {
      case 'PRESENT':
        return <Badge variant="success">PRESENT</Badge>;
      case 'GONE':
      case 'OUTSIDE':
        return <Badge variant="warning">GONE</Badge>;
      default:
        return <Badge variant="neutral">{status}</Badge>;
    }
  };

  return (
    <div className="overflow-x-auto rounded-xl border border-slate-200 shadow-sm">
      <table className="w-full text-left text-sm text-slate-700">
        <thead className="bg-slate-50 text-xs uppercase font-semibold text-slate-500 border-b border-slate-200">
          <tr>
            <th className="px-4 py-3">Date</th>
            <th className="px-4 py-3">Check In</th>
            <th className="px-4 py-3">Check Out</th>
            <th className="px-4 py-3">Status</th>
          </tr>
        </thead>
        <tbody className="divide-y divide-slate-200 bg-white">
          {safeRecords.map((row, index) => (
            <tr key={row.id || index} className="hover:bg-slate-50 transition-colors">
              <td className="px-4 py-3 font-medium text-slate-900">{formatDate(row.date)}</td>
              <td className="px-4 py-3 text-slate-600">{formatTime(row.check_in)}</td>
              <td className="px-4 py-3 text-slate-600">{formatTime(row.check_out)}</td>
              <td className="px-4 py-3">{getStatusBadge(row.status)}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}
