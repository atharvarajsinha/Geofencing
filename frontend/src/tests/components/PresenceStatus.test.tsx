import React from 'react';
import { render, screen } from '@testing-library/react';
import { describe, it, expect } from 'vitest';
import { PresenceStatus } from '@/components/presence/PresenceStatus';

describe('PresenceStatus Component', () => {
  it('renders PRESENT status state correctly', () => {
    render(
      <PresenceStatus
        data={{
          status: 'PRESENT',
          check_in_time: '2026-08-26T09:04:00Z',
          check_out_time: null,
          last_seen: '2026-08-26T12:24:00Z',
          geofence_name: 'College Campus',
          gps_accuracy: 8,
        }}
      />
    );

    expect(screen.getByText('Present')).toBeInTheDocument();
    expect(screen.getByText(/inside "College Campus"/i)).toBeInTheDocument();
    expect(screen.getByText('±8 meters')).toBeInTheDocument();
  });

  it('renders OUTSIDE state correctly', () => {
    render(
      <PresenceStatus
        data={{
          status: 'OUTSIDE',
          check_in_time: null,
          check_out_time: null,
          last_seen: '2026-08-26T10:42:00Z',
        }}
      />
    );

    expect(screen.getByText('Outside')).toBeInTheDocument();
    expect(screen.getByText(/outside the designated geographic area/i)).toBeInTheDocument();
  });

  it('renders LOCATION_REQUIRED state with Enable Location button', () => {
    render(
      <PresenceStatus
        statusOverride="LOCATION_REQUIRED"
        onEnableLocation={() => {}}
      />
    );

    expect(screen.getByText('Location Permission Required')).toBeInTheDocument();
    expect(screen.getByRole('button', { name: /enable location/i })).toBeInTheDocument();
  });

  it('renders LOCATION_ERROR state with custom message and retry button', () => {
    render(
      <PresenceStatus
        statusOverride="LOCATION_ERROR"
        errorMessage="GPS Signal Lost"
        onRetryLocation={() => {}}
      />
    );

    expect(screen.getByText('Location Error')).toBeInTheDocument();
    expect(screen.getByText('GPS Signal Lost')).toBeInTheDocument();
    expect(screen.getByRole('button', { name: /retry location/i })).toBeInTheDocument();
  });
});
