export function formatTime(isoString?: string | null): string {
  if (!isoString) return '--:--';
  try {
    const date = new Date(isoString);
    if (isNaN(date.getTime())) return '--:--';
    return date.toLocaleTimeString([], { hour: '2-digit', minute: '2-digit', hour12: true });
  } catch {
    return '--:--';
  }
}

export function formatDate(isoString?: string | null): string {
  if (!isoString) return '--';
  try {
    const date = new Date(isoString);
    if (isNaN(date.getTime())) return '--';
    return date.toLocaleDateString([], { day: '2-digit', month: 'short', year: 'numeric' });
  } catch {
    return '--';
  }
}

export function formatDistance(meters: number): string {
  if (meters >= 1000) {
    return `${(meters / 1000).toFixed(2)} km`;
  }
  return `${Math.round(meters)} m`;
}

export function formatRole(role?: string | null): string {
  if (!role) return 'User';
  if (role === 'SUPER_ADMIN') return 'Super Administrator';
  if (role === 'ADMIN') return 'Super Administrator';
  if (role === 'USER') return 'User';
  return role;
}
