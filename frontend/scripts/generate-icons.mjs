/**
 * Generate the PWA icon set.
 *
 *   node scripts/generate-icons.mjs
 *
 * Writes real, correctly sized PNGs. This replaces a previous script that wrote
 * a 1x1 pixel to `icon-192x192.png` and `icon-512x512.png`: Chrome requires a
 * decodable icon of at least 192x192 before it will install a WebAPK, so with a
 * 1x1 placeholder the app could only ever be added as a browser shortcut.
 *
 * Deliberately dependency-free - it encodes PNG by hand using Node's built-in
 * `zlib` - so `npm ci` on a clean machine (or in CI) can regenerate the icons
 * without pulling in sharp/canvas and their native toolchains.
 *
 * Two variants are produced, because they are not interchangeable:
 *
 *   any      - the artwork inside a rounded square, drawn edge to edge. Used
 *              when the platform displays the icon as-is.
 *   maskable - the same artwork inset into the 80% "safe zone" on a full-bleed
 *              background. Android crops maskable icons to its own shape, so a
 *              non-inset icon gets its edges shaved off.
 */
import { deflateSync } from 'node:zlib';
import { mkdirSync, writeFileSync } from 'node:fs';
import { dirname, join } from 'node:path';
import { fileURLToPath } from 'node:url';

const HERE = dirname(fileURLToPath(import.meta.url));
const ICONS_DIR = join(HERE, '..', 'public', 'icons');

// Brand palette, matching `theme_color` in the manifest and the Tailwind sky scale.
const GRADIENT_TOP = [14, 165, 233]; // sky-500
const GRADIENT_BOTTOM = [3, 105, 161]; // sky-700
const GLYPH = [255, 255, 255];

/** Supersampling factor. 4 gives clean edges without a slow render. */
const SS = 4;

// --- PNG encoding -----------------------------------------------------------

const CRC_TABLE = (() => {
  const table = new Int32Array(256);
  for (let n = 0; n < 256; n += 1) {
    let c = n;
    for (let k = 0; k < 8; k += 1) c = c & 1 ? 0xedb88320 ^ (c >>> 1) : c >>> 1;
    table[n] = c;
  }
  return table;
})();

function crc32(buffer) {
  let c = 0xffffffff;
  for (let i = 0; i < buffer.length; i += 1) {
    c = CRC_TABLE[(c ^ buffer[i]) & 0xff] ^ (c >>> 8);
  }
  return (c ^ 0xffffffff) >>> 0;
}

function chunk(type, data) {
  const length = Buffer.alloc(4);
  length.writeUInt32BE(data.length, 0);
  const typeAndData = Buffer.concat([Buffer.from(type, 'ascii'), data]);
  const crc = Buffer.alloc(4);
  crc.writeUInt32BE(crc32(typeAndData), 0);
  return Buffer.concat([length, typeAndData, crc]);
}

/** Encode RGBA pixel data (width*height*4) as a PNG buffer. */
function encodePng(width, height, rgba) {
  const signature = Buffer.from([0x89, 0x50, 0x4e, 0x47, 0x0d, 0x0a, 0x1a, 0x0a]);

  const ihdr = Buffer.alloc(13);
  ihdr.writeUInt32BE(width, 0);
  ihdr.writeUInt32BE(height, 4);
  ihdr[8] = 8; // bit depth
  ihdr[9] = 6; // colour type: RGBA
  ihdr[10] = 0; // deflate
  ihdr[11] = 0; // adaptive filtering
  ihdr[12] = 0; // no interlace

  // Each scanline is prefixed with its filter type; 0 (None) keeps this simple
  // and compresses well for flat artwork.
  const raw = Buffer.alloc(height * (width * 4 + 1));
  for (let y = 0; y < height; y += 1) {
    const rowStart = y * (width * 4 + 1);
    raw[rowStart] = 0;
    rgba.copy(raw, rowStart + 1, y * width * 4, (y + 1) * width * 4);
  }

  return Buffer.concat([
    signature,
    chunk('IHDR', ihdr),
    chunk('IDAT', deflateSync(raw, { level: 9 })),
    chunk('IEND', Buffer.alloc(0)),
  ]);
}

// --- Geometry ---------------------------------------------------------------

