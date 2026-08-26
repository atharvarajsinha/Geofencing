import { apiClient } from './client';
import { ApiResponse } from '@/types/api';
import { AuthResponseData, LoginCredentials } from '@/types/auth';
import { setAuthTokens, setStoredUser, clearAuthTokens } from '@/lib/auth/token';

export async function login(credentials: LoginCredentials): Promise<AuthResponseData> {
  const response = await apiClient.post<ApiResponse<AuthResponseData>>('/auth/login/', credentials);
  const data = response.data.data;
  setAuthTokens(data.access, data.refresh);
  setStoredUser(data.user);
  return data;
}

export async function logout(): Promise<void> {
  clearAuthTokens();
}
