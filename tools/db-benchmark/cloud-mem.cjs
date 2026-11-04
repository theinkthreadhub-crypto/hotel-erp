/**
 * Memory a cloud save needs (same V8 engine as Cloudflare Workers / Durable Objects).
 *
 *   node --expose-gc tools/db-benchmark/cloud-mem.cjs <setu-db.json>
 *
 * POST /api/db in cloud/src/worker.js holds the request text, parses it, parses the stored copy
 * (this.data()), and builds the public view (JSON.stringify). This replays those steps on a real
 * database file and reports the JavaScript heap at its peak. The Worker memory limit is 128 MB.
 */
const fs = require('node:fs');
const file = process.argv[2];
const mb = n => +(n / 1048576).toFixed(1);
gc(); const base = process.memoryUsage().heapUsed;
const text = JSON.parse(fs.readFileSync(file, 'utf8')).data;
const body = JSON.stringify({ baseVersion: 1, force: false, data: text });
gc(); const afterText = process.memoryUsage().heapUsed;
const stored = JSON.stringify(text);
const up = JSON.parse(body), old = JSON.parse(stored);
const pub = JSON.stringify(old);
gc(); const peak = process.memoryUsage().heapUsed;
console.log(JSON.stringify({ file, dataMB: mb(Buffer.byteLength(stored)), heapForTextMB: mb(afterText - base), heapAtSaveMB: mb(peak - base), workerLimitMB: 128, fits: peak - base < 128 * 1048576, keep: [up && 1, pub.length > 0] }));
