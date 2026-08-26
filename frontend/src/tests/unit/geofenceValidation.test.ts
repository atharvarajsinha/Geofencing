import { describe, it, expect } from 'vitest';
import { z } from 'zod';

const circleSchema = z
  .object({
    name: z.string().min(2),
    type: z.literal('CIRCLE'),
    latitude: z.number(),
    longitude: z.number(),
    radius: z.number().positive(),
    entry_radius: z.number().positive(),
    exit_radius: z.number().positive(),
  })
  .refine((data) => data.exit_radius >= data.entry_radius, {
    message: 'Exit radius must be greater than or equal to Entry radius',
  });

const rectangleSchema = z
  .object({
    name: z.string().min(2),
    type: z.literal('RECTANGLE'),
    min_latitude: z.number().min(-90).max(90),
    max_latitude: z.number().min(-90).max(90),
    min_longitude: z.number().min(-180).max(180),
    max_longitude: z.number().min(-180).max(180),
    entry_radius: z.number().min(0),
    exit_radius: z.number().positive(),
  })
  .refine((data) => data.max_latitude > data.min_latitude, {
    message: 'Max latitude must be greater than min latitude',
  })
  .refine((data) => data.max_longitude > data.min_longitude, {
    message: 'Max longitude must be greater than min longitude',
  })
  .refine((data) => data.exit_radius > data.entry_radius, {
    message: 'Exit outset must be greater than the entry inset',
  });

const VALID_RECTANGLE = {
  name: 'Academic Block',
  type: 'RECTANGLE' as const,
  min_latitude: 29.5971,
  max_latitude: 29.5983,
  min_longitude: 79.6581,
  max_longitude: 79.6601,
  entry_radius: 0,
  exit_radius: 40,
};

describe('Geofence Validation Schemas', () => {
  it('validates a valid circle geofence input', () => {
    const valid = {
      name: 'College Campus',
      type: 'CIRCLE' as const,
      latitude: 29.5976,
      longitude: 79.6591,
      radius: 150,
      entry_radius: 100,
      exit_radius: 150,
    };
    const result = circleSchema.safeParse(valid);
    expect(result.success).toBe(true);
  });

  it('fails circle validation when exit_radius is smaller than entry_radius', () => {
    const invalid = {
      name: 'College Campus',
      type: 'CIRCLE' as const,
      latitude: 29.5976,
      longitude: 79.6591,
      radius: 150,
      entry_radius: 150,
      exit_radius: 100, // Invalid: exit < entry
    };
    const result = circleSchema.safeParse(invalid);
    expect(result.success).toBe(false);
  });

  it('fails circle validation when radius is negative', () => {
    const invalid = {
      name: 'College Campus',
      type: 'CIRCLE' as const,
      latitude: 29.5976,
      longitude: 79.6591,
      radius: -50,
      entry_radius: 100,
      exit_radius: 150,
    };
    const result = circleSchema.safeParse(invalid);
    expect(result.success).toBe(false);
  });

  it('validates a valid rectangle geofence input', () => {
    expect(rectangleSchema.safeParse(VALID_RECTANGLE).success).toBe(true);
  });

  it('accepts a zero entry inset - the fence edge itself counts as inside', () => {
    expect(
      rectangleSchema.safeParse({ ...VALID_RECTANGLE, entry_radius: 0 }).success
    ).toBe(true);
  });

  it('fails rectangle validation when the latitudes are inverted', () => {
    const result = rectangleSchema.safeParse({
      ...VALID_RECTANGLE,
      min_latitude: 29.5983,
      max_latitude: 29.5971,
    });
    expect(result.success).toBe(false);
  });

  it('fails rectangle validation when the longitudes are inverted', () => {
    const result = rectangleSchema.safeParse({
      ...VALID_RECTANGLE,
      min_longitude: 79.6601,
      max_longitude: 79.6581,
    });
    expect(result.success).toBe(false);
  });

  it('fails rectangle validation on a degenerate box', () => {
    const result = rectangleSchema.safeParse({
      ...VALID_RECTANGLE,
      min_latitude: 29.5971,
      max_latitude: 29.5971,
    });
    expect(result.success).toBe(false);
  });

  it('fails rectangle validation when the exit outset does not exceed the inset', () => {
    const result = rectangleSchema.safeParse({
      ...VALID_RECTANGLE,
      entry_radius: 40,
      exit_radius: 40,
    });
    expect(result.success).toBe(false);
  });

  it('fails rectangle validation on an out-of-range edge', () => {
    const result = rectangleSchema.safeParse({
      ...VALID_RECTANGLE,
      max_longitude: 200,
    });
    expect(result.success).toBe(false);
  });
});
