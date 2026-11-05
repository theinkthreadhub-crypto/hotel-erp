"""HoReCa One / Setu: Phase 3 cloud sync service on PostgreSQL (multi-tenant, row-level security).

    SETU_PG_DSN=postgresql://setu_admin@host/db SETU_CLOUD_ADMIN_KEY=... python setu_cloud.py --port 8790

Counters (SQLite engine) push the records that changed (never whole documents) and pull commands. The counter is the
authority for its hotel's business records; the cloud keeps a replica for the owner's remote view, QR ordering,
backups and recovery. Rules:
  * Tenant isolation: every request is bound to one hotel by its credential; tenant SQL runs as role setu_app with
    setu.hotel set for that transaction only, so PostgreSQL row-level security filters every table.
  * A record is written only when its src_version (the counter's saved version) is newer than the stored one: older
    data never overwrites newer. A repeated batch (same id) is acknowledged without being applied again.
  * A bill whose sale key or number is already used by another bill is not stored; it is recorded as a conflict.
  * Commands to the counter (licence key, vendor message, vendor lock) are applied by the counter through its own save
    path and acknowledged; the cloud never writes counter records.
Nothing here is deployed; development and tests only.
"""
import gzip
import hashlib
import hmac
import http.server
import json
import os
import re
import secrets
import sys
import threading
import time
import urllib.parse
from contextlib import contextmanager

import psycopg
from psycopg.types.json import Jsonb

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import setu_security as SEC   # noqa: E402
import setu_sqlite as SQ      # noqa: E402

DSN = os.environ.get('SETU_PG_DSN', '')
ADMIN_KEY = os.environ.get('SETU_CLOUD_ADMIN_KEY', '')
BACKUP_DIR = os.environ.get('SETU_CLOUD_BACKUPS', os.path.join(os.getcwd(), 'cloud-backups'))
MAX_BODY = 64 * 1024 * 1024
HOTEL_RE = re.compile(r'^[A-Za-z0-9_-]{2,40}$')
REC_KINDS, MAP_KINDS = ('spec',), ('maptable', 'kvmap', 'att')   # every other kind is one whole value (rid '')
OWNER_HOURS = 12
sha = lambda s: hashlib.sha256(s.encode()).hexdigest()   # noqa: E731


class HttpError(Exception):
    def __init__(self, code, msg, extra=None):
        super().__init__(msg)
        self.code, self.msg, self.extra = code, msg, extra or {}


# ---------------------------------------------------------------- database
_local = threading.local()


def conn():
    c = getattr(_local, 'c', None)
    if c is None or c.closed:
        c = psycopg.connect(DSN, autocommit=True)
        _local.c = c
    return c


@contextmanager
def admin_tx():
    c = conn()
    with c.transaction():
        yield c.cursor()


@contextmanager
def tenant_tx(hotel):
    """One transaction as setu_app with the hotel set: row-level security applies to every statement."""
    if not HOTEL_RE.match(str(hotel or '')):
        raise HttpError(400, 'bad hotel id')
    c = conn()
    with c.transaction():
        cur = c.cursor()
        cur.execute('SET LOCAL ROLE setu_app')
        cur.execute("SELECT set_config('setu.hotel', %s, true)", (hotel,))
        yield cur


def rate(key, limit, window_s):
    """True when `key` has used up `limit` tries in `window_s` (and counts this one)."""
    with admin_tx() as cur:
        cur.execute('SELECT n, extract(epoch FROM now() - first_at) FROM login_fails WHERE key = %s FOR UPDATE', (key,))
        r = cur.fetchone()
        if r and r[1] < window_s:
            if r[0] >= limit:
                return True
            cur.execute('UPDATE login_fails SET n = n + 1 WHERE key = %s', (key,))
        else:
            cur.execute('INSERT INTO login_fails VALUES (%s, 1, now()) ON CONFLICT (key) DO UPDATE SET n = 1, first_at = now()', (key,))
    return False


# ---------------------------------------------------------------- authentication
def auth_counter(h):
    hotel, key = h.get('X-Setu-Hotel', ''), h.get('X-Setu-Key', '')
    if not hotel or not key:
        raise HttpError(401, 'counter credentials required')
    with admin_tx() as cur:
        cur.execute("""SELECT c.hotel_id, h.status FROM counters c JOIN hotels h USING (hotel_id)
                       WHERE c.key_hash = %s AND NOT c.revoked""", (sha(key),))
        r = cur.fetchone()
    if not r or not hmac.compare_digest(r[0], hotel):
        raise HttpError(403, 'not this hotel\'s counter')
    return r[0], r[1]


def auth_admin(h):
    if not ADMIN_KEY or not hmac.compare_digest(h.get('X-Admin-Key', ''), ADMIN_KEY):
        raise HttpError(401, 'admin key required')


def auth_owner(h):
    tok = h.get('X-Owner-Token', '')
    if not tok:
        raise HttpError(401, 'owner login required')
    with admin_tx() as cur:
        cur.execute('SELECT hotel_id FROM owner_sessions WHERE token_hash = %s AND expires_at > now()', (sha(tok),))
        r = cur.fetchone()
    if not r:
        raise HttpError(401, 'session expired; please log in again')
    return r[0]


