"""HoReCa One / Setu: Phase 3 counter-side cloud agent (SQLite engine only).

Pushes the records that changed since the last acknowledged version (never the whole data object), pulls commands
from the Super Admin (licence key, vendor message, vendor lock) and applies them through the counter's own save path,
forwards QR staff calls, and rebuilds a counter from the cloud for recovery.

Configuration: <data folder>/setu-cloud2.json  {"url": "https://...", "hotel": "...", "key": "sk_..."}
The cursor (last version the cloud acknowledged) is kept in the SQLite meta table, so it survives restarts and crashes:
a batch that was sent but not acknowledged is sent again, and the cloud ignores what it already has.
"""
import json
import os
import secrets
import threading
import time
import urllib.error
import urllib.request

import setu_security as SEC
import setu_sqlite as SQ

CONF_FILE = 'setu-cloud2.json'
CURSOR = 'cloud3_cursor'
BATCH_ITEMS = int(os.environ.get('SETU_CLOUD_BATCH', '1000'))
BATCH_BYTES = 4 * 1024 * 1024
RECORD_KINDS, MAP_KINDS = ('spec',), ('maptable', 'kvmap', 'att')   # extlist / seq / setting: whole value


class CloudError(Exception):
    pass


def load_conf(data_dir):
    p = os.path.join(data_dir, CONF_FILE)
    try:
        with open(p, encoding='utf-8') as f:
            c = json.load(f)
        return c if c.get('url') and c.get('hotel') and c.get('key') else None
    except (OSError, ValueError):
        return None


def http(url, method, path, body=None, headers=None, timeout=60):
    data = None if body is None else json.dumps(body, ensure_ascii=False).encode()
    req = urllib.request.Request(url.rstrip('/') + path, data=data, method=method,
                                 headers={'Content-Type': 'application/json', 'User-Agent': 'Setu-Counter/3', **(headers or {})})
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            raw = r.read()
            return r.status, json.loads(raw or b'{}'), len(data or b''), len(raw)
    except urllib.error.HTTPError as e:
        raw = e.read()
        try:
            j = json.loads(raw or b'{}')
        except ValueError:
            j = {'error': raw[:200].decode(errors='replace')}
        return e.code, j, len(data or b''), len(raw)


