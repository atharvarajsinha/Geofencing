import { useState, useEffect, useCallback } from 'react';
import { User, LoginCredentials } from '@/types/auth';
import { login as apiLogin, logout as apiLogout } from '@/api/auth';
import { getStoredUser, getAccessToken } from '@/lib/auth/token';

export function useAuth() {
  const [user, setUser] = useState<User | null>(null);
  const [isLoading, setIsLoading] = useState<boolean>(true);

  useEffect(() => {
    const token = getAccessToken();
    const stored = getStoredUser();
    if (token && stored) {
      setUser(stored);
    } else {
      setUser(null);
    }
    setIsLoading(false);
  }, []);

  const loginUser = useCallback(async (credentials: LoginCredentials) => {
    setIsLoading(true);
    try {
      const data = await apiLogin(credentials);
      setUser(data.user);
      return data.user;
    } finally {
      setIsLoading(false);
    }
  }, []);

  const logoutUser = useCallback(async () => {
    setIsLoading(true);
    try {
      await apiLogout();
      setUser(null);
    } finally {
      setIsLoading(false);
    }
  }, []);

  return {
    user,
    isAuthenticated: !!user && !!getAccessToken(),
    isAdmin: user?.role === 'ADMIN' || user?.role === 'SUPER_ADMIN',
    // SUPER_ADMIN only. Treating a plain ADMIN as super-admin would let the UI
    // offer actions the backend rejects.
    isSuperAdmin: user?.role === 'SUPER_ADMIN',
    isLoading,
    login: loginUser,
    logout: logoutUser,
  };
}
