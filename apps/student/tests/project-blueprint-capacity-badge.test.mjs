import test from 'node:test';
import assert from 'node:assert/strict';
import { readFile } from 'node:fs/promises';

test('student PS blueprint modal shows team_count in its allocation badge', async () => {
    const source = await readFile(
        new URL('../src/components/PsArchitecturePlanModal.jsx', import.meta.url),
        'utf8',
    );

    assert.match(source, /currentPs\.team_count/);
    assert.match(source, /Fully Booked \(\$\{currentPs\.team_count\}\/\$\{PS_TEAM_CAPACITY\} teams\)/);
});
