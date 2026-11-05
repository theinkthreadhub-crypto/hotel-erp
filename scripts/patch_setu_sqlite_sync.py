import re

# 1. Update setu_sqlite.py
with open('setu_sqlite.py', 'r', encoding='utf-8') as f:
    stext = f.read()

# Add import secrets
if 'import secrets' not in stext:
    stext = stext.replace('import time\n', 'import time\nimport secrets\n', 1)

# Add indexes to schema
schema_target = """CREATE TABLE IF NOT EXISTS sync_outbox (
  seq INTEGER PRIMARY KEY AUTOINCREMENT, op TEXT NOT NULL, ref TEXT, doc_version INTEGER, payload TEXT, at INTEGER NOT NULL, sent_at INTEGER);"""

schema_replacement = """CREATE TABLE IF NOT EXISTS sync_outbox (
  seq INTEGER PRIMARY KEY AUTOINCREMENT, op TEXT NOT NULL, ref TEXT, doc_version INTEGER, payload TEXT, at INTEGER NOT NULL, sent_at INTEGER);
CREATE INDEX IF NOT EXISTS idx_sync_outbox_pending ON sync_outbox(sent_at, seq);
CREATE INDEX IF NOT EXISTS idx_sync_outbox_ref ON sync_outbox(ref);"""

assert schema_target in stext, 'schema_target not found in setu_sqlite.py'
stext = stext.replace(schema_target, schema_replacement, 1)

# Add methods to SqliteDoc
doc_target = """    @staticmethod
    def set_version(c, version, saved_at):
        c.execute("INSERT OR REPLACE INTO meta VALUES ('doc_version', ?)", (str(int(version)),))
        c.execute("INSERT OR REPLACE INTO meta VALUES ('saved_at', ?)", (str(int(saved_at or 0)),))"""

doc_replacement = """    @staticmethod
    def set_version(c, version, saved_at):
        c.execute("INSERT OR REPLACE INTO meta VALUES ('doc_version', ?)", (str(int(version)),))
        c.execute("INSERT OR REPLACE INTO meta VALUES ('saved_at', ?)", (str(int(saved_at or 0)),))

    @staticmethod
    def append_outbox(c, op, ref, doc_version, payload_obj_or_str, at=None):
        if at is None:
            at = int(time.time() * 1000)
        p_str = json.dumps(payload_obj_or_str, ensure_ascii=False) if isinstance(payload_obj_or_str, (dict, list)) else str(payload_obj_or_str or '{}')
        c.execute('INSERT INTO sync_outbox (op, ref, doc_version, payload, at) VALUES (?, ?, ?, ?, ?)',
                  (str(op), str(ref) if ref else None, int(doc_version), p_str, int(at)))
        return c.lastrowid

    def get_pending_outbox(self, con=None, limit=100, include_legacy=True):
        if con is None:
            con = self.con()
        rows = con.execute(
            "SELECT seq, op, ref, doc_version, payload, at, sent_at FROM sync_outbox WHERE sent_at IS NULL ORDER BY seq ASC LIMIT ?",
            (int(limit),)
        ).fetchall()
        result = []
        for seq, op, ref, dv, p_raw, at, sent_at in rows:
            try:
                p_obj = json.loads(p_raw or '{}')
            except Exception:
                p_obj = {}
            is_leg = is_legacy_outbox(p_obj)
            if not include_legacy and is_leg:
                continue
            result.append({
                'seq': seq,
                'op': op,
                'ref': ref,
                'doc_version': dv,
                'payload': p_obj,
                'at': at,
                'sent_at': sent_at,
                'is_legacy': is_leg
            })
        return result

    def ack_outbox(self, con, confirmed_keys, now=None):
        \"\"\"Acknowledge ONLY confirmed operations by seq, ref or envelope op_id. Never bulk marks unconfirmed rows.\"\"\"
        if not confirmed_keys:
            return 0
        if now is None:
            now = int(time.time() * 1000)
        confirmed_set = set(str(k) for k in confirmed_keys if k is not None)
        if not confirmed_set:
            return 0
        pending = con.execute("SELECT seq, ref, payload FROM sync_outbox WHERE sent_at IS NULL").fetchall()
        matched = []
        for seq, ref, p_str in pending:
            if str(seq) in confirmed_set or (ref and str(ref) in confirmed_set):
                matched.append(seq)
                continue
            try:
                p = json.loads(p_str or '{}')
                if str(p.get('op_id') or '') in confirmed_set:
                    matched.append(seq)
            except Exception:
                pass
        if matched:
            q = ','.join('?' * len(matched))
            con.execute(f"UPDATE sync_outbox SET sent_at = ? WHERE seq IN ({q})", [int(now)] + matched)
        return len(matched)"""

assert doc_target in stext, 'doc_target not found in setu_sqlite.py'
stext = stext.replace(doc_target, doc_replacement, 1)

