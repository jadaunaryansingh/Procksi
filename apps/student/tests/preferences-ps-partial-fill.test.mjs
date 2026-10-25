import test from 'node:test';
import assert from 'node:assert/strict';
import { readFile } from 'node:fs/promises';

test('preferences list shows a partial-fill indicator when one team already holds a PS', async () => {
    const source = await readFile(new URL('../src/pages/PreferencesView.jsx', import.meta.url), 'utf8');

    assert.match(source, /!ps\.is_allocated\s*&&\s*Number\(ps\.team_count\)\s*>\s*0/);
    assert.match(source, /Team Already Selected/);
});
