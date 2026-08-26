'use client';

import React, { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import { useForm } from 'react-hook-form';
import { z } from 'zod';
import {
  CreateGeofenceInput,
  Geofence,
  GeofenceBounds,
  GeofenceType,
} from '@/types/geofence';
import { Input } from '@/components/ui/Input';
import { Button } from '@/components/ui/Button';
import { DynamicGeofenceEditorMap } from '@/components/maps/DynamicMap';
import {
  GeolocationFailure,
  getCurrentPositionOnce,
  isValidCoordinate,
  readStoredLocation,
} from '@/lib/location/geolocation';
import { boundsAround, boundsSizeMetres, isValidBounds } from '@/lib/location/bounds';
import { MapPin, Square, RotateCcw, AlertTriangle, Loader2 } from 'lucide-react';

const circleSchema = z
  .object({
    name: z.string().min(2, 'Name must be at least 2 characters'),
    type: z.literal('CIRCLE'),
    latitude: z.number({ invalid_type_error: 'Latitude required' }),
    longitude: z.number({ invalid_type_error: 'Longitude required' }),
    radius: z.number().positive('Radius must be greater than 0'),
    entry_radius: z.number().positive('Entry radius must be greater than 0'),
    exit_radius: z.number().positive('Exit radius must be greater than 0'),
    is_active: z.boolean().default(true),
  })
  .refine((data) => data.exit_radius >= data.entry_radius, {
    message: 'Exit radius must be greater than or equal to Entry radius',
    path: ['exit_radius'],
  });

const rectangleSchema = z
  .object({
    name: z.string().min(2, 'Name must be at least 2 characters'),
    type: z.literal('RECTANGLE'),
    min_latitude: z.number({ invalid_type_error: 'Southern edge required' }).min(-90).max(90),
    max_latitude: z.number({ invalid_type_error: 'Northern edge required' }).min(-90).max(90),
    min_longitude: z.number({ invalid_type_error: 'Western edge required' }).min(-180).max(180),
    max_longitude: z.number({ invalid_type_error: 'Eastern edge required' }).min(-180).max(180),
    entry_radius: z.number().min(0, 'Entry inset must not be negative'),
    exit_radius: z.number().positive('Exit outset must be greater than 0'),
    is_active: z.boolean().default(true),
  })
  .refine((data) => data.max_latitude > data.min_latitude, {
    message: 'Max latitude must be greater than min latitude',
    path: ['max_latitude'],
  })
  .refine((data) => data.max_longitude > data.min_longitude, {
    message: 'Max longitude must be greater than min longitude',
    path: ['max_longitude'],
  })
  .refine((data) => data.exit_radius > data.entry_radius, {
    message: 'Exit outset must be greater than the entry inset',
    path: ['exit_radius'],
  });

/** Half-side of the box a brand-new rectangle geofence starts as. */
const DEFAULT_RECTANGLE_HALF_SIDE_M = 100;

interface GeofenceFormProps {
  initialValues?: Geofence;
  onSubmit: (data: CreateGeofenceInput) => Promise<void>;
  isLoading?: boolean;
}

export function GeofenceForm({ initialValues, onSubmit, isLoading = false }: GeofenceFormProps) {
  const [type, setType] = useState<GeofenceType>(initialValues?.type || 'CIRCLE');

  // Opening centre: the geofence being edited, else the last known device
  // position, else nothing - the map then opens wide and asks for a fix rather
  // than silently pointing at a hardcoded city.
  const getInitialCenter = (): { lat: number | null; lng: number | null } => {
    if (initialValues?.type === 'CIRCLE') {
      return { lat: initialValues.center_latitude, lng: initialValues.center_longitude };
    }
    const cached = readStoredLocation();
    if (cached) return { lat: cached.latitude, lng: cached.longitude };
    return { lat: null, lng: null };
  };

  const getInitialBounds = (): GeofenceBounds | null => {
    if (initialValues?.type === 'RECTANGLE' && isValidBounds(initialValues)) {
      return {
        min_latitude: initialValues.min_latitude,
        max_latitude: initialValues.max_latitude,
        min_longitude: initialValues.min_longitude,
        max_longitude: initialValues.max_longitude,
      };
    }
    return null;
  };

  // Circle state
  const [{ lat: initialLat, lng: initialLng }] = useState(getInitialCenter);
  const [centerLat, setCenterLat] = useState<number | null>(initialLat);
  const [centerLng, setCenterLng] = useState<number | null>(initialLng);

  // Rectangle state
  const [bounds, setBounds] = useState<GeofenceBounds | null>(getInitialBounds);

  const [isLocating, setIsLocating] = useState<boolean>(false);
  const [locationFailure, setLocationFailure] = useState<GeolocationFailure | null>(null);
  // Once the admin has positioned the fence, an in-flight auto-locate must not
  // move it out from under them.
  const shapeTouchedRef = useRef<boolean>(Boolean(initialValues));

  const [formError, setFormError] = useState<string | null>(null);

  const {
    register,
    handleSubmit,
    setValue,
    watch,
    formState: { errors },
  } = useForm<any>({
    defaultValues: {
      name: initialValues?.name || '',
      radius: initialValues?.type === 'CIRCLE' ? initialValues.radius : 150,
      entry_radius:
        initialValues?.entry_radius ?? (initialValues?.type === 'RECTANGLE' ? 0 : 100),
      exit_radius:
        initialValues?.exit_radius ?? (initialValues?.type === 'RECTANGLE' ? 40 : 150),
      is_active: initialValues?.is_active ?? true,
    },
  });

  const watchRadius = watch('radius', 150);
  const watchEntryRadius = watch('entry_radius', type === 'RECTANGLE' ? 0 : 100);
  const watchExitRadius = watch('exit_radius', type === 'RECTANGLE' ? 40 : 150);

  const applyCenter = useCallback((lat: number, lng: number) => {
    setCenterLat(lat);
    setCenterLng(lng);
  }, []);

  const handleCenterChange = useCallback(
    (lat: number, lng: number) => {
      shapeTouchedRef.current = true;
      applyCenter(lat, lng);
    },
    [applyCenter]
  );

  const handleBoundsChange = useCallback((next: GeofenceBounds) => {
    shapeTouchedRef.current = true;
    setBounds(next);
  }, []);

  /** Edit one edge from the numeric inputs without disturbing the other three. */
  const handleEdgeChange = useCallback((edge: keyof GeofenceBounds, value: number) => {
    shapeTouchedRef.current = true;
    setBounds((prev) => {
      const base: GeofenceBounds = prev ?? {
        min_latitude: Number.NaN,
        max_latitude: Number.NaN,
        min_longitude: Number.NaN,
        max_longitude: Number.NaN,
      };
      return { ...base, [edge]: value };
    });
  }, []);

  const handleResetRectangle = useCallback(() => {
    setBounds(null);
    shapeTouchedRef.current = false;
  }, []);

  /**
   * Switching type keeps whatever the admin has already positioned and derives
   * a sensible starting shape for the other mode, so toggling never loses work.
   */
  const handleTypeChange = useCallback(
    (next: GeofenceType) => {
      setType(next);
      setFormError(null);

      if (next === 'RECTANGLE') {
        if (!bounds && isValidCoordinate(centerLat, centerLng)) {
          setBounds(
            boundsAround(
              centerLat as number,
              centerLng as number,
              DEFAULT_RECTANGLE_HALF_SIDE_M
            )
          );
        }
        // Hysteresis means different things per shape: for a rectangle these are
        // an inset and an outset in metres, not radii.
        setValue('entry_radius', 0);
        setValue('exit_radius', 40);
        return;
      }

      if (!isValidCoordinate(centerLat, centerLng) && bounds && isValidBounds(bounds)) {
        setCenterLat((bounds.min_latitude + bounds.max_latitude) / 2);
        setCenterLng((bounds.min_longitude + bounds.max_longitude) / 2);
      }
      const nominal = Number(watchRadius) || 150;
      setValue('entry_radius', nominal);
      setValue('exit_radius', nominal + 40);
    },
    [bounds, centerLat, centerLng, setValue, watchRadius]
  );

  const rectangleSize = useMemo(
    () => (bounds && isValidBounds(bounds) ? boundsSizeMetres(bounds) : null),
    [bounds]
  );

  const onFormSubmit = async (data: any) => {
    setFormError(null);

    if (type === 'CIRCLE') {
      if (!isValidCoordinate(centerLat, centerLng)) {
        setFormError(
          'Set the geofence centre first - click the map, drag the pin, or use "Center My Location".'
        );
        return;
      }

      const parsed = circleSchema.safeParse({
        ...data,
        type: 'CIRCLE',
        latitude: centerLat,
        longitude: centerLng,
        radius: Number(data.radius),
        entry_radius: Number(data.entry_radius),
        exit_radius: Number(data.exit_radius),
      });

      if (!parsed.success) {
        setFormError(parsed.error.errors[0]?.message || 'Validation error');
        return;
      }

      await onSubmit(parsed.data as CreateGeofenceInput);
      return;
    }

    if (!bounds) {
      setFormError(
        'Draw the rectangle first - click two opposite corners on the map, or type the four edges below.'
      );
      return;
    }

    const parsed = rectangleSchema.safeParse({
      name: data.name,
      type: 'RECTANGLE',
      min_latitude: Number(bounds.min_latitude),
      max_latitude: Number(bounds.max_latitude),
      min_longitude: Number(bounds.min_longitude),
      max_longitude: Number(bounds.max_longitude),
      entry_radius: Number(data.entry_radius),
      exit_radius: Number(data.exit_radius),
      is_active: data.is_active,
    });

    if (!parsed.success) {
      setFormError(parsed.error.errors[0]?.message || 'Validation error');
      return;
    }

    await onSubmit(parsed.data as CreateGeofenceInput);
  };

  /**
   * Centre the fence on the device. `explicit` marks a click on one of the
   * buttons, which always wins; the automatic call on mount defers to a shape
   * the admin has already positioned.
   */
  const locateMe = useCallback(
    async (explicit: boolean) => {
      setIsLocating(true);
      setLocationFailure(null);
      try {
        const position = await getCurrentPositionOnce();
        if (!explicit && shapeTouchedRef.current) return;

        const { latitude, longitude } = position.coords;
        if (explicit) {
          handleCenterChange(latitude, longitude);
        } else {
          applyCenter(latitude, longitude);
        }
        if (type === 'RECTANGLE' && (explicit || !bounds)) {
          setBounds(boundsAround(latitude, longitude, DEFAULT_RECTANGLE_HALF_SIDE_M));
        }
      } catch (err) {
        // Surfaced rather than swallowed: silently failing here is exactly why
        // the editor looked like it was stuck on a default location.
        setLocationFailure(err as GeolocationFailure);
      } finally {
        setIsLocating(false);
      }
    },
    [applyCenter, bounds, handleCenterChange, type]
  );

  // A new geofence starts at the admin's own position.
  useEffect(() => {
    if (initialValues) return;
    locateMe(false);
    // Run once per form instance; locateMe already guards a touched shape.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [initialValues]);

  return (
    <form onSubmit={handleSubmit(onFormSubmit)} className="space-y-6">
      {/* Super Administrator Action Banner */}
      <div className="p-3 bg-sky-50 border border-sky-200 rounded-xl text-xs text-sky-900 flex items-center justify-between gap-3">
        <span className="font-semibold">
          Super Administrator Map Studio: visually set the geofence position and boundaries.
        </span>
        <Button
          size="sm"
          variant="outline"
          type="button"
          onClick={() => locateMe(true)}
          disabled={isLocating}
          className="bg-white text-sky-700 border-sky-300 hover:bg-sky-100 shrink-0"
        >
          {isLocating ? (
            <Loader2 className="w-3.5 h-3.5 mr-1 animate-spin text-sky-600" />
          ) : (
            <MapPin className="w-3.5 h-3.5 mr-1 text-sky-600" />
          )}
          {isLocating ? 'Locating…' : 'Use My Current Location'}
        </Button>
      </div>

      {/* Geofence Name Input */}
      <Input
        label="Geofence Name"
        placeholder="e.g. Main Campus, Building A"
        error={errors.name?.message as string}
        {...register('name')}
      />

      {/* Type Toggle: Circle vs Rectangle */}
      <div>
        <label className="block text-sm font-medium text-slate-700 mb-2">Geofence Type</label>
        <div className="grid grid-cols-2 gap-3">
          <button
            type="button"
            onClick={() => handleTypeChange('CIRCLE')}
            className={`flex items-center justify-center p-3 rounded-xl border text-sm font-semibold transition-all min-h-[44px] ${
              type === 'CIRCLE'
                ? 'bg-sky-50 border-sky-600 text-sky-700 shadow-sm'
                : 'bg-white border-slate-200 text-slate-600 hover:bg-slate-50'
            }`}
          >
            <MapPin className="w-4 h-4 mr-2" />
            Circle
          </button>
          <button
            type="button"
            onClick={() => handleTypeChange('RECTANGLE')}
            className={`flex items-center justify-center p-3 rounded-xl border text-sm font-semibold transition-all min-h-[44px] ${
              type === 'RECTANGLE'
                ? 'bg-purple-50 border-purple-600 text-purple-700 shadow-sm'
                : 'bg-white border-slate-200 text-slate-600 hover:bg-slate-50'
            }`}
          >
            <Square className="w-4 h-4 mr-2" />
            Rectangle
          </button>
        </div>
      </div>

      {/* Map Drawing Studio */}
      <div className="space-y-2">
        <div className="flex items-center justify-between">
          <label className="block text-sm font-medium text-slate-700">
            {type === 'CIRCLE'
              ? 'Map Studio: set the centre and radius'
              : 'Map Studio: draw the rectangle'}
          </label>
          <div className="flex items-center space-x-2">
            <Button
              size="sm"
              variant="ghost"
              onClick={() => locateMe(true)}
              disabled={isLocating}
              type="button"
            >
              {isLocating ? (
                <Loader2 className="w-3.5 h-3.5 mr-1 animate-spin" />
              ) : (
                <MapPin className="w-3.5 h-3.5 mr-1" />
              )}
              Center My Location
            </Button>
            {type === 'RECTANGLE' && bounds && (
              <Button size="sm" variant="outline" onClick={handleResetRectangle} type="button">
                <RotateCcw className="w-3.5 h-3.5 mr-1" />
                Redraw
              </Button>
            )}
          </div>
        </div>

        {locationFailure && (
          <div className="flex items-start gap-2 rounded-xl border border-amber-200 bg-amber-50 p-3 text-xs text-amber-900">
            <AlertTriangle className="mt-0.5 h-4 w-4 shrink-0 text-amber-600" />
            <div className="flex-1">
              <p className="font-semibold">Could not use your current location</p>
              <p className="mt-0.5 leading-relaxed text-amber-800">{locationFailure.message}</p>
              <p className="mt-1 text-amber-800">
                Click the map or type coordinates below to place the geofence manually.
              </p>
            </div>
            <button
              type="button"
              onClick={() => locateMe(true)}
              className="shrink-0 rounded-md border border-amber-300 bg-white px-2 py-1 font-semibold text-amber-800 hover:bg-amber-100"
            >
              Retry
            </button>
          </div>
        )}

        <DynamicGeofenceEditorMap
          mode={type}
          centerLat={centerLat}
          centerLng={centerLng}
          radius={Number(watchRadius) || 150}
          entryRadius={Number(watchEntryRadius) || 0}
          exitRadius={Number(watchExitRadius) || 40}
          bounds={bounds}
          onCenterChange={handleCenterChange}
          onBoundsChange={handleBoundsChange}
        />
      </div>

      {/* Circle Controls */}
      {type === 'CIRCLE' && (
        <div className="space-y-4 bg-slate-50 p-4 rounded-xl border border-slate-200">
          <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
            <Input
              type="number"
              step="any"
              label="Center Latitude"
              placeholder="Click the map to set"
              value={centerLat ?? ''}
              onChange={(e) => handleCenterChange(Number(e.target.value), centerLng ?? Number.NaN)}
            />
            <Input
              type="number"
              step="any"
              label="Center Longitude"
              placeholder="Click the map to set"
              value={centerLng ?? ''}
              onChange={(e) => handleCenterChange(centerLat ?? Number.NaN, Number(e.target.value))}
            />
          </div>

          <div className="grid grid-cols-1 sm:grid-cols-3 gap-4">
            <Input
              type="number"
              label="Radius (meters)"
              error={errors.radius?.message as string}
              {...register('radius', { valueAsNumber: true })}
            />
            <Input
              type="number"
              label="Entry Radius (meters)"
              error={errors.entry_radius?.message as string}
              {...register('entry_radius', { valueAsNumber: true })}
            />
            <Input
              type="number"
              label="Exit Radius (meters)"
              error={errors.exit_radius?.message as string}
              {...register('exit_radius', { valueAsNumber: true })}
            />
          </div>
        </div>
      )}

      {/* Rectangle Controls */}
      {type === 'RECTANGLE' && (
        <div className="space-y-4 bg-slate-50 p-4 rounded-xl border border-slate-200">
          <div className="flex items-center justify-between">
            <p className="text-xs font-semibold text-slate-600">Bounding edges (WGS84)</p>
            {rectangleSize && (
              <p className="text-xs text-slate-500">
                {Math.round(rectangleSize.width)}m wide &times; {Math.round(rectangleSize.height)}m
                tall
              </p>
            )}
          </div>

          <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
            <Input
              type="number"
              step="any"
              label="Min Latitude (south edge)"
              placeholder="Click two corners on the map"
              value={Number.isFinite(bounds?.min_latitude) ? bounds!.min_latitude : ''}
              onChange={(e) => handleEdgeChange('min_latitude', Number(e.target.value))}
            />
            <Input
              type="number"
              step="any"
              label="Max Latitude (north edge)"
              placeholder="Click two corners on the map"
              value={Number.isFinite(bounds?.max_latitude) ? bounds!.max_latitude : ''}
              onChange={(e) => handleEdgeChange('max_latitude', Number(e.target.value))}
            />
            <Input
              type="number"
              step="any"
              label="Min Longitude (west edge)"
              placeholder="Click two corners on the map"
              value={Number.isFinite(bounds?.min_longitude) ? bounds!.min_longitude : ''}
              onChange={(e) => handleEdgeChange('min_longitude', Number(e.target.value))}
            />
            <Input
              type="number"
              step="any"
              label="Max Longitude (east edge)"
              placeholder="Click two corners on the map"
              value={Number.isFinite(bounds?.max_longitude) ? bounds!.max_longitude : ''}
              onChange={(e) => handleEdgeChange('max_longitude', Number(e.target.value))}
            />
          </div>

          <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
            <Input
              type="number"
              label="Entry inset (meters)"
              helperText="How far inside the box a device must be to check in."
              error={errors.entry_radius?.message as string}
              {...register('entry_radius', { valueAsNumber: true })}
            />
            <Input
              type="number"
              label="Exit outset (meters)"
              helperText="How far outside the box a device must be to check out."
              error={errors.exit_radius?.message as string}
              {...register('exit_radius', { valueAsNumber: true })}
            />
          </div>
        </div>
      )}

      {/* General Form Error Display */}
      {formError && (
        <div className="p-3 bg-red-50 border border-red-200 rounded-xl text-xs text-red-700 font-medium">
          {formError}
        </div>
      )}

      {/* Submit Button */}
      <Button type="submit" className="w-full" isLoading={isLoading}>
        {initialValues ? 'Update Geofence' : 'Save Geofence'}
      </Button>
    </form>
  );
}