# Add make_sync_envelope and is_legacy_outbox at bottom of setu_sqlite.py
envelope_code = """

# ---------------------------------------------------------------------------------------------------------
# Phase 3.0: Reliable Sync Foundation & Operation Envelopes
# ---------------------------------------------------------------------------------------------------------

def is_legacy_outbox(payload):
    \"\"\"Returns True if an outbox payload is a legacy summary-only record.\"\"\"
    if isinstance(payload, str):
        try:
            payload = json.loads(payload)
        except Exception:
            return True
    if not isinstance(payload, dict):
        return True
    return payload.get('envelope_version') != 1


def make_sync_envelope(
    op_id,
    hotel_id,
    device_id,
    doc_version,
    timestamp,
    event_type='ops',
    actor=None,
    writes_rec=None,
    writes_map=None,
    writes_whole=None,
    conflicts=None
):
    \"\"\"
    Constructs an immutable, durable Phase 3.0 operation sync envelope.
    Contains the complete business records and mutations needed to reproduce
    the committed transaction deterministically on the cloud or another replica.
    Strictly sanitizes all credentials, passwords, and PIN hashes.
    \"\"\"
    clean_rec = {}
    total_records = 0
    if writes_rec:
        for k, val in writes_rec.items():
            if isinstance(val, (list, tuple)) and len(val) == 3:
                kind, ups, rms = val
            elif isinstance(val, dict):
                kind = val.get('kind', 'rec')
                ups = val.get('ups') or []
                rms = val.get('rm') or []
            else:
                continue

            clean_ups = []
            for r in ups:
                if isinstance(r, dict):
                    # Strip any potential secrets/PINs from staff or users
                    cr = {rk: rv for rk, rv in r.items() if not any(x in rk.lower() for x in ('pin', 'pass', 'hash', 'secret'))}
                    clean_ups.append(cr)
                else:
                    clean_ups.append(r)
            clean_rms = [str(x) for x in rms]
            total_records += len(clean_ups) + len(clean_rms)
            clean_rec[k] = {
                'kind': kind,
                'ups': clean_ups,
                'rm': clean_rms
            }

    clean_map = {}
    if writes_map:
        for k, val in writes_map.items():
            if isinstance(val, (list, tuple)) and len(val) == 3:
                kind, s_, d_ = val
            elif isinstance(val, dict):
                kind = val.get('kind', 'map')
                s_ = val.get('set') or {}
                d_ = val.get('del') or []
            else:
                continue
            clean_map[k] = {
                'kind': kind,
                'set': dict(s_),
                'del': [str(x) for x in d_]
            }

    clean_values = {}
    if writes_whole:
        for k, v in writes_whole.items():
            if k in ('secure', 'adminPin', 'password', 'token'):
                continue
            if k == 'settings' and isinstance(v, dict):
                clean_values[k] = {sk: sv for sk, sv in v.items() if not any(x in sk.lower() for x in ('pin', 'pass', 'hash', 'secret', 'key'))}
            elif k == 'auth' and isinstance(v, dict):
                clean_values[k] = {ak: av for ak, av in v.items() if not any(x in ak.lower() for x in ('pin', 'pass', 'hash', 'secret'))}
            else:
                clean_values[k] = v

    payload = {
        'records': clean_rec,
        'maps': clean_map,
        'values': clean_values
    }

    payload_canonical = json.dumps(payload, sort_keys=True, ensure_ascii=False, separators=(',', ':'))
    checksum = hashlib.sha256(payload_canonical.encode('utf-8')).hexdigest()

    clean_conflicts = []
    if conflicts:
        for c in conflicts:
            if isinstance(c, (list, tuple)) and len(c) >= 3:
                clean_conflicts.append({'k': c[0], 'id': str(c[1]), 'reason': str(c[2])})
            elif isinstance(c, dict):
                clean_conflicts.append({'k': c.get('k'), 'id': str(c.get('id') or ''), 'reason': str(c.get('reason') or '')})

    actor_info = {}
    if isinstance(actor, dict):
        actor_info = {'role': str(actor.get('role') or 'local'), 'name': str(actor.get('name') or '')}
    elif actor:
        actor_info = {'role': str(actor), 'name': ''}
    else:
        actor_info = {'role': 'local', 'name': ''}

    envelope = {
        'envelope_version': 1,
        'op_id': str(op_id),
        'hotel_id': str(hotel_id or 'UNKNOWN'),
        'device_id': str(device_id or 'counter'),
        'doc_version': int(doc_version),
        'timestamp': int(timestamp),
        'event_type': str(event_type),
        'actor': actor_info,
        'payload': payload,
        'conflicts': clean_conflicts,
        'integrity': {
            'checksum': f'sha256:{checksum}',
            'record_count': total_records,
            'keys': sorted(set(clean_rec) | set(clean_map) | set(clean_values))
        }
    }
    return envelope
"""

stext += envelope_code

with open('setu_sqlite.py', 'w', encoding='utf-8') as f:
    f.write(stext)
print('setu_sqlite.py updated successfully!')
