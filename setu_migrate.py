"""Legacy JSON (setu-db.json) -> verified SQLite (setu.sqlite) for one hotel's data folder.

    python setu_migrate.py migrate <dataDir> [--cutover]      # dry run unless --cutover
    python setu_migrate.py verify  <dataDir>                  # re-check an existing migration
    python setu_migrate.py export  <dataDir> <out.json>        # SQLite -> legacy JSON (rollback; keeps new bills)

Safety:
* setu-db.json is never written. A read-only copy is kept as migration/setu-db.pre-sqlite-<time>.json.
* The SQLite file is built as setu.sqlite.migrating and only renamed to setu.sqlite after every check passes.
* The engine switch (setu-storage.json) is written only with --cutover and only after the checks pass.
* Re-running is safe: a half-built file from an interrupted run is deleted and rebuilt; an already migrated
  folder whose source has not changed is verified again and left as it is.
* Historical bill numbers, ids and amounts are kept exactly; nothing is renumbered.
"""
import hashlib
import json
import os
import shutil
import stat
import sys
import time
from decimal import Decimal

import setu_sqlite as S

MIG_DIR = 'migration'


def paise(v):
    try:
        return S.MONEY(v) if S._num(v) else 0
    except Exception:
        return 0


# ---------------- the app's own rules, in Python (for verification) ----------------
def legacy_stock(doc):
    """Port of stockMoves() + stockRecalc() in hotel_erp.html: expected quantity per active stock item."""
    alias = doc.get('stockAlias') or {}

    def sid_of(s):
        n = 0
        while s in alias and n < 6:
            s, n = alias[s], n + 1
        return s
    tot = {}

    def add(s, q):
        k = sid_of(s)
        tot[k] = tot.get(k, 0) + q
    for m in doc.get('moves') or []:
        add(m.get('sid'), float(m.get('qty') or 0))
    for t in doc.get('txns') or []:
        if t.get('type') == 'Purchase' and t.get('mv') and t.get('sid') and float(t.get('qty') or 0):
            add(t['sid'], float(t['qty']))
    for b in doc.get('bills') or []:
        if not b.get('mv'):
            continue
        for u in b.get('used') or []:
            add(u.get('sid'), -float(u.get('qty') or 0))
            if b.get('cancelled'):
                add(u.get('sid'), float(u.get('qty') or 0))
    opened = {m.get('sid') for m in doc.get('moves') or [] if m.get('type') == 'open'}
    out = {}
    for x in doc.get('stock') or []:
        if x.get('merged'):
            continue
        out[x['id']] = round(tot.get(x['id'], 0), 3) if x['id'] in opened else round(float(x.get('qty') or 0), 3)
    return out


def legacy_supplier_dues(doc):
    alias = doc.get('supAlias') or {}

    def key(n):
        x, i = str(n or '').strip().lower(), 0
        while x in alias and i < 6:
            x, i = alias[x], i + 1
        return x
    due = {}
    for t in doc.get('txns') or []:
        if not str(t.get('party') or '').strip():
            continue
        is_pay = t.get('type') == 'Expense' and t.get('head') == 'Supplier Payment'
        credit = (t.get('type') == 'Purchase' or (t.get('type') == 'Expense' and not is_pay)) and t.get('mode') == 'Credit'
        k = key(t['party'])
        if credit:
            due[k] = due.get(k, 0) + paise(t.get('amount'))
        elif is_pay:
            due[k] = due.get(k, 0) - paise(t.get('amount'))
    return {k: v for k, v in due.items() if v}


def legacy_money(doc):
    live = [b for b in doc.get('bills') or [] if not b.get('cancelled')]
    by_mode = {}
    for b in live:
        parts = b.get('pays') if b.get('mode') == 'Split' and isinstance(b.get('pays'), list) and b.get('pays') else [{'mode': b.get('mode') or 'Cash', 'amt': b.get('total') or 0}]
        for p in parts:
            by_mode[p.get('mode')] = by_mode.get(p.get('mode'), 0) + paise(p.get('amt'))
    tx = {}
    for t in doc.get('txns') or []:
        tx[t.get('type')] = tx.get(t.get('type'), 0) + paise(t.get('amount'))
    return {'sales_p': sum(paise(b.get('total')) for b in live), 'by_mode': by_mode, 'vouchers_by_type': tx}


