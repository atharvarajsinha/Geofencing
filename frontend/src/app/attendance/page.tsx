'use client';

import React from 'react';
import { usePresenceHistory, usePresence } from '@/hooks/usePresence';
import { PageContainer } from '@/components/layout/PageContainer';
import { AttendanceTable } from '@/components/presence/AttendanceTable';
import { Card, CardHeader, CardTitle } from '@/components/ui/Card';
import { formatTime } from '@/lib/utils/formatters';
import { Calendar, Clock, CheckCircle2 } from 'lucide-react';

export default function AttendanceHistoryPage() {
  const { data: presence } = usePresence();
  const { data: history = [], isLoading } = usePresenceHistory();

  return (
    <PageContainer className="space-y-6">
      <div>
        <h1 className="text-2xl font-bold text-slate-900 tracking-tight">Attendance History</h1>
        <p className="text-xs text-slate-500">View your daily check-in and check-out presence records.</p>
      </div>

      {/* Today Summary */}
      <Card className="bg-gradient-to-r from-sky-600 to-sky-700 text-white p-5">
        <div className="flex items-center justify-between mb-4">
          <span className="text-xs uppercase font-semibold tracking-wider text-sky-100">Today's Presence</span>
          <Calendar className="w-5 h-5 text-sky-200" />
        </div>
        <div className="grid grid-cols-2 gap-4">
          <div>
            <span className="text-xs text-sky-200 block">Check-In</span>
            <span className="text-xl font-bold">{formatTime(presence?.check_in_time)}</span>
          </div>
          <div>
            <span className="text-xs text-sky-200 block">Check-Out</span>
            <span className="text-xl font-bold">{formatTime(presence?.check_out_time)}</span>
          </div>
        </div>
      </Card>

      {/* History Table */}
      <div className="space-y-3">
        <h2 className="text-lg font-semibold text-slate-900">Past Records</h2>
        <AttendanceTable records={history} isLoading={isLoading} />
      </div>
    </PageContainer>
  );
}
