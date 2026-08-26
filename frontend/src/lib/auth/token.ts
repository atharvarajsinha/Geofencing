/**
 * TOKEN STORAGE & SECURITY IMPLICATIONS
 * 
 * Access and refresh tokens are stored in browser localStorage.
 * 
 * SECURITY IMPLICATIONS:
 * 1. XSS Vulnerability: LocalStorage is accessible by any JavaScript running in the same origin.
 *    If an attacker executes malicious JS (XSS), tokens can be extracted.
 *    Mitigation: Enforce strict CSP policies, sanitize all dynamic rendering, and avoid third-party script injection.
 * 2. CSRF Resilience: LocalStorage-based bearer tokens are immune to standard cross-site request forgery (CSRF)
 *    because browsers do not automatically attach localStorage headers to cross-origin requests.
 * 3. Production Recommendation: For maximum defense-in-depth in production environments, standard HTTP-Only,
 *    Secure, SameSite cookies with backend token rotation are recommended over localStorage.
 */

const ACCESS_TOKEN_KEY = 'geo_presence_access_token';
const REFRESH_TOKEN_KEY = 'geo_presence_refresh_token';
const USER_KEY = 'geo_presence_user';

export const getAccessToken = (): string | null => {
  if (typeof window === 'undefined') return null;
  return localStorage.getItem(ACCESS_TOKEN_KEY);
};

export const getRefreshToken = (): string | null => {
  if (typeof window === 'undefined') return null;
  return localStorage.getItem(REFRESH_TOKEN_KEY);
};

export const setAuthTokens = (access: string, refresh: string): void => {
  if (typeof window === 'undefined') return;
  localStorage.setItem(ACCESS_TOKEN_KEY, access);
  localStorage.setItem(REFRESH_TOKEN_KEY, refresh);
};

export const clearAuthTokens = (): void => {
  if (typeof window === 'undefined') return;
  localStorage.removeItem(ACCESS_TOKEN_KEY);
  localStorage.removeItem(REFRESH_TOKEN_KEY);
  localStorage.removeItem(USER_KEY);
};

export const getStoredUser = (): any | null => {
  if (typeof window === 'undefined') return null;
  const raw = localStorage.getItem(USER_KEY);
  if (!raw) return null;
  try {
    return JSON.parse(raw);
  } catch {
    return null;
  }
};

export const setStoredUser = (user: any): void => {
  if (typeof window === 'undefined') return;
  localStorage.setItem(USER_KEY, JSON.stringify(user));
};