def guest_table(token):
    if not re.fullmatch(r'[0-9a-f]{32}', str(token or '')):
        raise HttpError(410, 'This QR code is not active. Please ask the staff.')
    with admin_tx() as cur:
        cur.execute("""SELECT t.hotel_id, t.tbl FROM qr_tables t JOIN qr_conf q USING (hotel_id) JOIN hotels h USING (hotel_id)
                       WHERE t.token = %s AND t.active AND q.qr_on AND h.status = 'active'""", (token,))
        r = cur.fetchone()
    if not r:
        raise HttpError(410, 'This QR code is not active. Please ask the staff.')
    return r


# ---------------------------------------------------------------- counter -> cloud
def _bill_cols(b):
    tot = b.get('total')
    return {'no': int(b['no']) if isinstance(b.get('no'), (int, float)) and not isinstance(b.get('no'), bool) else None,
            'date': str(b.get('date') or '') or None,
            'total_p': SQ.MONEY(tot) if isinstance(tot, (int, float)) and not isinstance(tot, bool) else None,
            'mode': b.get('mode'), 'phone': SQ.norm_ph(b.get('phone')) or None, 'idem_key': b.get('idemKey') or None,
            'imported': bool(b.get('imported')), 'cancelled': bool(b.get('cancelled'))}


def apply_batch(hotel, body):
    batch = str(body.get('batch') or '')[:200]
    if not batch:
        raise HttpError(400, 'batch id required')
    to_v, from_v = int(body.get('to', 0)), int(body.get('from', 0))
    items = body.get('items') or []
    snap = body.get('snap') or None
    out = {'applied': 0, 'skipped': 0, 'conflicts': 0}
    with tenant_tx(hotel) as cur:
        cur.execute('SELECT result FROM sync_batches WHERE batch_id = %s', (batch,))
        r = cur.fetchone()
        if r:
            return {**r[0], 'repeat': True}
        if isinstance(body.get('meta'), dict):
            cur.execute('UPDATE hotels SET doc_meta = %s, meta_version = %s WHERE hotel_id = %s AND meta_version <= %s',
                        (Jsonb(body['meta']), to_v, hotel, to_v))
        cred = body.get('cred')
        if isinstance(cred, dict) and isinstance(cred.get('secure'), dict):
            cur.execute("""INSERT INTO owner_creds (hotel_id, secure, src_version) VALUES (%s, %s, %s)
                           ON CONFLICT (hotel_id) DO UPDATE SET secure = EXCLUDED.secure, src_version = EXCLUDED.src_version, updated_at = now()
                           WHERE owner_creds.src_version < EXCLUDED.src_version""", (hotel, Jsonb(cred['secure']), int(cred.get('v', to_v))))
        for it in items:
            k, rid, v = str(it.get('k')), str(it.get('rid', '')), int(it.get('v', to_v))
            deleted, data, ordn = bool(it.get('deleted')), it.get('data'), int(it.get('ord') or 0)
            isnap = it.get('snap') or snap
            if k == 'bills':
                if not deleted and not isinstance(data, dict):
                    raise HttpError(400, 'bill data must be an object')
                cols = _bill_cols(data) if not deleted else {}
                if deleted:
                    cur.execute("""UPDATE bills SET deleted = true, src_version = %s, snap = %s, updated_at = now()
                                   WHERE hotel_id = %s AND id = %s AND src_version < %s""", (v, isnap, hotel, rid, v))
                else:
                    cur.execute("""INSERT INTO bills (hotel_id, id, ord, no, date, total_p, mode, phone, idem_key, imported, cancelled, deleted, src_version, snap, data)
                                   VALUES (%(h)s, %(id)s, %(ord)s, %(no)s, %(date)s, %(total_p)s, %(mode)s, %(phone)s, %(idem_key)s, %(imported)s, %(cancelled)s, false, %(v)s, %(snap)s, %(data)s)
                                   ON CONFLICT (hotel_id, id) DO UPDATE SET ord = EXCLUDED.ord, no = EXCLUDED.no, date = EXCLUDED.date, total_p = EXCLUDED.total_p,
                                     mode = EXCLUDED.mode, phone = EXCLUDED.phone, idem_key = EXCLUDED.idem_key, imported = EXCLUDED.imported,
                                     cancelled = EXCLUDED.cancelled, deleted = false, src_version = EXCLUDED.src_version, snap = EXCLUDED.snap,
                                     data = EXCLUDED.data, updated_at = now()
                                   WHERE bills.src_version < EXCLUDED.src_version""",
                                dict(cols, h=hotel, id=rid, ord=ordn, v=v, snap=isnap, data=Jsonb(data)))
                n = cur.rowcount
                if not n and isnap:
                    cur.execute('UPDATE bills SET snap = %s WHERE hotel_id = %s AND id = %s', (isnap, hotel, rid))
                if n and not deleted and (cols['idem_key'] or (cols['no'] is not None and not cols['imported'])):
                    # Another live bill with the same sale key or number and different content: stored, never
                    # silently merged or dropped, and reported for review
                    cur.execute("""SELECT id, data FROM bills WHERE hotel_id = %s AND NOT deleted AND id <> %s
                                   AND (idem_key = %s OR (no = %s AND NOT imported AND %s)) LIMIT 5""",
                                (hotel, rid, cols['idem_key'], cols['no'], not cols['imported']))
                    for oid, od in cur.fetchall():
                        if SQ.canonical_hash({'b': od}) != SQ.canonical_hash({'b': data}):
                            reason = 'same sale key' if cols['idem_key'] and od.get('idemKey') == cols['idem_key'] else 'same bill number'
                            cur.execute('INSERT INTO conflicts (hotel_id, k, rid, reason, stored, incoming) VALUES (%s, %s, %s, %s, %s, %s)',
                                        (hotel, 'bills', rid, f'{reason} as bill {oid}', Jsonb(od), Jsonb(data)))
                            out['conflicts'] += 1
                out['applied' if n else 'skipped'] += 1
            else:
                cur.execute("""INSERT INTO records (hotel_id, k, rid, ord, deleted, src_version, snap, data) VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
                               ON CONFLICT (hotel_id, k, rid) DO UPDATE SET ord = EXCLUDED.ord, deleted = EXCLUDED.deleted, src_version = EXCLUDED.src_version,
                                 snap = EXCLUDED.snap, data = EXCLUDED.data, updated_at = now()
                               WHERE records.src_version < EXCLUDED.src_version""",
                            (hotel, k, rid, ordn, deleted, v, isnap, None if deleted else Jsonb(data)))
                n = cur.rowcount
                if not n and isnap:
                    cur.execute('UPDATE records SET snap = %s WHERE hotel_id = %s AND k = %s AND rid = %s', (isnap, hotel, k, rid))
                out['applied' if n else 'skipped'] += 1
        if body.get('snap_end') and snap:
            # A full copy (or a copy of some keys) just finished: what the counter no longer has, and nobody changed
            # after the copy, is removed here
            keys = body.get('snap_keys')
            kf, ka = ('AND k = ANY(%s)', [list(keys)]) if keys else ('', [])
            if not keys or 'bills' in keys:
                cur.execute("""UPDATE bills SET deleted = true, src_version = %s WHERE hotel_id = %s AND NOT deleted AND snap IS DISTINCT FROM %s AND src_version <= %s""",
                            (to_v, hotel, snap, to_v))
                out['snapRemovedBills'] = cur.rowcount
            cur.execute(f"""UPDATE records SET deleted = true, data = NULL, src_version = %s WHERE hotel_id = %s AND NOT deleted AND snap IS DISTINCT FROM %s AND src_version <= %s {kf}""",
                        [to_v, hotel, snap, to_v] + ka)
            out['snapRemovedRecords'] = cur.rowcount
        if body.get('final', True):
            cur.execute('UPDATE hotels SET synced_version = GREATEST(synced_version, %s), last_seen = now() WHERE hotel_id = %s', (to_v, hotel))
        res = {'ok': True, 'to': to_v, 'from': from_v, **out}
        cur.execute('INSERT INTO sync_batches (hotel_id, batch_id, from_v, to_v, result) VALUES (%s, %s, %s, %s, %s)', (hotel, batch, from_v, to_v, Jsonb(res)))
    return res


