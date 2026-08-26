import React from 'react';
import { AdminStats } from '@/types/presence';
import { Card } from '@/components/ui/Card';
import { Users, CheckCircle2, XCircle, AlertTriangle, HelpCircle } from 'lucide-react';

interface StatsCardsProps {
  stats?: AdminStats | null;
  isLoading?: boolean;
}

export function StatsCards({ stats, isLoading = false }: StatsCardsProps) {
  if (isLoading) {
    return (
      <div className="grid grid-cols-2 sm:grid-cols-4 gap-4">
        {[1, 2, 3, 4].map((i) => (
          <div key={i} className="h-24 bg-slate-100 animate-pulse rounded-xl" />
        ))}
      </div>
    );
  }

  const items = [
    {
      title: 'Total Users',
      value: stats?.total_users ?? 0,
      icon: Users,
      color: 'text-slate-700 bg-slate-100',
    },
    {
      title: 'Present',
      value: stats?.present ?? 0,
      icon: CheckCircle2,
      color: 'text-emerald-700 bg-emerald-50 border-emerald-200',
    },
    {
      title: 'Gone',
      value: stats?.gone ?? 0,
      icon: XCircle,
      color: 'text-amber-700 bg-amber-50 border-amber-200',
    },
    {
      title: 'Stale',
      value: stats?.stale ?? 0,
      icon: AlertTriangle,
      color: 'text-slate-700 bg-slate-100 border-slate-200',
    },
  ];

  return (
    <div className="grid grid-cols-2 sm:grid-cols-4 gap-4">
      {items.map((item) => {
        const Icon = item.icon;
        return (
          <Card key={item.title} className="p-4 flex items-center justify-between">
            <div>
              <p className="text-xs font-medium text-slate-500">{item.title}</p>
              <h3 className="text-2xl font-bold text-slate-900 mt-1">{item.value}</h3>
            </div>
            <div className={`p-2.5 rounded-xl border ${item.color}`}>
              <Icon className="w-5 h-5" />
            </div>
          </Card>
        );
      })}
    </div>
  );
}
