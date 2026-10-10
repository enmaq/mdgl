#!/usr/bin/env node
'use strict';
// Newline-delimited JSON conformance adapter (PROTOCOL v1). One response line per request line,
// processed in order; the final non-empty line without a newline is answered once.
const { handleLine, invalidUtf8, MAX_REQUEST_LINE } = require('../dist/adapter.js');
// Fatal decode of the complete line bytes: malformed UTF-8 is rejected, never replaced; a BOM is kept (ignoreBOM) so JSON parsing rejects it.
const dec = new TextDecoder('utf-8', { fatal: true, ignoreBOM: true });
let buf = Buffer.alloc(0), skipping = false;
const emit = (s) => process.stdout.write(s + '\n');
function line(b) {
  if (b.length > MAX_REQUEST_LINE) return emit(handleLine('', b.length));
  let text;
  try { text = dec.decode(b); } catch (e) { return emit(invalidUtf8()); }
  emit(handleLine(text, b.length));
}
process.stdin.on('data', (chunk) => {
  buf = Buffer.concat([buf, chunk]);
  for (;;) {
    const nl = buf.indexOf(10);
    if (nl < 0) {
      if (buf.length > MAX_REQUEST_LINE && !skipping) { emit(handleLine('', MAX_REQUEST_LINE + 1)); skipping = true; }
      if (skipping) buf = Buffer.alloc(0);
      return;
    }
    const l = buf.subarray(0, nl);
    buf = buf.subarray(nl + 1);
    if (skipping) { skipping = false; continue; }
    line(l);
  }
});
process.stdin.on('end', () => { if (!skipping && buf.length > 0) line(buf); });