# ---------------------------------------------------------------- a hotel's data rebuilt (backup, recovery, owner)
def write_doc(hotel, f, with_secure=True):
    """The hotel's data object in the counter's key order, written in parts (bills via a server-side cursor)."""
    with tenant_tx(hotel) as cur:
        cur.execute('SELECT doc_meta, synced_version FROM hotels WHERE hotel_id = %s', (hotel,))
        r = cur.fetchone()
        if not r:
            raise HttpError(404, 'hotel not found')
        meta, synced = r[0] or {}, r[1]
        keys, kinds = meta.get('keys') or [], meta.get('kinds') or {}
        cur.execute('SELECT k, rid, data FROM records WHERE hotel_id = %s AND NOT deleted ORDER BY k, ord, rid', (hotel,))
        rec = {}
        for k, rid, data in cur:
            rec.setdefault(k, []).append((rid, data))
        cur.execute('SELECT secure FROM owner_creds WHERE hotel_id = %s', (hotel,))
        sr = cur.fetchone()
        f.write('{')
        first = True
        for k in keys:   # exactly the counter's keys, in its order (same as SqliteDoc._export_document)
            kind = kinds.get(k)
            if k == 'secure':
                if not (with_secure and sr):
                    continue
                val = sr[0]
            elif k == 'bills':
                f.write(('' if first else ', ') + json.dumps(k) + ': [')
                first = False
                bc = cur.connection.cursor(name='bills_export')
                bc.itersize = 2000
                bc.execute('SELECT data FROM bills WHERE hotel_id = %s AND NOT deleted ORDER BY ord, id', (hotel,))
                n = 0
                for (d,) in bc:
                    f.write((', ' if n else '') + json.dumps(d, ensure_ascii=False))
                    n += 1
                bc.close()
                f.write(']')
                continue
            elif kind in REC_KINDS:
                val = [d for _, d in rec.get(k, [])]
            elif kind in MAP_KINDS:
                val = {rid: d for rid, d in rec.get(k, [])}
            else:
                val = next((d for rid, d in rec.get(k, []) if rid == ''), None)
            f.write(('' if first else ', ') + json.dumps(k) + ': ' + json.dumps(val, ensure_ascii=False))
            first = False
        f.write('}')
    return synced


class _Buf:
    def __init__(self):
        self.parts = []

    def write(self, t):
        self.parts.append(t)

    def text(self):
        return ''.join(self.parts)


