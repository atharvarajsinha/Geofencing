import withPWAInit from "@ducanh2912/next-pwa";

/**
 * The service worker is normally disabled in `next dev`, because a caching SW
 * fights hot reload. Set `ENABLE_PWA_IN_DEV=1` to turn it back on when you need
 * to test installability locally:
 *
 *   ENABLE_PWA_IN_DEV=1 npm run dev
 *
 * Note that install prompts additionally require a secure context, so use
 * http://localhost (which counts as secure) rather than a LAN IP.
 */
const disablePWA =
  process.env.NODE_ENV === "development" && process.env.ENABLE_PWA_IN_DEV !== "1";

const withPWA = withPWAInit({
  dest: "public",
  disable: disablePWA,
  register: true,
  skipWaiting: true,
  // Cache pages as they are navigated to, so a return visit opens instantly and
  // previously seen screens survive a dead spot.
  cacheOnFrontEndNav: true,
  aggressiveFrontEndNavCaching: true,
  reloadOnOnline: true,
  fallbacks: {
    // Served when a navigation misses the cache with no network. Without it an
    // installed app shows the browser's own error page inside the app window.
    document: "/offline",
  },
  workboxOptions: {
    // The API is the backend's job to cache (or not); never serve a stale
    // presence verdict from the service worker.
    navigateFallbackDenylist: [/^\/api\//],
  },
});

/** @type {import('next').NextConfig} */
const nextConfig = {
  reactStrictMode: true,
  swcMinify: true,
};

export default withPWA(nextConfig);