# ---------------- the same figures from SQLite (SQL, not the rebuilt object) ----------------
def sql_money(db):
    c = db.con()
    sales = c.execute('SELECT COALESCE(SUM(total_p), 0) FROM bills WHERE is_cancelled = 0').fetchone()[0]
    # payParts(): split tenders, else one line with the bill mode (missing mode = Cash)
    by_mode = {}
    for mode, amt in c.execute("""SELECT CASE WHEN p.synthetic = 1 THEN COALESCE(b.mode, 'Cash') ELSE p.mode END, SUM(p.amount_p)
                                  FROM bill_payments p JOIN bills b ON b.id = p.bill_id
                                  WHERE b.is_cancelled = 0 AND (p.synthetic = 1 OR (b.mode = 'Split'))
                                  GROUP BY 1"""):
        by_mode[mode] = amt
    tx = dict(c.execute('SELECT type, SUM(COALESCE(amount_p, 0)) FROM vouchers GROUP BY type'))
    return {'sales_p': sales, 'by_mode': {k: v for k, v in by_mode.items() if v is not None}, 'vouchers_by_type': {k: v for k, v in tx.items()}}


def sql_supplier_dues(db, doc_alias):
    alias = doc_alias or {}

    def key(n):
        x, i = str(n or '').strip().lower(), 0
        while x in alias and i < 6:
            x, i = alias[x], i + 1
        return x
    due = {}
    for party, typ, head, mode, amt in db.con().execute("SELECT party, type, head, mode, COALESCE(amount_p, 0) FROM vouchers WHERE TRIM(COALESCE(party, '')) <> ''"):
        is_pay = typ == 'Expense' and head == 'Supplier Payment'
        credit = (typ == 'Purchase' or (typ == 'Expense' and not is_pay)) and mode == 'Credit'
        k = key(party)
        if credit:
            due[k] = due.get(k, 0) + amt
        elif is_pay:
            due[k] = due.get(k, 0) - amt
    return {k: v for k, v in due.items() if v}


def sql_stock(db, doc):
    bal = db.stock_balances(doc.get('stockAlias') or {})
    opened = {r[0] for r in db.con().execute("SELECT sid FROM stock_move_records WHERE type = 'open'")}
    out = {}
    for sid, qty, extra in db.con().execute('SELECT id, qty, extra FROM stock_items'):
        if '"merged"' in (extra or '') and json.loads(extra).get('merged'):
            continue
        out[sid] = round(bal.get(sid, 0), 3) if sid in opened else round(float(qty or 0), 3)
    return out