def backup(hotel):
    """Cloud backup of one hotel: gzip JSON + sha256 of the file + canonical hash of the content, then verified by
    reading it back."""
    os.makedirs(os.path.join(BACKUP_DIR, hotel), exist_ok=True)
    bid = time.strftime('%Y%m%d-%H%M%S') + '-' + secrets.token_hex(3)
    path = os.path.join(BACKUP_DIR, hotel, f'{bid}.json.gz')
    with gzip.open(path + '.part', 'wt', encoding='utf-8') as g:
        synced = write_doc(hotel, g)
    os.replace(path + '.part', path)
    with gzip.open(path, 'rt', encoding='utf-8') as g:
        doc = json.load(g)
    content = SQ.canonical_hash(doc)
    fsha = hashlib.sha256(open(path, 'rb').read()).hexdigest()
    live = _Buf()
    write_doc(hotel, live)
    verified = SQ.canonical_hash(json.loads(live.text())) == content
    with tenant_tx(hotel) as cur:
        cur.execute("""INSERT INTO backups (hotel_id, id, file, bytes, sha256, content_sha256, bills, records, synced_version, verified)
                       VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)""",
                    (hotel, bid, os.path.basename(path), os.path.getsize(path), fsha, content, len(doc.get('bills') or []), sum(1 for _ in doc), synced, verified))
    return {'id': bid, 'file': path, 'bytes': os.path.getsize(path), 'sha256': fsha, 'contentSha256': content, 'bills': len(doc.get('bills') or []),
            'syncedVersion': synced, 'verified': verified}


def verify_backup(hotel, bid):
    with tenant_tx(hotel) as cur:
        cur.execute('SELECT file, sha256, content_sha256 FROM backups WHERE hotel_id = %s AND id = %s', (hotel, bid))
        r = cur.fetchone()
    if not r:
        raise HttpError(404, 'backup not found')
    path = os.path.join(BACKUP_DIR, hotel, r[0])
    try:
        if hashlib.sha256(open(path, 'rb').read()).hexdigest() != r[1]:
            return {'ok': False, 'error': 'file checksum differs (damaged or changed)'}
        with gzip.open(path, 'rt', encoding='utf-8') as g:
            ok = SQ.canonical_hash(json.load(g)) == r[2]
        return {'ok': ok, **({} if ok else {'error': 'content checksum differs'})}
    except Exception as e:
        return {'ok': False, 'error': f'unreadable: {e!r}'[:200]}


# ---------------------------------------------------------------- QR (same shapes as the Worker)
def _menu_view(cur, hotel):
    cur.execute("SELECT k, rid, data FROM records WHERE hotel_id = %s AND NOT deleted AND k IN ('menu', 'settings', 'stock', 'stockAlias') ORDER BY k, ord", (hotel,))
    d = {'menu': [], 'stock': [], 'stockAlias': {}, 'settings': {}}
    for k, rid, data in cur:
        if k == 'settings':
            d['settings'] = data or {}
        elif k == 'stockAlias':
            d['stockAlias'][rid] = data
        else:
            d[k].append(data)
    return d


def _s(v, n):
    return str(v or '')[:n]


