-- ---------------------------------------------------------------------------
-- One-off conversion of an EXISTING PostGIS-backed database to the
-- PostGIS-free schema.
--
-- You only need this if you have geofence/attendance data you want to keep.
-- For a fresh install, or a disposable dev database, just drop and recreate it
-- and run `python manage.py migrate` - the new migrations build the schema
-- without any extension.
--
-- Run every statement as a role that can ALTER the tables. PostGIS must still
-- be installed while THIS script runs (it reads the old geometry columns); it
-- is no longer needed afterwards.
--
--   psql -U postgres -d geofencing -f scripts/migrate_from_postgis.sql
--
-- WHAT CHANGES
--   geofences_geofence.center_point (geometry) -> center_latitude/center_longitude
--   geofences_geofence.geometry     (polygon)  -> min/max_latitude, min/max_longitude
--   geofence_type 'POLYGON'                    -> 'RECTANGLE'
--   locations_locationupdate.point  (geometry) -> dropped (lat/lon were already
--                                                 the source of truth)
--
-- IMPORTANT: a POLYGON geofence becomes its axis-aligned BOUNDING BOX, so any
-- non-rectangular fence will cover more ground than it used to. Review those
-- rows after converting - the SELECT at the end lists them.
-- ---------------------------------------------------------------------------

BEGIN;

-- --- 1. New geofence columns ------------------------------------------------
ALTER TABLE geofences_geofence
    ADD COLUMN IF NOT EXISTS center_latitude  double precision,
    ADD COLUMN IF NOT EXISTS center_longitude double precision,
    ADD COLUMN IF NOT EXISTS min_latitude     double precision,
    ADD COLUMN IF NOT EXISTS max_latitude     double precision,
    ADD COLUMN IF NOT EXISTS min_longitude    double precision,
    ADD COLUMN IF NOT EXISTS max_longitude    double precision;

-- --- 2. Circles: split the centre point, then derive the envelope ----------
UPDATE geofences_geofence
SET center_latitude  = ST_Y(center_point),
    center_longitude = ST_X(center_point)
WHERE geofence_type = 'CIRCLE'
  AND center_point IS NOT NULL;

-- 111194.9266 m per degree of latitude on the sphere the application uses
-- (6371008.8 m mean radius). Longitude is widened at the poleward edge, which
-- matches common.utils.geo.bbox_for_circle.
UPDATE geofences_geofence
SET min_latitude  = center_latitude - (radius / 111194.9266),
    max_latitude  = center_latitude + (radius / 111194.9266),
    min_longitude = center_longitude - (
        radius / GREATEST(
            111194.9266 * COS(RADIANS(
                GREATEST(
                    ABS(center_latitude - radius / 111194.9266),
                    ABS(center_latitude + radius / 111194.9266)
                )
            )), 0.000001)
    ),
    max_longitude = center_longitude + (
        radius / GREATEST(
            111194.9266 * COS(RADIANS(
                GREATEST(
                    ABS(center_latitude - radius / 111194.9266),
                    ABS(center_latitude + radius / 111194.9266)
                )
            )), 0.000001)
    )
WHERE geofence_type = 'CIRCLE'
  AND center_latitude IS NOT NULL
  AND radius IS NOT NULL;

-- --- 3. Polygons: collapse to the bounding box ------------------------------
UPDATE geofences_geofence
SET min_latitude  = ST_YMin(geometry),
    max_latitude  = ST_YMax(geometry),
    min_longitude = ST_XMin(geometry),
    max_longitude = ST_XMax(geometry)
WHERE geofence_type = 'POLYGON'
  AND geometry IS NOT NULL;

UPDATE geofences_geofence
SET geofence_type = 'RECTANGLE'
WHERE geofence_type = 'POLYGON';

-- --- 4. Refuse to continue if anything is still unset -----------------------
-- Better to fail loudly inside the transaction than to install NOT NULL
-- constraints over silently broken rows.
DO $$
DECLARE
    bad integer;
BEGIN
    SELECT COUNT(*) INTO bad
    FROM geofences_geofence
    WHERE min_latitude IS NULL
       OR max_latitude IS NULL
       OR min_longitude IS NULL
       OR max_longitude IS NULL
       OR max_latitude <= min_latitude
       OR max_longitude <= min_longitude;
    IF bad > 0 THEN
        RAISE EXCEPTION
            'ck: % geofence row(s) have an unusable bounding box; inspect them before rerunning.', bad;
    END IF;
END $$;

ALTER TABLE geofences_geofence
    ALTER COLUMN min_latitude  SET NOT NULL,
    ALTER COLUMN max_latitude  SET NOT NULL,
    ALTER COLUMN min_longitude SET NOT NULL,
    ALTER COLUMN max_longitude SET NOT NULL;

-- --- 5. Drop the geometry columns ------------------------------------------
ALTER TABLE geofences_geofence
    DROP COLUMN IF EXISTS center_point,
    DROP COLUMN IF EXISTS geometry;

ALTER TABLE locations_locationupdate
    DROP COLUMN IF EXISTS point;

-- --- 6. Replace the shape constraint and add the box constraints -----------
ALTER TABLE geofences_geofence
    DROP CONSTRAINT IF EXISTS geofence_shape_matches_type;

ALTER TABLE geofences_geofence
    ADD CONSTRAINT geofence_shape_matches_type CHECK (
        (geofence_type = 'CIRCLE'
            AND center_latitude IS NOT NULL
            AND center_longitude IS NOT NULL
            AND radius IS NOT NULL)
        OR geofence_type = 'RECTANGLE'
    ),
    ADD CONSTRAINT geofence_bbox_latitude_ordered
        CHECK (max_latitude > min_latitude),
    ADD CONSTRAINT geofence_bbox_longitude_ordered
        CHECK (max_longitude > min_longitude);

-- --- 7. Indexes backing the bounding-box prefilter -------------------------
CREATE INDEX IF NOT EXISTS geofence_bbox_lat_idx
    ON geofences_geofence (min_latitude, max_latitude);
CREATE INDEX IF NOT EXISTS geofence_bbox_lon_idx
    ON geofences_geofence (min_longitude, max_longitude);

-- --- 8. Tell Django the new migration state is already in place ------------
-- The migration files were rewritten, so their recorded names are unchanged
-- and `migrate` will consider them applied. The row for the deleted PostGIS
-- migration has to go, or Django reports an unapplied dependency.
DELETE FROM django_migrations
WHERE app = 'common' AND name = '0001_enable_postgis';

COMMIT;

-- --- 9. Review the fences whose shape actually changed ---------------------
-- Every row listed here used to be an arbitrary polygon and is now a rectangle
-- that circumscribes it. Redraw any that now cover ground they should not.
SELECT id, organization_id, name,
       min_latitude, max_latitude, min_longitude, max_longitude
FROM geofences_geofence
WHERE geofence_type = 'RECTANGLE'
ORDER BY organization_id, name;

-- Afterwards, PostGIS can be removed if nothing else uses it:
--   DROP EXTENSION IF EXISTS postgis CASCADE;
