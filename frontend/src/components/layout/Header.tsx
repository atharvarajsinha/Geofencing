'use client';

import React from 'react';
import Link from 'next/link';
import { useRouter, usePathname } from 'next/navigation';
import { useAuth } from '@/hooks/useAuth';
import { usePwa } from '@/hooks/usePwa';
import { Button } from '@/components/ui/Button';
import { Badge } from '@/components/ui/Badge';
import { formatRole } from '@/lib/utils/formatters';
import { MapPin, LogOut, Download, User as UserIcon, ShieldAlert } from 'lucide-react';

export function Header() {
  const { user, isAuthenticated, isAdmin, logout } = useAuth();
  const { isInstallable, isInstalled, promptInstall } = usePwa();
  const router = useRouter();
  const pathname = usePathname();

  if (!isAuthenticated || pathname === '/login') return null;

  const handleLogout = async () => {
    await logout();
    router.push('/login');
  };

  return (
    <header className="sticky top-0 z-40 bg-white/95 backdrop-blur-md border-b border-slate-200">
      <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8">
        <div className="flex items-center justify-between h-16">
          {/* Logo & App Title */}
          <Link href={isAdmin ? '/admin/dashboard' : '/dashboard'} className="flex items-center space-x-2">
            <div className="w-9 h-9 rounded-xl bg-sky-600 flex items-center justify-center text-white shadow-sm">
              <MapPin className="w-5 h-5" />
            </div>
            <div>
              <span className="font-bold text-slate-900 tracking-tight text-lg">GeoPresence</span>
              <span className="text-xs text-sky-600 font-semibold block leading-none">PWA</span>
            </div>
          </Link>

          {/* Desktop Navigation Links */}
          <nav className="hidden md:flex items-center space-x-6">
            {!isAdmin ? (
              <>
                <Link
                  href="/dashboard"
                  className={`text-sm font-medium transition-colors ${
                    pathname === '/dashboard' ? 'text-sky-600 font-semibold' : 'text-slate-600 hover:text-slate-900'
                  }`}
                >
                  My Presence
                </Link>
                <Link
                  href="/attendance"
                  className={`text-sm font-medium transition-colors ${
                    pathname === '/attendance' ? 'text-sky-600 font-semibold' : 'text-slate-600 hover:text-slate-900'
                  }`}
                >
                  Attendance History
                </Link>
                <Link
                  href="/profile"
                  className={`text-sm font-medium transition-colors ${
                    pathname === '/profile' ? 'text-sky-600 font-semibold' : 'text-slate-600 hover:text-slate-900'
                  }`}
                >
                  Profile
                </Link>
              </>
            ) : (
              <>
                <Link
                  href="/admin/dashboard"
                  className={`text-sm font-medium transition-colors ${
                    pathname.startsWith('/admin/dashboard') ? 'text-sky-600 font-semibold' : 'text-slate-600 hover:text-slate-900'
                  }`}
                >
                  Overview
                </Link>
                <Link
                  href="/admin/presence/map"
                  className={`text-sm font-medium transition-colors ${
                    pathname.startsWith('/admin/presence') ? 'text-sky-600 font-semibold' : 'text-slate-600 hover:text-slate-900'
                  }`}
                >
                  Live Presence Map
                </Link>
                <Link
                  href="/admin/geofences"
                  className={`text-sm font-medium transition-colors ${
                    pathname.startsWith('/admin/geofences') ? 'text-sky-600 font-semibold' : 'text-slate-600 hover:text-slate-900'
                  }`}
                >
                  Geofences
                </Link>
              </>
            )}
          </nav>

          {/* Actions & User Info */}
          <div className="flex items-center space-x-3">
            {!isInstalled && (
              <Button
                size="sm"
                variant="outline"
                onClick={() => {
                  if (isInstallable) {
                    promptInstall();
                  } else {
                    alert(
                      'To install this PWA:\n\n• Chrome / Edge (Desktop or Android): Open browser menu (⋮) -> Install App / Add to Home Screen.\n• iOS Safari: Tap Share icon -> Add to Home Screen.\n\nNote: Automated 1-click install requires running a production build (npm run build && npm run start).'
                    );
                  }
                }}
                className="hidden sm:inline-flex"
              >
                <Download className="w-3.5 h-3.5 mr-1.5" />
                Install App
              </Button>
            )}

            {user && (
              <div className="hidden sm:flex items-center space-x-2 text-sm text-slate-700 bg-slate-100 px-3 py-1.5 rounded-full">
                <UserIcon className="w-4 h-4 text-slate-500" />
                <span className="font-medium">{user.name}</span>
                <Badge variant={user.role === 'SUPER_ADMIN' ? 'info' : 'neutral'}>{formatRole(user.role)}</Badge>
              </div>
            )}

            <Button size="sm" variant="ghost" onClick={handleLogout} title="Logout">
              <LogOut className="w-4 h-4 text-slate-600 hover:text-red-600" />
            </Button>
          </div>
        </div>
      </div>
    </header>
  );
}