class CloudAgent:
    def __init__(self, store, conf, interval=None):
        self.store, self.sdb, self.conf = store, store.sdb, conf
        self.interval = float(interval or os.environ.get('SETU_CLOUD_INTERVAL', '15'))
        self.wake = threading.Event()
        self.stop = threading.Event()
        self.lock = threading.Lock()   # one sync at a time
        self.state = {'ok': None, 'lastOk': 0, 'lastError': '', 'fails': 0, 'pushed': 0, 'batches': 0, 'bytesOut': 0, 'bytesIn': 0,
                      'snapshots': 0, 'commands': 0, 'conflicts': 0}
        self.thread = None

    # ---------------------------------------------------------------- transport
    def _h(self):
        return {'X-Setu-Hotel': self.conf['hotel'], 'X-Setu-Key': self.conf['key']}

    def call(self, method, path, body=None):
        code, j, out_b, in_b = http(self.conf['url'], method, path, body, self._h())
        self.state['bytesOut'] += out_b
        self.state['bytesIn'] += in_b
        return code, j

    # ---------------------------------------------------------------- cursor
    def cursor(self):
        v = self.sdb.meta(CURSOR)
        return int(v) if v is not None else -1

    def _set_cursor(self, v):
        with self.sdb.tx() as c:
            c.execute('INSERT OR REPLACE INTO meta VALUES (?, ?)', (CURSOR, str(int(v))))

    def pending(self):
        """Saved versions not yet acknowledged by the cloud."""
        return max(0, self.store.version - max(self.cursor(), 0))

    # ---------------------------------------------------------------- building items
    def _meta(self):
        return {'keys': self.sdb.doc_keys(), 'kinds': self.sdb.kinds()}

    def _bill_items(self, c, ids, v_of, snap=None):
        ids = [str(i) for i in ids]
        ords = {}
        for i in range(0, len(ids), 400):
            ch = ids[i:i + 400]
            ords.update(dict(c.execute(f'SELECT id, ord FROM bills WHERE id IN ({",".join("?" * len(ch))})', ch).fetchall()))
        recs = self.sdb.get_records(c, 'bills', ids)
        out = []
        for rid in ids:
            it = {'k': 'bills', 'rid': rid, 'v': v_of(rid)}
            if rid in recs:
                it.update(ord=ords.get(rid, 0), data=recs[rid])
            else:
                it['deleted'] = True
            if snap:
                it['snap'] = snap
            out.append(it)
        return out

    def _key_items(self, c, k, v, snap, rids=None):
        """Items for one working-data key (all of it, or only `rids`). Memory copy taken under the store's lock."""
        kinds, ws = self.sdb.kinds(), self.store._ws or {}
        kind, val = kinds.get(k), ws.get(k)
        out = []
        tag = (lambda it: dict(it, snap=snap)) if snap else (lambda it: it)
        if k == 'secure':
            return out   # credentials travel separately (cred), hashes only
        if k not in ws:
            return [tag({'k': k, 'rid': '', 'v': v, 'deleted': True})] if rids is None or '' in rids else []
        if kind in RECORD_KINDS and isinstance(val, list):
            spec = SQ.SPEC_BY_KEY[k]
            ords = dict(c.execute(f'SELECT id, ord FROM {spec.table}').fetchall())
            pos = {x.get('id'): x for x in val if isinstance(x, dict)}
            for rid in (rids if rids is not None else list(pos)):
                if rid in pos:
                    out.append(tag({'k': k, 'rid': rid, 'v': v, 'ord': ords.get(rid, 0), 'data': json.loads(json.dumps(pos[rid]))}))
                else:
                    out.append(tag({'k': k, 'rid': rid, 'v': v, 'deleted': True}))
        elif kind in MAP_KINDS and isinstance(val, dict):
            for rid in (rids if rids is not None else list(val)):
                if rid in val:
                    out.append(tag({'k': k, 'rid': rid, 'v': v, 'data': json.loads(json.dumps(val[rid]))}))
                else:
                    out.append(tag({'k': k, 'rid': rid, 'v': v, 'deleted': True}))
        else:
            out.append(tag({'k': k, 'rid': '', 'v': v, 'data': json.loads(json.dumps(val))}))
        return out

    def _cred(self, v):
        sec = (self.store._ws or {}).get('secure')
        return {'secure': sec, 'v': v} if isinstance(sec, dict) else None

    # ---------------------------------------------------------------- push
    def _send(self, batches):
        """Send batches in order; each must be acknowledged before the next. Raises on any failure."""
        res = None
        for b in batches:
            code, res = self.call('POST', '/v1/sync/push', b)
            if code != 200 or not res.get('ok'):
                raise CloudError(f'push refused ({code}): {res.get("error") or res}'[:300])
            self.state['batches'] += 1
            self.state['pushed'] += res.get('applied', 0)
            self.state['conflicts'] += res.get('conflicts', 0)
        return res

    def _chunk(self, items, base, mk_id, last_extra):
        """Split items into batches by count and size; `last_extra` goes on the final batch."""
        batches, cur, size = [], [], 0
        for it in items:
            n = len(json.dumps(it, ensure_ascii=False))
            if cur and (len(cur) >= BATCH_ITEMS or size + n > BATCH_BYTES):
                batches.append(cur)
                cur, size = [], 0
            cur.append(it)
            size += n
        batches.append(cur)
        out = []
        for i, items_ in enumerate(batches):
            b = dict(base, batch=mk_id(i), items=items_, final=False)
            if i == len(batches) - 1:
                b.update(last_extra, final=True)
            out.append(b)
        return out

    def push(self):
        """Send everything saved after the cursor. Returns the number of items sent (0 when up to date)."""
        cursor = self.cursor()
        with self.store._enc_lock:
            upto = self.store.version
        if cursor == upto:
            return 0
        con = self.sdb.con()
        with self.sdb.rlock():
            rows = self.sdb.changed_since(con, cursor, upto) if cursor >= 0 else None
        if rows is None or any(k == '*' for k, _, _ in rows) or any(k == 'bills' and rid == '' for k, rid, _ in rows):
            return self.snapshot(cursor, upto)
        groups, vmax = {}, {}
        for k, rid, v in rows:
            groups.setdefault(k, []).append(rid)
            vmax[(k, rid)] = v
        ksnap = f'k{upto}-{secrets.token_hex(3)}'
        snap_keys, items = [], []
        with self.sdb.rlock(), self.store._enc_lock:
            for k, rids in groups.items():
                if k == 'bills':
                    items += self._bill_items(con, rids, lambda r: vmax[('bills', r)])
                elif '' in rids:
                    # The whole key was saved: send all of it; what is no longer there is removed in the cloud
                    snap_keys.append(k)
                    items += self._key_items(con, k, upto, ksnap)
                else:
                    for it in self._key_items(con, k, 0, None, rids):
                        it['v'] = vmax[(k, it['rid'])]
                        items.append(it)
            cred = self._cred(vmax.get(('secure', ''), upto)) if 'secure' in groups else None
            meta = self._meta()
        base = {'from': cursor, 'to': upto, 'meta': meta}
        if cred:
            base['cred'] = cred
        last = {'snap_end': True, 'snap': ksnap, 'snap_keys': snap_keys} if snap_keys else {}
        self._send(self._chunk(items, base, lambda i: f'i{cursor}-{upto}-{i}', last))
        self._set_cursor(upto)
        return len(items)

    def snapshot(self, cursor, upto):
        """Full copy (first sync, or the change log no longer reaches back): every record tagged with one snapshot id;
        the final batch removes in the cloud whatever this copy did not contain."""
        snap = f's{upto}-{secrets.token_hex(4)}'
        self.state['snapshots'] += 1
        con = self.sdb.con()
        with self.sdb.rlock(), self.store._enc_lock:
            items = []
            for k in list((self.store._ws or {}).keys()):
                items += self._key_items(con, k, upto, snap)
            cred = self._cred(upto)
            meta = self._meta()
        base = {'from': cursor, 'to': upto, 'meta': meta, 'snap': snap}
        if cred:
            base['cred'] = cred
        n, sent, part = 0, 0, 0
        batch = []

        def flush(final):
            nonlocal part, batch
            b = dict(base, batch=f'{snap}-{part}', items=batch, final=final)
            if final:
                b['snap_end'] = True
            self._send([b])
            part += 1
            batch = []

        for it in items:
            batch.append(it)
            if len(batch) >= BATCH_ITEMS:
                flush(False)
        # Bills from the tables, in stored order, one read snapshot
        with self.sdb.reader() as rc:
            last = -1
            while True:
                ids = rc.execute('SELECT id, ord FROM bills WHERE ord > ? ORDER BY ord LIMIT ?', (last, BATCH_ITEMS)).fetchall()
                if not ids:
                    break
                last = ids[-1][1]
                for it in self._bill_items(rc, [i for i, _ in ids], lambda r: upto, snap):
                    batch.append(it)
                    n += 1
                    if len(batch) >= BATCH_ITEMS:
                        flush(False)
        flush(True)
        self._set_cursor(upto)
        return len(items) + n + sent

    # ---------------------------------------------------------------- commands (Super Admin -> counter)
    def apply_command(self, cmd):
        """Applied through the counter's own save path (store.write). Idempotent by content: applying it twice changes
        nothing the second time."""
        kind, p = cmd.get('kind'), cmd.get('payload') or {}
        st = self.store
        with st.lock:
            d = st.data()
            if kind == 'licence_key':
                key = str(p.get('key') or '')
                sub = dict(d.get('subscription') or {})
                keys = list(sub.get('cloudKeys') or [])
                if key in keys:
                    return {'ok': True, 'note': 'already received'}
                sub['cloudKeys'] = keys + [key]
                st.write({'subscription': sub})
                return {'ok': True, 'note': 'licence key received'}
            saas = dict(d.get('saas') or {})
            if kind == 'vendor_message':
                t = str(p.get('text') or '')[:500]
                new = {'t': t, 'at': cmd.get('at')} if t else None
                if saas.get('notice') == new:
                    return {'ok': True, 'note': 'already shown'}
                saas['notice'] = new
                st.write({'saas': saas})
                return {'ok': True, 'note': 'message saved' if t else 'message cleared'}
            if kind == 'vendor_lock':
                lv = max(0, min(2, int(p.get('lv') or 0)))
                new = {'lv': lv, 'msg': str(p.get('msg') or '')[:300], 'at': cmd.get('at')} if lv else None
                if saas.get('lock') == new:
                    return {'ok': True, 'note': 'already set'}
                saas['lock'] = new
                st.write({'saas': saas})
                return {'ok': True, 'note': ['lock off', 'warning on', 'app locked'][lv]}
        return {'ok': False, 'note': f'unknown command {kind}'}

    def pull_commands(self):
        code, j = self.call('GET', '/v1/sync/commands')
        if code != 200:
            raise CloudError(f'commands refused ({code}): {j.get("error")}')
        results = []
        for cmd in j.get('commands') or []:
            try:
                r = self.apply_command(cmd)
            except Exception as e:   # one bad command never blocks the others
                r = {'ok': False, 'note': f'failed: {e!r}'[:200]}
            results.append({'seq': cmd['seq'], **r})
        if results:
            code, j = self.call('POST', '/v1/sync/ack', {'results': results})
            if code != 200:
                raise CloudError(f'ack refused ({code})')
            self.state['commands'] += len(results)
        return len(results)

    # ---------------------------------------------------------------- loop
    def sync_once(self):
        with self.lock:
            try:
                pushed = self.push()
                cmds = self.pull_commands()
                if cmds:
                    pushed += self.push()   # the commands' own saves go up right away
                self.state.update(ok=True, lastOk=int(time.time() * 1000), lastError='', fails=0)
                return pushed, cmds
            except Exception as e:
                self.state.update(ok=False, lastError=str(e)[:300], fails=self.state['fails'] + 1)
                raise

    def run(self):
        while not self.stop.is_set():
            try:
                self.sync_once()
                wait = self.interval
            except Exception:
                wait = min(300.0, self.interval * (2 ** min(self.state['fails'], 5)))   # backoff while offline
            self.wake.wait(wait)
            self.wake.clear()

    def start(self):
        self.thread = threading.Thread(target=self.run, daemon=True, name='setu-cloud3')
        self.thread.start()
        return self

    def public(self):
        return {'engine': 'phase3', 'url': self.conf['url'], 'hotel': self.conf['hotel'], 'cursor': self.cursor(),
                'version': self.store.version, 'pending': self.pending(), **{k: v for k, v in self.state.items()}}

    def qr(self, method, path, body=None):
        return self.call(method, path, body)