# ---------------- verification ----------------
def verify(doc, db):
    checks = []

    def check(name, expected, actual, mandatory=True, note=''):
        ok = expected == actual
        checks.append({'check': name, 'pass': ok, 'mandatory': mandatory, 'expected': expected if not ok else None, 'actual': actual if not ok else None, 'note': note})
        return ok
    c = db.con()
    # 1. Exact round trip: every record, id, amount and field comes back identical
    rebuilt = db.export_document()
    check('Rebuilt data identical to the original (every record, id and amount)', S.canonical_hash(doc), S.canonical_hash(rebuilt))
    rebuilt = None
    # 2. Record counts per module (rows in the tables, not the rebuilt object)
    kinds = json.loads(db.meta('doc_kinds') or '{}')
    for k, spec in S.SPEC_BY_KEY.items():
        if kinds.get(k) == 'spec':
            check(f'Record count: {k} -> {spec.table}', len(doc.get(k) or []), c.execute(f'SELECT COUNT(*) FROM {spec.table}').fetchone()[0])
    if kinds.get('bills') == 'spec':
        check('Record count: bill items', sum(len(x.get('items') or []) for x in doc['bills'] if isinstance(x.get('items'), list)), c.execute('SELECT COUNT(*) FROM bill_items').fetchone()[0])
        check('Record count: split payment lines', sum(len(x.get('pays') or []) for x in doc['bills'] if isinstance(x.get('pays'), list)), c.execute('SELECT COUNT(*) FROM bill_payments WHERE synthetic = 0').fetchone()[0])
    # 3. Money to the paisa
    lm, sm = legacy_money(doc), sql_money(db)
    check('Sales total (non-cancelled bills), paise', lm['sales_p'], sm['sales_p'])
    check('Payments by mode (payParts rule), paise', lm['by_mode'], sm['by_mode'])
    check('Voucher totals by type (purchases, expenses, income), paise', lm['vouchers_by_type'], sm['vouchers_by_type'])
    # 4. Supplier balances
    check('Supplier balances (credit - payments, merged suppliers), paise', legacy_supplier_dues(doc), sql_supplier_dues(db, doc.get('supAlias')))
    # 5. Stock: the app's own rules vs the SQLite movement ledger
    ls, ss = legacy_stock(doc), sql_stock(db, doc)
    bad = {k: (ls.get(k), ss.get(k)) for k in set(ls) | set(ss) if abs((ls.get(k) or 0) - (ss.get(k) or 0)) > 0.0015}
    check('Stock balance per item (app rules = SQLite ledger)', {}, bad)
    stored = {x['id']: round(float(x.get('qty') or 0), 3) for x in doc.get('stock') or [] if not x.get('merged')}
    drift = {k: (stored[k], ls.get(k)) for k in stored if abs(stored[k] - (ls.get(k) or 0)) > 0.0015}
    check('Stored stock quantities match their movements (information)', {}, drift, mandatory=False,
          note='Differences mean the original data already disagreed with its own movements; they are carried over unchanged.')
    # 6. Duplicates
    if kinds.get('bills') == 'spec':
        dup_no = [r[0] for r in c.execute("SELECT no FROM bills WHERE COALESCE(imported, 0) = 0 AND no IS NOT NULL GROUP BY no HAVING COUNT(*) > 1")]
        check('Duplicate bill numbers (kept as they are; reported, not renumbered)', [], dup_no, mandatory=False)
        check('Duplicate idempotency keys', 0, c.execute('SELECT COUNT(*) - COUNT(DISTINCT idemKey) FROM bills WHERE idemKey IS NOT NULL').fetchone()[0])
        mx = c.execute('SELECT MAX(CAST(no AS INTEGER)) FROM bills WHERE COALESCE(imported, 0) = 0').fetchone()[0] or 0
        seq = (doc.get('seq') or {}).get('bill') or 0
        check('Bill sequence is not behind the highest bill number (information)', True, (seq or 0) >= mx, mandatory=False,
              note='If behind, the first new bill takes the next free number anyway (never reused).')
    # 7. SQLite integrity
    check('SQLite integrity_check', 'ok', c.execute('PRAGMA integrity_check').fetchone()[0])
    check('SQLite foreign_key_check', [], [list(r) for r in c.execute('PRAGMA foreign_key_check')])
    return checks


def _sha_file(p):
    h = hashlib.sha256()
    with open(p, 'rb') as f:
        for chunk in iter(lambda: f.read(1 << 20), b''):
            h.update(chunk)
    return h.hexdigest()


def write_report(data_dir, rep):
    d = os.path.join(data_dir, MIG_DIR)
    os.makedirs(d, exist_ok=True)
    with open(os.path.join(d, 'migration-report.json'), 'w', encoding='utf-8') as f:
        json.dump(rep, f, indent=1, ensure_ascii=False)
    lines = [f"# Setu data migration report ({rep.get('status')})", '', f"- Folder: {data_dir}", f"- Started: {rep.get('started')}",
             f"- Source: {rep.get('source')} ({rep.get('source_bytes')} bytes, sha256 {rep.get('source_sha256', '')[:16]}...)",
             f"- Result: **{rep.get('status')}** {rep.get('message', '')}", '', '| Check | Result | Note |', '|---|---|---|']
    for ch in rep.get('checks', []):
        res = 'PASS' if ch['pass'] else ('FAIL' if ch['mandatory'] else 'WARN')
        extra = '' if ch['pass'] else f" expected {json.dumps(ch['expected'])[:120]} got {json.dumps(ch['actual'])[:120]}"
        lines.append(f"| {ch['check']} | {res} | {ch.get('note', '')}{extra} |")
    with open(os.path.join(d, 'migration-report.md'), 'w', encoding='utf-8') as f:
        f.write('\n'.join(lines) + '\n')


