'use client';

import React from 'react';
import Link from 'next/link';
import { usePathname } from 'next/navigation';
import { useAuth } from '@/hooks/useAuth';
import { Home, Calendar, User, Map, Layers, ShieldCheck } from 'lucide-react';
import { cn } from '@/lib/utils/cn';

export function MobileNav() {
  const { isAuthenticated, isAdmin } = useAuth();
  const pathname = usePathname();

  if (!isAuthenticated || pathname === '/login') return null;

  const userItems = [
    { label: 'Presence', href: '/dashboard', icon: Home },
    { label: 'Attendance', href: '/attendance', icon: Calendar },
    { label: 'Profile', href: '/profile', icon: User },
  ];

  const adminItems = [
    { label: 'Admin', href: '/admin/dashboard', icon: ShieldCheck },
    { label: 'Live Map', href: '/admin/presence/map', icon: Map },
    { label: 'Fences', href: '/admin/geofences', icon: Layers },
    { label: 'Profile', href: '/profile', icon: User },
  ];

  const items = isAdmin ? adminItems : userItems;

  return (
    <div className="md:hidden fixed bottom-0 left-0 right-0 z-40 bg-white/95 backdrop-blur-md border-t border-slate-200 pb-safe">
      <nav className="flex justify-around items-center h-16 px-2">
        {items.map((item) => {
          const Icon = item.icon;
          const isActive = pathname === item.href || (item.href !== '/dashboard' && item.href !== '/admin/dashboard' && pathname.startsWith(item.href));

          return (
            <Link
              key={item.href}
              href={item.href}
              className={cn(
                'flex flex-col items-center justify-center w-full h-full py-1 text-xs font-medium transition-colors touch-manipulation',
                isActive ? 'text-sky-600 font-semibold' : 'text-slate-500 hover:text-slate-900'
              )}
            >
              <Icon className={cn('w-5 h-5 mb-0.5', isActive ? 'text-sky-600' : 'text-slate-400')} />
              <span>{item.label}</span>
            </Link>
          );
        })}
      </nav>
    </div>
  );
}