def guest(method, path, q, body, ip):
    token = body.get('t') if method == 'POST' else q.get('t')
    hotel, tbl = guest_table(token)
    with tenant_tx(hotel) as cur:
        d = _menu_view(cur, hotel)
        st = d['settings']
        if method == 'GET' and path == '/v1/guest/menu':
            stock = {x.get('id'): x for x in d['stock'] if isinstance(x, dict)}
            alias = d['stockAlias']

            def qty(sid):
                x = sid
                for _ in range(6):
                    if x in alias:
                        x = alias[x]
                it = stock.get(x)
                return float(it.get('qty') or 0) if it else 1

            out = lambda m: st.get('qrHideOut') and any(r and float(r.get('qty') or 0) > 0 and qty(r.get('sid')) <= 0 for r in m.get('recipe') or [])   # noqa: E731
            items = [{'id': m['id'], 'name': _s(m.get('name'), 80), 'cat': _s(m.get('cat'), 40) or 'Menu', 'price': float(m.get('price') or 0), 'veg': m.get('veg'),
                      'desc': _s(m.get('desc'), 160) or None, 'out': True if m.get('out') else None}
                     for m in d['menu'] if isinstance(m, dict) and m.get('id') and m.get('name') and not m.get('qrOff') and m.get('active') is not False and not out(m)]
            return 200, {'hotel': _s(st.get('name'), 80), 'table': tbl, 'items': items, 'gst': float(st.get('gst') or 0), 'incl': bool(st.get('gstInclusive'))}
        if method == 'GET' and path == '/v1/guest/status':
            cur.execute("SELECT id, at, status, items, reason FROM guest_orders WHERE hotel_id = %s AND tbl = %s AND at > %s ORDER BY at", (hotel, tbl, int(time.time() * 1000) - 12 * 3600e3))
            orders = [{'id': r[0], 'at': r[1], 'status': r[2], 'items': r[3], 'reason': r[4] or ''} for r in cur.fetchall()]
            cur.execute('SELECT id, kind, at, done FROM guest_calls WHERE hotel_id = %s AND tbl = %s AND at > %s ORDER BY at', (hotel, tbl, int(time.time() * 1000) - 3 * 3600e3))
            return 200, {'table': tbl, 'orders': orders, 'calls': [{'id': r[0], 'kind': r[1], 'at': r[2], 'done': r[3]} for r in cur.fetchall()]}
    if rate('gip:' + ip, 40, 3600):
        raise HttpError(429, 'Too many requests. Please ask the staff.')
    with tenant_tx(hotel) as cur:
        if method == 'POST' and path == '/v1/guest/order':
            oid = str(body.get('id') or '')
            if not re.fullmatch(r'[A-Za-z0-9_-]{8,40}', oid):
                raise HttpError(400, 'bad order id')
            cur.execute('SELECT id, status FROM guest_orders WHERE hotel_id = %s AND id = %s', (hotel, 'g' + oid))
            same = cur.fetchone()
            if same:
                return 200, {'id': same[0], 'status': same[1], 'again': True}
            cur.execute("SELECT count(*) FROM guest_orders WHERE hotel_id = %s AND tbl = %s AND status = 'pending'", (hotel, tbl))
            if cur.fetchone()[0] >= 5:
                raise HttpError(429, 'Your earlier orders are still waiting for the staff. Please wait a moment.')
            menu = {m['id']: m for m in _menu_view(cur, hotel)['menu'] if isinstance(m, dict) and m.get('id') and not m.get('qrOff') and not m.get('out') and m.get('active') is not False}
            lines = []
            for x in (body.get('items') or [])[:40]:
                m = menu.get(str((x or {}).get('mid') or ''))
                qn = round(float((x or {}).get('qty') or 0))
                if not m or qn < 1 or qn > 50:
                    continue
                ex = next((ln for ln in lines if ln['mid'] == m['id']), None)
                if ex:
                    ex['qty'] = min(50, ex['qty'] + qn)
                else:
                    lines.append({'mid': m['id'], 'name': _s(m.get('name'), 80), 'price': float(m.get('price') or 0), 'qty': qn})   # price from the menu, never the guest
            if not lines:
                raise HttpError(400, 'Please add an item')
            cur.execute("INSERT INTO guest_orders (hotel_id, id, tbl, items, note, name, status, at) VALUES (%s, %s, %s, %s, %s, %s, 'pending', %s)",
                        (hotel, 'g' + oid, tbl, Jsonb(lines), _s(body.get('note'), 200), _s(body.get('name'), 60), int(time.time() * 1000)))
            return 200, {'id': 'g' + oid, 'status': 'pending'}
        if method == 'POST' and path == '/v1/guest/call':
            kind = body.get('kind') if body.get('kind') in ('waiter', 'bill', 'water') else 'waiter'
            cur.execute('SELECT id FROM guest_calls WHERE hotel_id = %s AND tbl = %s AND kind = %s AND NOT done', (hotel, tbl, kind))
            r = cur.fetchone()
            if r:
                return 200, {'id': r[0], 'again': True}
            cid = 'c' + secrets.token_hex(8)
            cur.execute('INSERT INTO guest_calls (hotel_id, id, tbl, kind, at) VALUES (%s, %s, %s, %s, %s)', (hotel, cid, tbl, kind, int(time.time() * 1000)))
            return 200, {'id': cid}
    raise HttpError(404, 'not found')