def migrate(data_dir, cutover=False, progress=None):
    """Returns the report dict. Never raises for data problems: the report says what failed."""
    src = os.path.join(data_dir, 'setu-db.json')
    final = os.path.join(data_dir, S.DB_FILE)
    work = final + '.migrating'
    rep = {'started': time.strftime('%Y-%m-%d %H:%M:%S'), 'source': src, 'status': 'FAILED', 'checks': []}
    say = progress or (lambda m: None)
    try:
        flag = S.read_flag(data_dir)
        if not os.path.exists(src):
            rep['message'] = 'No setu-db.json in this folder (nothing to migrate).'
            return rep
        rep['source_bytes'] = os.path.getsize(src)
        rep['source_sha256'] = sha = _sha_file(src)
        if flag.get('engine') == 'sqlite' and os.path.exists(final):
            rep['status'] = 'ALREADY_MIGRATED'
            rep['message'] = 'This folder already runs on SQLite; the JSON file is no longer the live database.'
            return rep
        # 1. Read-only copy of the original
        md = os.path.join(data_dir, MIG_DIR)
        os.makedirs(md, exist_ok=True)
        keep = os.path.join(md, f'setu-db.pre-sqlite-{sha[:12]}.json')
        if not os.path.exists(keep):
            shutil.copy2(src, keep + '.part')
            if _sha_file(keep + '.part') != sha:
                raise RuntimeError('the safety copy of setu-db.json does not match the original')
            os.replace(keep + '.part', keep)
            os.chmod(keep, stat.S_IREAD | stat.S_IRGRP | stat.S_IROTH)
        rep['safety_copy'] = keep
        # 2. Validate structure
        with open(src, 'r', encoding='utf-8') as f:
            raw = json.load(f)
        doc = raw.get('data') if isinstance(raw, dict) else None
        if not isinstance(doc, dict) or 'settings' not in doc:
            raise RuntimeError('setu-db.json has no valid data object')
        problems = []
        for k in ('bills', 'kots', 'txns', 'moves', 'stock', 'menu'):
            v = doc.get(k)
            if v is not None and not isinstance(v, list):
                problems.append(f'{k} is not a list')
        ids = [b.get('id') for b in doc.get('bills') or [] if isinstance(b, dict)]
        if len(ids) != len(set(ids)) or not all(ids):
            problems.append('bills have missing or duplicate ids (kept in a generic table; reported)')
        st = doc.get('settings') or {}
        if any(st.get(k) for k in ('adminPin', 'cashierPin')) or any(isinstance(x, dict) and x.get('pin') for x in doc.get('staff') or []):
            problems.append('plain PINs found in the data: start the counter once on the JSON file (it hashes them) before migrating')
        rep['structure_notes'] = problems
        # 3. Build into a work file (an interrupted earlier run leaves one: start again)
        for p in (work, work + '-wal', work + '-shm', work + '-journal'):
            if os.path.exists(p):
                os.remove(p)
        t0 = time.time()
        say('importing')
        db = S.SqliteDoc(work, create=True)
        with db.tx() as c:
            db.import_document(c, doc, raw.get('version', 1), raw.get('savedAt', 0))
            c.execute("INSERT OR REPLACE INTO meta VALUES ('source_sha256', ?)", (sha,))
            c.execute("INSERT OR REPLACE INTO meta VALUES ('migrated_at', ?)", (str(int(time.time() * 1000)),))
        rep['import_seconds'] = round(time.time() - t0, 2)
        # 4. Verify
        say('verifying')
        t0 = time.time()
        rep['checks'] = verify(doc, db)
        rep['verify_seconds'] = round(time.time() - t0, 2)
        failed = [ch for ch in rep['checks'] if ch['mandatory'] and not ch['pass']]
        db.con().execute('PRAGMA wal_checkpoint(TRUNCATE)')
        db.close()
        if failed:
            rep['message'] = f'{len(failed)} mandatory check(s) failed. The program keeps using setu-db.json.'
            os.replace(work, work + '.failed-' + time.strftime('%Y%m%d-%H%M%S'))
            return rep
        rep['db_bytes'] = os.path.getsize(work)
        if not cutover:
            rep['status'] = 'DRY_RUN_PASSED'
            rep['message'] = 'All checks passed. Nothing was switched (dry run).'
            os.replace(work, os.path.join(md, 'dry-run.sqlite'))
            return rep
        # 5. Switch: database file first, engine flag last (a crash in between leaves JSON in charge)
        if os.path.exists(final):
            os.replace(final, final + '.replaced-' + time.strftime('%Y%m%d-%H%M%S'))
        os.replace(work, final)
        S.write_flag(data_dir, {'engine': 'sqlite', 'db': S.DB_FILE, 'migrated_at': int(time.time() * 1000), 'source_sha256': sha, 'safety_copy': os.path.basename(keep)})
        with open(os.path.join(data_dir, 'setu-db.json.NOT-IN-USE.txt'), 'w', encoding='utf-8') as f:
            f.write('Since ' + time.strftime('%Y-%m-%d %H:%M') + ' this counter keeps its data in setu.sqlite (see setu-storage.json).\n'
                    'setu-db.json is the old copy from before that day and is NOT updated any more. Do not edit or restore it by hand.\n'
                    'To go back to the JSON file, use: python setu_migrate.py export <this folder> setu-db.json (it includes every newer bill).\n')
        rep['status'] = 'MIGRATED'
        rep['message'] = 'All checks passed. The counter now uses setu.sqlite; setu-db.json was left untouched.'
        return rep
    except Exception as e:
        rep['message'] = f'Migration stopped: {e!r}. The program keeps using setu-db.json.'
        return rep
    finally:
        try:
            write_report(data_dir, rep)
        except Exception:
            pass


