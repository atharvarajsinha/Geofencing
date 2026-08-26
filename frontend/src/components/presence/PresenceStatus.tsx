import React from 'react';
import { PresenceStatusType, UserPresenceData } from '@/types/presence';
import { formatTime, formatDate } from '@/lib/utils/formatters';
import { Button } from '@/components/ui/Button';
import {
  CheckCircle2,
  XCircle,
  AlertTriangle,
  HelpCircle,
  MapPinOff,
  AlertOctagon,
  RefreshCw,
  Clock,
  Radio,
} from 'lucide-react';
import { cn } from '@/lib/utils/cn';

interface PresenceStatusProps {
  data?: UserPresenceData | null;
  statusOverride?: PresenceStatusType;
  errorMessage?: string | null;
  onEnableLocation?: () => void;
  onRetryLocation?: () => void;
  isLoading?: boolean;
}

export function PresenceStatus({
  data,
  statusOverride,
  errorMessage,
  onEnableLocation,
  onRetryLocation,
  isLoading = false,
}: PresenceStatusProps) {
  const currentStatus: PresenceStatusType = statusOverride || data?.status || 'UNKNOWN';

  const getStatusConfig = () => {
    switch (currentStatus) {
      case 'PRESENT':
        return {
          title: 'Present',
          description: data?.geofence_name
            ? `You are inside "${data.geofence_name}".`
            : 'You are inside the designated geographic area.',
          bgColor: 'bg-emerald-50 border-emerald-200',
          textColor: 'text-emerald-900',
          dotColor: 'bg-emerald-500',
          icon: CheckCircle2,
          iconColor: 'text-emerald-600',
        };
      case 'GONE':
      case 'OUTSIDE':
        return {
          title: 'Outside',
          description: 'You are currently outside the designated geographic area.',
          bgColor: 'bg-amber-50 border-amber-200',
          textColor: 'text-amber-900',
          dotColor: 'bg-amber-500',
          icon: XCircle,
          iconColor: 'text-amber-600',
        };
      case 'STALE':
        return {
          title: 'Location Unavailable',
          description: "We haven't received a recent location update from your device.",
          bgColor: 'bg-slate-100 border-slate-300',
          textColor: 'text-slate-900',
          dotColor: 'bg-slate-400',
          icon: AlertTriangle,
          iconColor: 'text-slate-600',
        };
      case 'LOCATION_REQUIRED':
        return {
          title: 'Location Permission Required',
          description: 'Location access is required to determine your presence status.',
          bgColor: 'bg-sky-50 border-sky-200',
          textColor: 'text-sky-900',
          dotColor: 'bg-sky-500',
          icon: MapPinOff,
          iconColor: 'text-sky-600',
        };
      case 'LOCATION_ERROR':
        return {
          title: 'Location Error',
          description: errorMessage || 'Unable to retrieve your current location.',
          bgColor: 'bg-rose-50 border-rose-200',
          textColor: 'text-rose-900',
          dotColor: 'bg-rose-500',
          icon: AlertOctagon,
          iconColor: 'text-rose-600',
        };
      case 'SYNCING':
        return {
          title: 'Updating Location...',
          description: 'Synchronizing your current location with the server.',
          bgColor: 'bg-blue-50 border-blue-200',
          textColor: 'text-blue-900',
          dotColor: 'bg-blue-500',
          icon: RefreshCw,
          iconColor: 'text-blue-600 animate-spin',
        };
      case 'UNKNOWN':
      default:
        return {
          title: 'Status Unavailable',
          description: 'Unable to determine presence status at this moment.',
          bgColor: 'bg-slate-50 border-slate-200',
          textColor: 'text-slate-800',
          dotColor: 'bg-slate-400',
          icon: HelpCircle,
          iconColor: 'text-slate-500',
        };
    }
  };

  const config = getStatusConfig();
  const IconComponent = config.icon;

  return (
    <div className={cn('rounded-2xl border p-6 text-center transition-all shadow-sm', config.bgColor)}>
      {/* Animated Pulse Dot + Status Icon */}
      <div className="relative inline-flex items-center justify-center mb-4">
        <div className={cn('w-16 h-16 rounded-full flex items-center justify-center bg-white shadow-md')}>
          <IconComponent className={cn('w-9 h-9', config.iconColor)} />
        </div>
        <span className="absolute top-0 right-0 flex h-4 w-4">
          <span
            className={cn(
              'animate-ping absolute inline-flex h-full w-full rounded-full opacity-75',
              config.dotColor
            )}
          />
          <span className={cn('relative inline-flex rounded-full h-4 w-4', config.dotColor)} />
        </span>
      </div>

      <h2 className={cn('text-2xl font-bold tracking-tight mb-1', config.textColor)}>{config.title}</h2>
      <p className="text-sm text-slate-600 max-w-xs mx-auto mb-6">{config.description}</p>

      {/* Action Buttons for Permission/Error */}
      {currentStatus === 'LOCATION_REQUIRED' && onEnableLocation && (
        <Button onClick={onEnableLocation} className="w-full sm:w-auto px-6">
          <Radio className="w-4 h-4 mr-2" />
          Enable Location
        </Button>
      )}

      {currentStatus === 'LOCATION_ERROR' && onRetryLocation && (
        <Button onClick={onRetryLocation} variant="outline" className="w-full sm:w-auto px-6">
          <RefreshCw className="w-4 h-4 mr-2" />
          Retry Location
        </Button>
      )}

      {/* Detail Metrics */}
      {data && currentStatus !== 'LOCATION_REQUIRED' && (
        <div className="grid grid-cols-2 gap-3 pt-4 border-t border-slate-200/80 text-left">
          <div className="bg-white/80 backdrop-blur-sm p-3 rounded-xl border border-slate-200">
            <div className="text-xs font-medium text-slate-500 flex items-center mb-1">
              <Clock className="w-3.5 h-3.5 mr-1 text-slate-400" />
              Check-in
            </div>
            <div className="text-sm font-semibold text-slate-900">
              {formatTime(data.check_in_time)}
            </div>
          </div>

          <div className="bg-white/80 backdrop-blur-sm p-3 rounded-xl border border-slate-200">
            <div className="text-xs font-medium text-slate-500 flex items-center mb-1">
              <Radio className="w-3.5 h-3.5 mr-1 text-slate-400" />
              Last Seen
            </div>
            <div className="text-sm font-semibold text-slate-900">{formatTime(data.last_seen)}</div>
          </div>
        </div>
      )}

      {data?.gps_accuracy && (
        <div className="mt-3 text-xs text-slate-500">
          GPS Accuracy: <span className="font-semibold text-slate-700">±{Math.round(data.gps_accuracy)} meters</span>
        </div>
      )}
    </div>
  );
}