def qr_staff(hotel, method, path, body, base):
    with tenant_tx(hotel) as cur:
        cur.execute('INSERT INTO qr_conf (hotel_id) VALUES (%s) ON CONFLICT DO NOTHING', (hotel,))
        cur.execute('SELECT qr_on, auto FROM qr_conf WHERE hotel_id = %s', (hotel,))
        on, auto = cur.fetchone()
        tables = lambda: {t: {'token': tok, 'on': a} for t, tok, a in cur.execute('SELECT tbl, token, active FROM qr_tables WHERE hotel_id = %s ORDER BY tbl', (hotel,)).fetchall()}   # noqa: E731
        if method == 'GET' and path == '/v1/qr/state':
            cur.execute("""SELECT id, tbl, items, note, name, status, at, by, decided, reason, kot FROM guest_orders
                           WHERE hotel_id = %s AND (status IN ('pending', 'accepted') OR at > %s) ORDER BY at""", (hotel, int(time.time() * 1000) - 6 * 3600e3))
            cols = ['id', 'tbl', 'items', 'note', 'name', 'status', 'at', 'by', 'decided', 'reason', 'kot']
            orders = [dict(zip(cols, r)) for r in cur.fetchall()]
            cur.execute('SELECT id, tbl, kind, at, done, by FROM guest_calls WHERE hotel_id = %s AND NOT done ORDER BY at', (hotel,))
            calls = [dict(zip(['id', 'tbl', 'kind', 'at', 'done', 'by'], r)) for r in cur.fetchall()]
            return 200, {'on': on, 'auto': auto, 'base': base + '/q/' + hotel + '/', 'tables': tables(), 'orders': orders, 'calls': calls}
        if method != 'POST':
            raise HttpError(404, 'not found')
        if path == '/v1/qr/settings':
            on = bool(body['on']) if 'on' in body else on
            auto = bool(body['auto']) if 'auto' in body else auto
            cur.execute('UPDATE qr_conf SET qr_on = %s, auto = %s WHERE hotel_id = %s', (on, auto, hotel))
            return 200, {'on': on, 'auto': auto}
        if path == '/v1/qr/table':
            t = _s(body.get('table'), 30)
            if not t:
                raise HttpError(400, 'table required')
            act = body.get('action')
            cur.execute('SELECT active FROM qr_tables WHERE hotel_id = %s AND tbl = %s', (hotel, t))
            ex = cur.fetchone()
            if act == 'new' or (not ex and act != 'remove'):
                cur.execute("""INSERT INTO qr_tables (hotel_id, tbl, token) VALUES (%s, %s, %s)
                               ON CONFLICT (hotel_id, tbl) DO UPDATE SET token = EXCLUDED.token, active = true, at = now()""", (hotel, t, secrets.token_hex(16)))
                cur.execute('UPDATE qr_conf SET qr_on = true WHERE hotel_id = %s', (hotel,))
                on = True
            elif act in ('off', 'on') and ex:
                cur.execute('UPDATE qr_tables SET active = %s WHERE hotel_id = %s AND tbl = %s', (act == 'on', hotel, t))
            elif act == 'remove':
                cur.execute('DELETE FROM qr_tables WHERE hotel_id = %s AND tbl = %s', (hotel, t))
            return 200, {'tables': tables(), 'on': on}
        if path == '/v1/qr/decide':
            cur.execute('SELECT id, tbl, items, status, by FROM guest_orders WHERE hotel_id = %s AND id = %s FOR UPDATE', (hotel, str(body.get('id') or '')))
            o = cur.fetchone()
            if not o:
                raise HttpError(404, 'order not found')
            if o[3] != 'pending':   # first decision wins (row lock)
                raise HttpError(409, 'already ' + o[3], {'status': o[3], 'by': o[4]})
            accept = body.get('action') == 'accept'
            cur.execute('UPDATE guest_orders SET status = %s, by = %s, decided = %s, reason = %s WHERE hotel_id = %s AND id = %s',
                        ('accepted' if accept else 'rejected', _s(body.get('by'), 60), int(time.time() * 1000), '' if accept else _s(body.get('reason'), 120), hotel, o[0]))
            return 200, {'id': o[0], 'status': 'accepted' if accept else 'rejected', 'order': {'id': o[0], 'tbl': o[1], 'items': o[2]}}
        if path == '/v1/qr/applied':
            cur.execute("UPDATE guest_orders SET status = 'done', kot = %s WHERE hotel_id = %s AND id = %s AND status = 'accepted'", (_s(body.get('kot'), 20), hotel, str(body.get('id') or '')))
            return 200, {'ok': True}
        if path == '/v1/qr/call':
            cur.execute('UPDATE guest_calls SET done = true, by = %s WHERE hotel_id = %s AND id = %s', (_s(body.get('by'), 60), hotel, str(body.get('id') or '')))
            return 200, {'ok': True}
    raise HttpError(404, 'not found')


