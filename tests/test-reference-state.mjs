import assert from 'node:assert/strict';
import {readFileSync} from 'node:fs';
const source=readFileSync(new URL('../public/reference-state.js',import.meta.url),'utf8');
const {nextEditReferences}=await import('data:text/javascript;base64,'+Buffer.from(source).toString('base64'));
assert.deepEqual(nextEditReferences('B',['A','pose','room']),['B','pose','room']);
assert.deepEqual(nextEditReferences('C',nextEditReferences('B',['A','pose'])),['C','pose']);
assert.deepEqual(nextEditReferences('B',['A']),['B']);
assert.deepEqual(nextEditReferences('B',['A','B']),['B']);
console.log('Reference advance: 4 checks passed');
