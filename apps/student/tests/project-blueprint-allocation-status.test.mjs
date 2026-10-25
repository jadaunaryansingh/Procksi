import assert from 'node:assert/strict';
import { readFile } from 'node:fs/promises';
import test from 'node:test';

test('allocated project blueprints do not render as available', async () => {
  const source = await readFile(
    new URL('../src/components/PsArchitecturePlanModal.jsx', import.meta.url),
    'utf8',
  );

  assert.match(source, /allocation\s*\|\|\s*currentPs\.is_held_by_current_team\s*\|\|\s*currentPs\.is_allocated/);
  assert.match(source, /Held by Your Team/);
});