def recover(url, hotel, key, data_dir):
    """Rebuild a counter's database from the cloud (lost or damaged PC). Writes only into a folder without a database,
    checks the download against the cloud's canonical hash and the rebuilt database against the download, then
    switches the folder to the SQLite engine. The cursor starts at the cloud's acknowledged version, so the next sync
    sends only new work."""
    dest = os.path.join(data_dir, SQ.DB_FILE)
    if os.path.exists(dest):
        raise CloudError('this folder already has a database; recovery writes only into an empty folder')
    code, j, _, _ = http(url, 'GET', '/v1/sync/export', None, {'X-Setu-Hotel': hotel, 'X-Setu-Key': key}, timeout=600)
    if code != 200:
        raise CloudError(f'export refused ({code}): {j.get("error")}')
    doc, want = j['data'], j['contentSha256']
    if SQ.canonical_hash(doc) != want:
        raise CloudError('downloaded data does not match the cloud checksum')
    os.makedirs(data_dir, exist_ok=True)
    tmp = dest + '.recover'
    for x in (tmp, tmp + '-wal', tmp + '-shm'):
        if os.path.exists(x):
            os.remove(x)
    v = max(1, int(j['syncedVersion']))
    db = SQ.SqliteDoc(tmp, create=True)
    with db.tx() as c:
        db.import_document(c, doc, v, int(time.time() * 1000))
        c.execute('INSERT OR REPLACE INTO meta VALUES (?, ?)', (CURSOR, str(v)))
    got = SQ.canonical_hash(db.export_document())
    db.close()
    if got != want:
        os.remove(tmp)
        raise CloudError('rebuilt database differs from the cloud copy; nothing was written')
    os.replace(tmp, dest)
    SQ.write_flag(data_dir, {'engine': 'sqlite', 'db': SQ.DB_FILE, 'recovered_at': int(time.time() * 1000), 'source': 'cloud', 'content_sha256': want})
    with open(os.path.join(data_dir, CONF_FILE), 'w', encoding='utf-8') as f:
        json.dump({'url': url, 'hotel': hotel, 'key': key}, f)
    return {'bills': len(doc.get('bills') or []), 'version': v, 'contentSha256': want}


__all__ = ['CloudAgent', 'load_conf', 'recover', 'CloudError', 'SEC']
