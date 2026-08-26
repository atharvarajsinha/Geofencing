import { openDB, DBSchema, IDBPDatabase } from 'idb';
import { OfflineQueuedLocation } from '@/types/location';

interface LocationQueueDB extends DBSchema {
  location_queue: {
    key: number;
    value: OfflineQueuedLocation;
    indexes: { 'by-synced': number };
  };
}

const DB_NAME = 'geo_presence_offline_db';
const DB_VERSION = 1;

let dbPromise: Promise<IDBPDatabase<LocationQueueDB>> | null = null;

function getDB() {
  if (typeof window === 'undefined') return null;
  if (!dbPromise) {
    dbPromise = openDB<LocationQueueDB>(DB_NAME, DB_VERSION, {
      upgrade(db) {
        if (!db.objectStoreNames.contains('location_queue')) {
          const store = db.createObjectStore('location_queue', {
            keyPath: 'id',
            autoIncrement: true,
          });
          store.createIndex('by-synced', 'synced' as any);
        }
      },
    });
  }
  return dbPromise;
}

export async function queueOfflineLocation(
  location: Omit<OfflineQueuedLocation, 'id' | 'synced' | 'queued_at'>
): Promise<number | null> {
  const db = await getDB();
  if (!db) return null;

  const entry: OfflineQueuedLocation = {
    ...location,
    synced: false,
    queued_at: new Date().toISOString(),
  };

  return db.add('location_queue', entry);
}

export async function getUnsyncedLocations(): Promise<OfflineQueuedLocation[]> {
  const db = await getDB();
  if (!db) return [];

  const all = await db.getAll('location_queue');
  return all.filter((item) => !item.synced);
}

export async function markLocationSynced(id: number): Promise<void> {
  const db = await getDB();
  if (!db) return;

  await db.delete('location_queue', id);
}

export async function clearSyncedLocations(): Promise<void> {
  const db = await getDB();
  if (!db) return;

  const tx = db.transaction('location_queue', 'readwrite');
  const store = tx.objectStore('location_queue');
  const all = await store.getAll();
  for (const item of all) {
    if (item.synced && item.id) {
      await store.delete(item.id);
    }
  }
  await tx.done;
}
