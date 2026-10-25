import test from 'node:test';
import assert from 'node:assert/strict';
import { readFile } from 'node:fs/promises';

test('admin PsArchitecturePlanModal renders a multi-team allocation badge', async () => {
    const source = await readFile(new URL('../src/components/PsArchitecturePlanModal.jsx', import.meta.url), 'utf8');

    assert.match(source, /allocations\s*=\s*\[\]/);
    assert.match(source, /allocations\.length > 0/);
    assert.match(source, /allocationLabels\.join\(', '\)/);
    assert.doesNotMatch(source, /allocation\s*=\s*null/);
});
