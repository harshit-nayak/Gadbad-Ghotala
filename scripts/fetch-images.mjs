/**
 * Downloads the landing page photographs into public/img/.
 *
 * Run once after cloning:  npm run fetch:images
 *
 * The images are requested from Unsplash at a web-appropriate width and quality
 * (about 150-300 KB each, ~1.5 MB total) so the repository stays small. All are
 * free under the Unsplash licence; credits are in IMAGES.md and the site footer.
 */
import { createWriteStream } from 'node:fs';
import { mkdir, stat } from 'node:fs/promises';
import { dirname, join } from 'node:path';
import { fileURLToPath } from 'node:url';
import { pipeline } from 'node:stream/promises';

const OUT = join(dirname(fileURLToPath(import.meta.url)), '..', 'public', 'img');

/** filename -> Unsplash photo id. Every entry is a different photograph. */
const PHOTOS = {
  'hero-call.jpg': '1758873272000-d3763373f863',
  'problem-executive.jpg': '1630659508738-74252299fa4d',
  'problem-vendor.jpg': '1761914410572-02614b575847',
  'problem-authority.jpg': '1713947506536-2edbac14d3bb',
  'case-executive.jpg': '1758518731457-5ef826b75b3b',
  'case-vendor.jpg': '1544377193-33dcf4d68fb5',
  'case-authority.jpg': '1674471361339-2e1e1dbd3e73',
  'cta.jpg': '1590649681928-4b179f773bd5',
};

const url = (id, w) => `https://images.unsplash.com/photo-${id}?fm=jpg&q=70&w=${w}&fit=crop&auto=format`;

async function download(name, id) {
  const width = name === 'hero-call.jpg' || name === 'cta.jpg' ? 2000 : 1500;
  const res = await fetch(url(id, width));
  if (!res.ok) throw new Error(`${name}: HTTP ${res.status}`);
  await pipeline(res.body, createWriteStream(join(OUT, name)));
  const { size } = await stat(join(OUT, name));
  console.log(`  ${name.padEnd(26)} ${(size / 1024).toFixed(0)} KB`);
}

await mkdir(OUT, { recursive: true });
console.log(`Downloading ${Object.keys(PHOTOS).length} photographs into public/img ...`);
let failed = 0;
for (const [name, id] of Object.entries(PHOTOS)) {
  try {
    await download(name, id);
  } catch (error) {
    failed += 1;
    console.error(`  FAILED ${name}: ${error.message}`);
  }
}
console.log(failed ? `\n${failed} image(s) failed. Re-run, or drop your own files in public/img with these names.` : '\nDone.');
