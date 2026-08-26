-- ---------------------------------------------------------------------------
-- Local database bootstrap for a native PostgreSQL install (pgAdmin, no Docker).
--
-- This project needs NO PostGIS extension and no GEOS/GDAL/PROJ libraries:
-- geofences are stored as ordinary float columns (a centre plus radius, or a
-- lat/lon bounding box) and every geographic comparison is done in Python by
-- common/utils/geo.py.
--
-- That removes the step that used to require superuser rights, so the whole
-- setup is now two statements run as the "postgres" superuser.
-- ---------------------------------------------------------------------------

-- === Connected to the "postgres" database, as the postgres superuser =======

-- Application role. CREATEDB is required so that pytest can build the
-- throwaway test_geofencing database.
CREATE ROLE geofencing WITH LOGIN PASSWORD 'geofencing' CREATEDB;

CREATE DATABASE geofencing OWNER geofencing;


-- === Reconnect to the "geofencing" database, still as postgres =============
--
-- PostgreSQL 15+ no longer lets every role create objects in the "public"
-- schema; only the database owner can. Django needs to create tables there, so
-- make the application role the owner (and grant CREATE explicitly, which also
-- covers a database that was created without an OWNER clause).
--
-- pytest's test_geofencing database does not need this: it is created *by* the
-- application role, which therefore already owns its public schema.
ALTER DATABASE geofencing OWNER TO geofencing;
GRANT USAGE, CREATE ON SCHEMA public TO geofencing;

-- Verify the connection works and report the server version.
SELECT version();

-- ---------------------------------------------------------------------------
-- Then, from backend/ with the virtualenv active:
--
--   python manage.py migrate
--   python manage.py seed_demo_data      -- optional demo organization
--   python -m pytest                     -- the suite builds test_geofencing
--
-- If you previously ran this project with PostGIS, see
-- scripts/migrate_from_postgis.sql for converting existing geofence rows, or
-- simply drop and recreate the database (the schema is created from scratch by
-- `migrate`).
-- ---------------------------------------------------------------------------
