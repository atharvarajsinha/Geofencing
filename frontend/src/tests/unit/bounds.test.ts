import { describe, it, expect } from 'vitest';
import {
  METRES_PER_DEGREE_LATITUDE,
  boundsAreaKm2,
  boundsAround,
  boundsCenter,
  boundsFromCorners,
  boundsSizeMetres,
  boundsToLeaflet,
  isValidBounds,
  metresPerDegreeLongitude,
  offsetBounds,
  signedDistanceToBounds,
} from '@/lib/location/bounds';
import { GeofenceBounds } from '@/types/geofence';

const CAMPUS_LATITUDE = 29.5976;
const CAMPUS_LONGITUDE = 79.6591;

/** ~200 m x ~200 m box centred on the campus. */
const BOX: GeofenceBounds = boundsAround(CAMPUS_LATITUDE, CAMPUS_LONGITUDE, 100);

describe('metresPerDegreeLongitude', () => {
  it('is widest at the equator', () => {
    expect(metresPerDegreeLongitude(0)).toBeCloseTo(METRES_PER_DEGREE_LATITUDE, 5);
  });

  it('halves at 60 degrees', () => {
    expect(metresPerDegreeLongitude(60)).toBeCloseTo(METRES_PER_DEGREE_LATITUDE / 2, 0);
  });

  it('vanishes at the pole', () => {
    expect(metresPerDegreeLongitude(90)).toBeCloseTo(0, 6);
  });
});

describe('boundsAround', () => {
  it('produces a box of the requested half-size', () => {
    const { width, height } = boundsSizeMetres(BOX);
    expect(height).toBeCloseTo(200, 0);
    expect(width).toBeCloseTo(200, 0);
  });

  it('is centred on the requested point', () => {
    const [lat, lng] = boundsCenter(BOX);
    expect(lat).toBeCloseTo(CAMPUS_LATITUDE, 9);
    expect(lng).toBeCloseTo(CAMPUS_LONGITUDE, 9);
  });
});

describe('boundsFromCorners', () => {
  it('orders the edges regardless of which corners were clicked', () => {
    const northEastFirst = boundsFromCorners([29.6, 79.67], [29.59, 79.65]);
    const southWestFirst = boundsFromCorners([29.59, 79.65], [29.6, 79.67]);
    expect(northEastFirst).toEqual(southWestFirst);
    expect(northEastFirst.min_latitude).toBe(29.59);
    expect(northEastFirst.max_latitude).toBe(29.6);
    expect(northEastFirst.min_longitude).toBe(79.65);
    expect(northEastFirst.max_longitude).toBe(79.67);
  });

  it('handles the two remaining diagonal orderings', () => {
    const northWestFirst = boundsFromCorners([29.6, 79.65], [29.59, 79.67]);
    expect(northWestFirst.min_latitude).toBe(29.59);
    expect(northWestFirst.max_longitude).toBe(79.67);
  });
});

describe('isValidBounds', () => {
  it('accepts an ordered box', () => {
    expect(isValidBounds(BOX)).toBe(true);
  });

  it('rejects null and undefined', () => {
    expect(isValidBounds(null)).toBe(false);
    expect(isValidBounds(undefined)).toBe(false);
  });

  it('rejects an inverted box rather than silently ordering it', () => {
    expect(
      isValidBounds({
        min_latitude: BOX.max_latitude,
        max_latitude: BOX.min_latitude,
        min_longitude: BOX.min_longitude,
        max_longitude: BOX.max_longitude,
      })
    ).toBe(false);
  });

  it('rejects a degenerate box', () => {
    expect(
      isValidBounds({
        min_latitude: 29.6,
        max_latitude: 29.6,
        min_longitude: 79.65,
        max_longitude: 79.67,
      })
    ).toBe(false);
  });

  it('rejects a partial or non-numeric box', () => {
    expect(isValidBounds({ min_latitude: 29.5 })).toBe(false);
    expect(
      isValidBounds({
        min_latitude: Number.NaN,
        max_latitude: 29.6,
        min_longitude: 79.65,
        max_longitude: 79.67,
      })
    ).toBe(false);
  });
});

describe('offsetBounds', () => {
  it('grows a box by the requested distance', () => {
    const grown = offsetBounds(BOX, 50);
    expect(grown).not.toBeNull();
    const { width, height } = boundsSizeMetres(grown!);
    // 50 m added on each of the four sides.
    expect(height).toBeCloseTo(300, 0);
    expect(width).toBeCloseTo(300, 0);
  });

  it('shrinks a box with a negative distance', () => {
    const shrunk = offsetBounds(BOX, -50);
    expect(shrunk).not.toBeNull();
    const { width, height } = boundsSizeMetres(shrunk!);
    expect(height).toBeCloseTo(100, 0);
    expect(width).toBeCloseTo(100, 0);
  });

  it('returns null rather than an inverted box when the inset is too large', () => {
    // The box is 200 m across; insetting 150 m per side would invert it.
    expect(offsetBounds(BOX, -150)).toBeNull();
  });

  it('returns a copy for a zero offset', () => {
    const same = offsetBounds(BOX, 0);
    expect(same).toEqual(BOX);
    expect(same).not.toBe(BOX);
  });

  it('rejects a non-finite offset', () => {
    expect(offsetBounds(BOX, Number.NaN)).toBeNull();
  });
});

describe('signedDistanceToBounds', () => {
  it('is negative inside, by the distance to the nearest edge', () => {
    expect(signedDistanceToBounds(CAMPUS_LATITUDE, CAMPUS_LONGITUDE, BOX)).toBeCloseTo(
      -100,
      0
    );
  });

  it('is zero on an edge', () => {
    expect(
      signedDistanceToBounds(BOX.min_latitude, CAMPUS_LONGITUDE, BOX)
    ).toBeCloseTo(0, 2);
  });

  it('is positive outside', () => {
    const latitude = BOX.max_latitude + 100 / METRES_PER_DEGREE_LATITUDE;
    expect(signedDistanceToBounds(latitude, CAMPUS_LONGITUDE, BOX)).toBeCloseTo(100, 0);
  });

  it('measures to the corner when outside on both axes', () => {
    const latitude = BOX.max_latitude + 100 / METRES_PER_DEGREE_LATITUDE;
    const longitude =
      BOX.max_longitude + 100 / metresPerDegreeLongitude(CAMPUS_LATITUDE);
    expect(signedDistanceToBounds(latitude, longitude, BOX)).toBeCloseTo(141.42, 0);
  });

  it('flips sign exactly at the boundary', () => {
    const epsilon = 0.01 / METRES_PER_DEGREE_LATITUDE;
    const inside = signedDistanceToBounds(
      BOX.min_latitude + epsilon,
      CAMPUS_LONGITUDE,
      BOX
    );
    const outside = signedDistanceToBounds(
      BOX.min_latitude - epsilon,
      CAMPUS_LONGITUDE,
      BOX
    );
    expect(inside).toBeLessThan(0);
    expect(outside).toBeGreaterThan(0);
  });
});

describe('boundsToLeaflet', () => {
  it('emits [[south, west], [north, east]] as Leaflet expects', () => {
    expect(boundsToLeaflet(BOX)).toEqual([
      [BOX.min_latitude, BOX.min_longitude],
      [BOX.max_latitude, BOX.max_longitude],
    ]);
  });
});

describe('boundsAreaKm2', () => {
  it('measures a 200 m square as 0.04 km2', () => {
    expect(boundsAreaKm2(BOX)).toBeCloseTo(0.04, 3);
  });
});
