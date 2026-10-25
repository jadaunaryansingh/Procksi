import test from 'node:test';
import assert from 'node:assert/strict';
import { readFile } from 'node:fs/promises';

test('ProjectAllocation.jsx uses the shared PS capacity module instead of a single-team allocated-titles set', async () => {
    const source = await readFile(new URL('../src/pages/ProjectAllocation.jsx', import.meta.url), 'utf8');

    assert.match(source, /from ['"]\.\.\/lib\/psAllocation['"]/);
    assert.match(source, /computeBulkAllocations\(/);
    assert.match(source, /isPsAvailableForTeam\(/);
    assert.match(source, /buildAllocationsByTitle\(/);
    assert.doesNotMatch(source, /new Set\(\s*\n?\s*teams\s*\n?\s*\.filter\(t => getHasAllocated\(t\)\)/);
    assert.match(source, /getPsAllocations\(/);
    assert.match(source, /allocations=\{getPsAllocations\(selectedPsForAnalysis\.title\)\}/);
});
