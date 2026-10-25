import test from 'node:test';
import assert from 'node:assert/strict';
import { readFile } from 'node:fs/promises';

test('proposal table numbers visible filtered rows from one', async () => {
  const source = await readFile(new URL('../src/pages/ProposalList.jsx', import.meta.url), 'utf8');

  assert.match(source, /<th[^>]*>S\. No\.<\/th>/);
  assert.match(source, /filtered\.map\(\(p, index\)\s*=>/);
  assert.match(source, /<td[^>]*>\{index \+ 1\}<\/td>/);
  assert.match(source, /colSpan="7"/);
});