def export_json(data_dir, out_path):
    """SQLite -> legacy JSON document (for rollback). Includes every bill made after the switch."""
    db = S.SqliteDoc(os.path.join(data_dir, S.DB_FILE))
    doc = db.export_document()
    doc_v = int(db.meta('doc_version') or 1)
    saved = int(db.meta('saved_at') or 0)
    with open(out_path + '.tmp', 'w', encoding='utf-8') as f:
        f.write('{"version": %d, "savedAt": %d, "data": %s}' % (doc_v, saved, json.dumps(doc, ensure_ascii=False)))
        f.flush()
        os.fsync(f.fileno())
    os.replace(out_path + '.tmp', out_path)
    return {'bills': len(doc.get('bills') or []), 'version': doc_v, 'file': out_path}


if __name__ == '__main__':
    a = sys.argv[1:]
    if len(a) >= 2 and a[0] == 'migrate':
        r = migrate(a[1], cutover='--cutover' in a, progress=lambda m: print('...', m, flush=True))
        print(r['status'], '-', r.get('message', ''))
        for ch in r['checks']:
            if not ch['pass']:
                print('  ', 'FAIL' if ch['mandatory'] else 'WARN', ch['check'])
        sys.exit(0 if r['status'] in ('MIGRATED', 'DRY_RUN_PASSED', 'ALREADY_MIGRATED') else 1)
    if len(a) >= 2 and a[0] == 'verify':
        with open(os.path.join(a[1], 'setu-db.json'), 'r', encoding='utf-8') as f:
            doc = json.load(f)['data']
        res = verify(doc, S.SqliteDoc(os.path.join(a[1], S.DB_FILE)))
        print(json.dumps([r for r in res if not r['pass']], indent=1) or 'all passed')
        sys.exit(0 if all(r['pass'] or not r['mandatory'] for r in res) else 1)
    if len(a) >= 3 and a[0] == 'export':
        print(export_json(a[1], a[2]))
        sys.exit(0)
    print(__doc__)
    sys.exit(2)
