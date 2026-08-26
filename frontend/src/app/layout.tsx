import React from 'react';
import type { Metadata, Viewport } from 'next';
import { Inter } from 'next/font/google';
import '@/styles/globals.css';
import { Providers } from './providers';
import { Header } from '@/components/layout/Header';
import { MobileNav } from '@/components/layout/MobileNav';

const inter = Inter({ subsets: ['latin'] });

export const metadata: Metadata = {
  // Used as the window/task-switcher title when the app runs standalone, so it
  // is the product name rather than "... PWA".
  title: {
    default: 'GeoPresence',
    template: '%s · GeoPresence',
  },
  applicationName: 'GeoPresence',
  description:
    'Geofencing-based presence and attendance tracking. Your device reports GPS fixes; the backend decides whether you are on site.',
  // Next emits <link rel="manifest">; declaring it here rather than by hand in
  // <head> keeps a single source of truth.
  manifest: '/manifest.json',
  icons: {
    icon: [
      { url: '/icons/favicon-32x32.png', sizes: '32x32', type: 'image/png' },
      { url: '/icons/icon-192x192.png', sizes: '192x192', type: 'image/png' },
      { url: '/icons/icon-512x512.png', sizes: '512x512', type: 'image/png' },
    ],
    // iOS ignores the manifest's icons and needs its own opaque 180x180.
    apple: [{ url: '/icons/apple-touch-icon.png', sizes: '180x180', type: 'image/png' }],
  },
  appleWebApp: {
    capable: true,
    // Matches the sky theme colour so the iOS status bar blends with the header.
    statusBarStyle: 'black-translucent',
    title: 'GeoPresence',
  },
  formatDetection: {
    // Stop iOS turning coordinates and durations into tel: links.
    telephone: false,
  },
};

export const viewport: Viewport = {
  themeColor: '#0284c7',
  width: 'device-width',
  initialScale: 1,
  maximumScale: 1,
  userScalable: false,
  // Draw under the notch/home indicator; `pb-safe` and the header handle insets.
  viewportFit: 'cover',
};

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="en" className="h-full bg-slate-50 antialiased">
      <body
        className={`${inter.className} h-full flex flex-col font-sans text-slate-900 selection:bg-sky-100`}
      >
        <Providers>
          <Header />
          <div className="flex-1">{children}</div>
          <MobileNav />
        </Providers>
      </body>
    </html>
  );
}
