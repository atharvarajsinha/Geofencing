const fs = require('fs');
const path = require('path');

const iconsDir = path.join(__dirname, '../../public/icons');
if (!fs.existsSync(iconsDir)) {
  fs.mkdirSync(iconsDir, { recursive: true });
}

// 1x1 blue PNG pixel base64
const bluePngBase64 = 'iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mNk+M9QDwADhgGAWjR9awAAAABJRU5ErkJggg==';
const buffer = Buffer.from(bluePngBase64, 'base64');

fs.writeFileSync(path.join(iconsDir, 'icon-192x192.png'), buffer);
fs.writeFileSync(path.join(iconsDir, 'icon-512x512.png'), buffer);

console.log('Generated PWA icon placeholders successfully.');