# ---------------------------------------------------------------- HTTP
class Handler(http.server.BaseHTTPRequestHandler):
    server_version = 'SetuCloud/3'
    protocol_version = 'HTTP/1.1'

    def log_message(self, *a):
        pass

    def _send(self, code, obj, raw=None, ctype='application/json; charset=utf-8'):
        body = raw if raw is not None else json.dumps(obj, ensure_ascii=False, default=str).encode()
        self.send_response(code)
        self.send_header('Content-Type', ctype)
        self.send_header('Content-Length', str(len(body)))
        self.send_header('Cache-Control', 'no-store')
        self.end_headers()
        self.wfile.write(body)

    def _body(self):
        n = int(self.headers.get('Content-Length') or 0)
        if n > MAX_BODY:
            raise HttpError(413, 'request too large')
        if not n:
            return {}
        try:
            b = json.loads(self.rfile.read(n))
        except Exception:
            raise HttpError(400, 'bad JSON')
        if not isinstance(b, dict):
            raise HttpError(400, 'bad request')
        return b

    def do_GET(self):
        self._route('GET')

    def do_POST(self):
        self._route('POST')

    def _route(self, method):
        u = urllib.parse.urlparse(self.path)
        path, q = u.path, {k: v[0] for k, v in urllib.parse.parse_qs(u.query).items()}
        try:
            body = self._body() if method == 'POST' else {}
            code, obj = self.route(method, path, q, body)
            if isinstance(obj, bytes):
                return self._send(code, None, raw=obj)
            return self._send(code, obj)
        except HttpError as e:
            return self._send(e.code, {'error': e.msg, **e.extra})
        except psycopg.Error as e:
            return self._send(500, {'error': 'database error', 'detail': str(e).splitlines()[0][:200]})

    def route(self, method, path, q, body):
        h = self.headers
        ip = self.client_address[0]
        if path == '/v1/ping':
            return 200, {'ok': True, 'service': 'setu-cloud-3'}
        # ---- counter
        if path == '/v1/sync/push' and method == 'POST':
            hotel, status = auth_counter(h)
            return 200, apply_batch(hotel, body)
        if path == '/v1/sync/commands' and method == 'GET':
            hotel, _ = auth_counter(h)
            with tenant_tx(hotel) as cur:
                cur.execute('SELECT seq, kind, payload, created_at FROM commands WHERE hotel_id = %s AND acked_at IS NULL ORDER BY seq LIMIT 100', (hotel,))
                return 200, {'commands': [{'seq': r[0], 'kind': r[1], 'payload': r[2], 'at': int(r[3].timestamp() * 1000)} for r in cur.fetchall()]}
        if path == '/v1/sync/ack' and method == 'POST':
            hotel, _ = auth_counter(h)
            n = 0
            with tenant_tx(hotel) as cur:
                for r in body.get('results') or []:
                    cur.execute('UPDATE commands SET acked_at = now(), result = %s WHERE hotel_id = %s AND seq = %s AND acked_at IS NULL',
                                (Jsonb({'ok': bool(r.get('ok')), 'note': _s(r.get('note'), 300)}), hotel, int(r.get('seq'))))
                    n += cur.rowcount
            return 200, {'acked': n}
        if path == '/v1/sync/state' and method == 'GET':
            hotel, status = auth_counter(h)
            with tenant_tx(hotel) as cur:
                cur.execute('SELECT synced_version, status FROM hotels WHERE hotel_id = %s', (hotel,))
                r = cur.fetchone()
            return 200, {'hotel': hotel, 'syncedVersion': r[0], 'status': r[1]}
        if path == '/v1/sync/export' and method == 'GET':
            # Recovery: the counter's own data rebuilt from the cloud (with its credential hashes)
            hotel, _ = auth_counter(h)
            buf = _Buf()
            synced = write_doc(hotel, buf)
            text = buf.text()
            return 200, json.dumps({'hotel': hotel, 'syncedVersion': synced, 'contentSha256': SQ.canonical_hash(json.loads(text)), 'data': '__DATA__'}).replace('"__DATA__"', text).encode()
        if path.startswith('/v1/qr/'):
            hotel, _ = auth_counter(h)
            return qr_staff(hotel, method, path, body, 'https://' + (h.get('Host') or 'cloud'))
        # ---- guests (QR)
        if path.startswith('/v1/guest/'):
            return guest(method, path, q, body, ip)
        # ---- owner (remote, read only)
        if path == '/v1/owner/login' and method == 'POST':
            hotel, pw = str(body.get('hotel') or ''), str(body.get('password') or '')
            if not HOTEL_RE.match(hotel):
                raise HttpError(400, 'bad hotel id')
            if rate('owner:' + ip + ':' + hotel, 5, 900):
                raise HttpError(429, 'Too many wrong tries. Please wait 15 minutes.')
            with tenant_tx(hotel) as cur:
                cur.execute("SELECT o.secure, h.status FROM owner_creds o JOIN hotels h USING (hotel_id) WHERE o.hotel_id = %s", (hotel,))
                r = cur.fetchone()
                owner_hash = ((r or [None])[0] or {}).get('owner')
                if not r or not owner_hash or not SEC.verify_secret(pw, owner_hash):
                    raise HttpError(401, 'Hotel ID or password is not correct')
                if r[1] != 'active':
                    raise HttpError(402, 'This hotel is suspended')
                tok = secrets.token_hex(24)
                cur.execute("INSERT INTO owner_sessions (hotel_id, token_hash, expires_at) VALUES (%s, %s, now() + make_interval(hours => %s))", (hotel, sha(tok), OWNER_HOURS))
            with admin_tx() as c2:
                c2.execute('DELETE FROM login_fails WHERE key = %s', ('owner:' + ip + ':' + hotel,))
            return 200, {'token': tok, 'hotel': hotel, 'expiresInHours': OWNER_HOURS}
        if path.startswith('/v1/owner/'):
            hotel = auth_owner(h)
            with tenant_tx(hotel) as cur:
                if path == '/v1/owner/logout':
                    cur.execute('DELETE FROM owner_sessions WHERE token_hash = %s', (sha(h.get('X-Owner-Token', '')),))
                    return 200, {'ok': True}
                if path == '/v1/owner/summary':
                    frm, to = q.get('from') or '0000-00-00', q.get('to') or '9999-99-99'
                    cur.execute("""SELECT date, count(*), COALESCE(sum(total_p), 0) FROM bills WHERE hotel_id = %s AND NOT deleted AND NOT cancelled
                                   AND date BETWEEN %s AND %s GROUP BY date ORDER BY date""", (hotel, frm, to))
                    days = [{'date': d, 'bills': n, 'sales_p': int(t)} for d, n, t in cur.fetchall()]
                    cur.execute('SELECT synced_version, last_seen FROM hotels WHERE hotel_id = %s', (hotel,))
                    sv, seen = cur.fetchone()
                    return 200, {'hotel': hotel, 'days': days, 'bills': sum(x['bills'] for x in days), 'sales_p': sum(x['sales_p'] for x in days),
                                 'syncedVersion': sv, 'lastSeen': seen.isoformat() if seen else None}
                if path == '/v1/owner/bills':
                    lim = max(1, min(int(q.get('limit', 50) or 50), 500))
                    cur.execute("""SELECT id, no, date, total_p, mode, cancelled FROM bills WHERE hotel_id = %s AND NOT deleted AND date = %s
                                   ORDER BY ord DESC LIMIT %s OFFSET %s""", (hotel, q.get('date') or '', lim, max(0, int(q.get('offset', 0) or 0))))
                    return 200, {'rows': [dict(zip(['id', 'no', 'date', 'total_p', 'mode', 'cancelled'], r)) for r in cur.fetchall()]}
                if path == '/v1/owner/bill':
                    cur.execute('SELECT data FROM bills WHERE hotel_id = %s AND id = %s AND NOT deleted', (hotel, q.get('id') or ''))
                    r = cur.fetchone()
                    if not r:
                        raise HttpError(404, 'bill not found')
                    return 200, {'bill': r[0]}
            raise HttpError(404, 'not found')
        # ---- Super Admin
        if path.startswith('/v1/admin/'):
            auth_admin(h)
            if path == '/v1/admin/hotels' and method == 'POST':
                hid = str(body.get('hotel') or '')
                if not HOTEL_RE.match(hid):
                    raise HttpError(400, 'hotel id: 2-40 letters, digits, - or _')
                key = 'sk_' + secrets.token_hex(24)
                with admin_tx() as cur:   # a new tenant is created by the admin role only
                    cur.execute('INSERT INTO hotels (hotel_id, name) VALUES (%s, %s) ON CONFLICT (hotel_id) DO NOTHING', (hid, _s(body.get('name'), 120)))
                    cur.execute('INSERT INTO qr_conf (hotel_id) VALUES (%s) ON CONFLICT DO NOTHING', (hid,))
                    cur.execute('UPDATE counters SET revoked = true WHERE hotel_id = %s', (hid,))
                    cur.execute('INSERT INTO counters (hotel_id, counter_id, key_hash) VALUES (%s, %s, %s)', (hid, 'c' + secrets.token_hex(4), sha(key)))
                return 200, {'hotel': hid, 'syncKey': key, 'note': 'shown once; earlier keys of this hotel are revoked'}
            if path == '/v1/admin/hotels' and method == 'GET':
                with admin_tx() as cur:
                    cur.execute("""SELECT h.hotel_id, h.name, h.status, h.synced_version, h.last_seen,
                                     (SELECT count(*) FROM bills b WHERE b.hotel_id = h.hotel_id AND NOT b.deleted),
                                     (SELECT count(*) FROM conflicts c WHERE c.hotel_id = h.hotel_id),
                                     (SELECT count(*) FROM commands m WHERE m.hotel_id = h.hotel_id AND m.acked_at IS NULL)
                                   FROM hotels h ORDER BY h.hotel_id""")
                    cols = ['hotel', 'name', 'status', 'syncedVersion', 'lastSeen', 'bills', 'conflicts', 'pendingCommands']
                    return 200, {'hotels': [dict(zip(cols, r)) for r in cur.fetchall()]}
            hid = str(body.get('hotel') or q.get('hotel') or '')
            if path == '/v1/admin/command' and method == 'POST':
                kind, payload = body.get('kind'), body.get('payload')
                if kind not in ('licence_key', 'vendor_message', 'vendor_lock') or not isinstance(payload, dict):
                    raise HttpError(400, 'kind: licence_key | vendor_message | vendor_lock; payload object')
                if kind == 'licence_key' and not re.fullmatch(r'SETU-[A-Z2-7]{20,400}', str(payload.get('key') or '')):
                    raise HttpError(400, 'a licence key starts with SETU-')
                with tenant_tx(hid) as cur:
                    cur.execute('INSERT INTO commands (hotel_id, kind, payload, created_by) VALUES (%s, %s, %s, %s) RETURNING seq', (hid, kind, Jsonb(payload), _s(body.get('by'), 60) or 'admin'))
                    return 200, {'seq': cur.fetchone()[0]}
            if path == '/v1/admin/commands' and method == 'GET':
                with tenant_tx(hid) as cur:
                    cur.execute('SELECT seq, kind, payload, created_at, acked_at, result FROM commands WHERE hotel_id = %s ORDER BY seq DESC LIMIT 100', (hid,))
                    return 200, {'commands': [dict(zip(['seq', 'kind', 'payload', 'at', 'ackedAt', 'result'], r)) for r in cur.fetchall()]}
            if path == '/v1/admin/status' and method == 'POST':
                if body.get('status') not in ('active', 'suspended'):
                    raise HttpError(400, 'status: active | suspended')
                with tenant_tx(hid) as cur:
                    cur.execute('UPDATE hotels SET status = %s WHERE hotel_id = %s', (body['status'], hid))
                return 200, {'ok': True}
            if path == '/v1/admin/backup' and method == 'POST':
                return 200, backup(hid)
            if path == '/v1/admin/backup/verify' and method == 'POST':
                return 200, verify_backup(hid, str(body.get('id') or ''))
            if path == '/v1/admin/backups' and method == 'GET':
                with tenant_tx(hid) as cur:
                    cur.execute('SELECT id, at, bytes, sha256, bills, synced_version, verified FROM backups WHERE hotel_id = %s ORDER BY at DESC', (hid,))
                    return 200, {'backups': [dict(zip(['id', 'at', 'bytes', 'sha256', 'bills', 'syncedVersion', 'verified'], r)) for r in cur.fetchall()]}
            if path == '/v1/admin/conflicts' and method == 'GET':
                with tenant_tx(hid) as cur:
                    cur.execute('SELECT seq, k, rid, reason, stored, incoming, at FROM conflicts WHERE hotel_id = %s ORDER BY seq DESC LIMIT 200', (hid,))
                    return 200, {'conflicts': [dict(zip(['seq', 'k', 'id', 'reason', 'stored', 'incoming', 'at'], r)) for r in cur.fetchall()]}
            raise HttpError(404, 'not found')
        raise HttpError(404, 'not found')


def serve(port):
    srv = http.server.ThreadingHTTPServer(('0.0.0.0', port), Handler)
    srv.daemon_threads = True
    srv.request_queue_size = 128
    srv.serve_forever()


if __name__ == '__main__':
    p = int(sys.argv[sys.argv.index('--port') + 1]) if '--port' in sys.argv else 8790
    if not DSN:
        sys.exit('SETU_PG_DSN is required')
    serve(p)