function insideRoundedRect(x, y, size, radius) {
  const near = Math.min(x, size - x);
  const nearY = Math.min(y, size - y);
  if (near >= radius || nearY >= radius) return x >= 0 && y >= 0 && x <= size && y <= size;
  const cx = x < radius ? radius : size - radius;
  const cy = y < radius ? radius : size - radius;
  return (x - cx) ** 2 + (y - cy) ** 2 <= radius ** 2;
}

/**
 * A map pin: a disc with a tapering tail, minus a hole in the middle.
 * `cx`/`headY` locate the disc, `r` is its radius, `tipY` the point of the tail.
 */
function insidePin(x, y, cx, headY, r, tipY) {
  const inHead = (x - cx) ** 2 + (y - headY) ** 2 <= r ** 2;

  // Tail: a triangle from the disc's widest useful chord down to the tip.
  const shoulder = r * 0.7;
  let inTail = false;
  if (y >= headY && y <= tipY) {
    const t = (y - headY) / (tipY - headY);
    const halfWidth = shoulder * (1 - t);
    inTail = Math.abs(x - cx) <= halfWidth;
  }

  if (!inHead && !inTail) return false;

  // The hole.
  const inHole = (x - cx) ** 2 + (y - headY) ** 2 <= (r * 0.36) ** 2;
  return !inHole;
}

// --- Rendering --------------------------------------------------------------

/**
 * @param {number} size      output edge length in px
 * @param {boolean} maskable full-bleed background and inset artwork
 */
function renderIcon(size, maskable) {
  const rgba = Buffer.alloc(size * size * 4);
  const superSize = size * SS;

  // Maskable icons must survive an aggressive crop, so keep the artwork inside
  // the 80% safe zone and let the background run to the edges.
  const artScale = maskable ? 0.62 : 0.78;
  const cornerRadius = maskable ? 0 : size * 0.22;

  const cx = size / 2;
  const headY = size * (maskable ? 0.46 : 0.44);
  const r = (size * artScale) / 2.9;
  const tipY = headY + r * 2.35;

  for (let y = 0; y < size; y += 1) {
    for (let x = 0; x < size; x += 1) {
      let bgHits = 0;
      let glyphHits = 0;

      for (let sy = 0; sy < SS; sy += 1) {
        for (let sx = 0; sx < SS; sx += 1) {
          const px = x + (sx + 0.5) / SS;
          const py = y + (sy + 0.5) / SS;

          if (maskable || insideRoundedRect(px, py, size, cornerRadius)) bgHits += 1;
          if (insidePin(px, py, cx, headY, r, tipY)) glyphHits += 1;
        }
      }

      const samples = SS * SS;
      const bgAlpha = bgHits / samples;
      const glyphAlpha = (glyphHits / samples) * bgAlpha; // never paint outside the badge

      // Vertical gradient across the badge.
      const t = y / (size - 1);
      const bg = [0, 1, 2].map((i) =>
        Math.round(GRADIENT_TOP[i] + (GRADIENT_BOTTOM[i] - GRADIENT_TOP[i]) * t)
      );

      // Composite the white glyph over the gradient.
      const out = [0, 1, 2].map((i) => Math.round(bg[i] * (1 - glyphAlpha) + GLYPH[i] * glyphAlpha));

      const offset = (y * size + x) * 4;
      rgba[offset] = out[0];
      rgba[offset + 1] = out[1];
      rgba[offset + 2] = out[2];
      rgba[offset + 3] = Math.round(bgAlpha * 255);
    }
  }

  return encodePng(size, size, rgba);
}

/** Apple touch icons are composited on white; transparency shows as black. */
function renderOpaque(size) {
  const png = renderIcon(size, true);
  return png;
}

// --- Output -----------------------------------------------------------------

const TARGETS = [
  { file: 'icon-192x192.png', size: 192, maskable: false },
  { file: 'icon-512x512.png', size: 512, maskable: false },
  { file: 'icon-maskable-192x192.png', size: 192, maskable: true },
  { file: 'icon-maskable-512x512.png', size: 512, maskable: true },
  { file: 'apple-touch-icon.png', size: 180, maskable: true },
  { file: 'favicon-32x32.png', size: 32, maskable: false },
];

mkdirSync(ICONS_DIR, { recursive: true });

for (const { file, size, maskable } of TARGETS) {
  const png = file === 'apple-touch-icon.png' ? renderOpaque(size) : renderIcon(size, maskable);
  writeFileSync(join(ICONS_DIR, file), png);
  console.log(`  ${file.padEnd(28)} ${size}x${size}  ${png.length} bytes`);
}

console.log('\nPWA icons generated.');
