with open('app_main.py', 'r', encoding='utf-8') as f:
    text = f.read()

# 1. apply_ops target
target1 = """            summary = {'keys': sorted(set(writes_rec) | set(writes_map) | set(writes_whole)), 'records': sum(len(u) + len(r) for _, u, r in writes_rec.values()), 'op': opid}
            c.execute('INSERT INTO sync_outbox (op, ref, doc_version, payload, at) VALUES (?, ?, ?, ?, ?)', ('ops', opid or None, version, json.dumps(summary), now))"""

replacement1 = """            summary = {'keys': sorted(set(writes_rec) | set(writes_map) | set(writes_whole)), 'records': sum(len(u) + len(r) for _, u, r in writes_rec.values()), 'op': opid}
            hotel_id = self.sdb.meta('hotel_id') or (self._ws.get('settings') or {}).get('hotelCode') or 'UNKNOWN'
            dev_id = body.get('deviceId') or body.get('device') or ('counter_' + str(role))
            op_id_val = opid or f"op_{version}_{secrets.token_hex(6)}"
            envelope = SQ.make_sync_envelope(
                op_id=op_id_val,
                hotel_id=hotel_id,
                device_id=dev_id,
                doc_version=version,
                timestamp=now,
                event_type='settle' if opid and opid.startswith('settle:') else ('cancel' if opid and opid.startswith('cancel:') else 'ops'),
                actor={'role': role, 'elevated': bool(elev)},
                writes_rec=writes_rec,
                writes_map=writes_map,
                writes_whole=writes_whole,
                conflicts=conflicts
            )
            SQ.SqliteDoc.append_outbox(c, 'ops', op_id_val, version, envelope, now)"""

assert target1 in text, 'target1 not found in app_main.py'
text = text.replace(target1, replacement1, 1)

# 2. write target
target2 = """            c.execute('INSERT INTO sync_outbox (op, ref, doc_version, payload, at) VALUES (?, ?, ?, ?, ?)', (outbox[0], outbox[1], version, json.dumps({'keys': touched}), saved_at))"""

replacement2 = """            hotel_id = self.sdb.meta('hotel_id') or (self._ws.get('settings') or {}).get('hotelCode') or 'UNKNOWN'
            changed_values = {k: data_obj[k] for k in touched}
            envelope = SQ.make_sync_envelope(
                op_id=outbox[1] or f"srv_{version}_{secrets.token_hex(6)}",
                hotel_id=hotel_id,
                device_id='counter_server',
                doc_version=version,
                timestamp=saved_at,
                event_type=outbox[0] or 'write',
                actor={'role': 'server', 'elevated': True},
                writes_whole=changed_values
            )
            SQ.SqliteDoc.append_outbox(c, outbox[0], outbox[1] or envelope['op_id'], version, envelope, saved_at)"""

assert target2 in text, 'target2 not found in app_main.py'
text = text.replace(target2, replacement2, 1)

# 3. replace_all target
target3 = """            c.execute('INSERT INTO sync_outbox (op, ref, doc_version, payload, at) VALUES (?, ?, ?, ?, ?)', ('restore', None, version, '{}', saved_at))"""

replacement3 = """            hotel_id = self.sdb.meta('hotel_id') or (doc.get('settings') or {}).get('hotelCode') or 'UNKNOWN'
            envelope = SQ.make_sync_envelope(
                op_id=f"restore_{version}_{secrets.token_hex(6)}",
                hotel_id=hotel_id,
                device_id='counter_server',
                doc_version=version,
                timestamp=saved_at,
                event_type='restore',
                actor={'role': 'manager', 'elevated': True},
                writes_whole={k: v for k, v in doc.items() if k not in HIST_KEYS}
            )
            SQ.SqliteDoc.append_outbox(c, 'restore', envelope['op_id'], version, envelope, saved_at)"""

assert target3 in text, 'target3 not found in app_main.py'
text = text.replace(target3, replacement3, 1)

# 4. Add convenience methods on SqliteSetuStore
target4 = """    def replace_all(self, doc):"""
methods_to_add = """    def get_pending_outbox(self, limit=100, include_legacy=True):
        with self.sdb.rlock():
            return self.sdb.get_pending_outbox(self.sdb.con(), limit=limit, include_legacy=include_legacy)

    def ack_outbox(self, confirmed_keys, now=None):
        with self.sdb.tx() as c:
            return self.sdb.ack_outbox(c, confirmed_keys, now=now)

    def replace_all(self, doc):"""

assert target4 in text, 'target4 not found in app_main.py'
text = text.replace(target4, methods_to_add, 1)

with open('app_main.py', 'w', encoding='utf-8') as f:
    f.write(text)

print('app_main.py updated successfully!')
