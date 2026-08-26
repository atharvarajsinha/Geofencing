'use client';

import { useEffect } from 'react';
import { useRouter } from 'next/navigation';
import { useAuth } from '@/hooks/useAuth';
import { Spinner } from '@/components/ui/Spinner';

export default function RootPage() {
  const { isAuthenticated, isAdmin, isLoading } = useAuth();
  const router = useRouter();

  useEffect(() => {
    if (isLoading) return;
    if (!isAuthenticated) {
      router.replace('/login');
    } else if (isAdmin) {
      router.replace('/admin/dashboard');
    } else {
      router.replace('/dashboard');
    }
  }, [isAuthenticated, isAdmin, isLoading, router]);

  return (
    <div className="h-screen w-full flex items-center justify-center bg-slate-50">
      <Spinner size="lg" />
    </div>
  );
}
