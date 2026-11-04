"""HoReCa One / Setu — local SQLite storage for the counter PC (Phase 2).

One SQLite file per hotel (`setu.sqlite` in the hotel's data folder, Hotel ID fixed in `meta`), WAL journal,
synchronous=FULL, foreign keys on, busy timeout, schema versioning. Every business list is stored as rows:
bills / bill_items / bill_payments / bill_used, KOTs, vouchers (purchases, expenses, income, supplier
payments), stock items and a stock movement ledger with transactional balances, menu + recipes, staff,
attendance, audit log, credit notes, purchase orders, customers, cash drawer, salary records.

Lossless: a record's known fields go into typed columns with their exact JSON value (SQLite keeps int / float /
text as given); everything else stays in the row's `extra` JSON. `export_document()` rebuilds exactly the data
object the app has always used, so the existing UI keeps working while storage is incremental:

* `write(doc)` (the existing whole-document upload) runs ONE transaction that touches only records that
  changed (compared in memory with the last committed copy), not the whole database.
* `settle_bill()` / `cancel_bill()` are native transactions: number, rows, stock movements, idempotency
  record and sync-outbox entry commit together or not at all.

Not here (Phase 3): cloud incremental sync. The outbox is written so Phase 3 can send it; nothing sends it yet.
"""
import copy
import gzip
import hashlib
import json
import os
import shutil
import sqlite3
import threading
import time
from decimal import Decimal, ROUND_HALF_UP

SCHEMA_VERSION = 1
DB_FILE = 'setu.sqlite'
FLAG_FILE = 'setu-storage.json'

# ---------------------------------------------------------------------------------------------------------
# Schema. Value columns without a declared type keep the exact JSON scalar (int stays int, 290.0 stays float).
# *_p columns are integer paise for exact money sums; they are projections, never used to rebuild records.
# ---------------------------------------------------------------------------------------------------------
SCHEMA = r"""
CREATE TABLE IF NOT EXISTS meta (k TEXT PRIMARY KEY, v TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS database_migrations (version INTEGER PRIMARY KEY, name TEXT NOT NULL, applied_at INTEGER NOT NULL);
CREATE TABLE IF NOT EXISTS hotels (hotel_id TEXT PRIMARY KEY, created_at INTEGER NOT NULL);

-- Small configuration objects of the data (settings, auth, secure hashes, subscription, saas, ...): one row each
CREATE TABLE IF NOT EXISTS hotel_settings (k TEXT PRIMARY KEY, v TEXT NOT NULL);
-- Running numbers (bill, kot, token, cn, ...). Text values (tokenDate) in t.
CREATE TABLE IF NOT EXISTS sequences (name TEXT PRIMARY KEY, n, t TEXT, ord INTEGER NOT NULL DEFAULT 0);

-- ---------------- Billing & POS ----------------
CREATE TABLE IF NOT EXISTS bills (
  id TEXT PRIMARY KEY, ord INTEGER NOT NULL,
  no, kot, date, time, "table", channel, mode, sub, disc, tax, taxable, total, round, cust, phone, idemKey, mv, imported, cancelled,
  total_p INTEGER, is_cancelled INTEGER NOT NULL DEFAULT 0, arrays TEXT NOT NULL DEFAULT '', extra TEXT NOT NULL DEFAULT '{}');
CREATE INDEX IF NOT EXISTS bills_date ON bills(date);
CREATE INDEX IF NOT EXISTS bills_no ON bills(no);
CREATE INDEX IF NOT EXISTS bills_phone ON bills(phone);
CREATE INDEX IF NOT EXISTS bills_ord ON bills(ord);
CREATE UNIQUE INDEX IF NOT EXISTS bills_idem ON bills(idemKey) WHERE idemKey IS NOT NULL;
CREATE TABLE IF NOT EXISTS bill_items (
  bill_id TEXT NOT NULL REFERENCES bills(id) ON DELETE CASCADE, line INTEGER NOT NULL,
  mid, name, price, qty, extra TEXT NOT NULL DEFAULT '{}', PRIMARY KEY (bill_id, line));
CREATE INDEX IF NOT EXISTS bill_items_mid ON bill_items(mid);
-- Payment lines: the bill's split tenders, or one synthetic line (mode, total) for a single-mode bill
CREATE TABLE IF NOT EXISTS bill_payments (
  bill_id TEXT NOT NULL REFERENCES bills(id) ON DELETE CASCADE, line INTEGER NOT NULL,
  mode, amt, amount_p INTEGER, synthetic INTEGER NOT NULL DEFAULT 0, extra TEXT NOT NULL DEFAULT '{}', PRIMARY KEY (bill_id, line));
CREATE INDEX IF NOT EXISTS bill_payments_mode ON bill_payments(mode);
-- Recipe consumption recorded on the bill (legacy bills[].used)
CREATE TABLE IF NOT EXISTS bill_used (
  bill_id TEXT NOT NULL REFERENCES bills(id) ON DELETE CASCADE, line INTEGER NOT NULL,
  sid, qty, extra TEXT NOT NULL DEFAULT '{}', PRIMARY KEY (bill_id, line));
CREATE TABLE IF NOT EXISTS bill_cancellations (
  bill_id TEXT PRIMARY KEY REFERENCES bills(id) ON DELETE CASCADE, cancelled_by TEXT, recorded_at INTEGER NOT NULL);
-- Every change to an existing bill (edit, cancel, delete) with the old and new record
CREATE TABLE IF NOT EXISTS bill_modifications (
  seq INTEGER PRIMARY KEY AUTOINCREMENT, bill_id TEXT NOT NULL, action TEXT NOT NULL, at INTEGER NOT NULL,
  doc_version INTEGER, old TEXT, new TEXT);
CREATE INDEX IF NOT EXISTS bill_modifications_bill ON bill_modifications(bill_id);
CREATE TABLE IF NOT EXISTS credit_notes (
  id TEXT PRIMARY KEY, ord INTEGER NOT NULL, no, billId, date, total, total_p INTEGER, extra TEXT NOT NULL DEFAULT '{}');
CREATE TABLE IF NOT EXISTS table_orders (tbl TEXT PRIMARY KEY, ord INTEGER NOT NULL, data TEXT NOT NULL);

-- ---------------- KOT & kitchen ----------------
CREATE TABLE IF NOT EXISTS kots (
  id TEXT PRIMARY KEY, ord INTEGER NOT NULL, no, date, time, "table", channel, status, arrays TEXT NOT NULL DEFAULT '', extra TEXT NOT NULL DEFAULT '{}');
CREATE INDEX IF NOT EXISTS kots_date ON kots(date);
CREATE TABLE IF NOT EXISTS kot_items (
  kot_id TEXT NOT NULL REFERENCES kots(id) ON DELETE CASCADE, line INTEGER NOT NULL,
  mid, name, qty, extra TEXT NOT NULL DEFAULT '{}', PRIMARY KEY (kot_id, line));
CREATE TABLE IF NOT EXISTS kot_status_history (
  seq INTEGER PRIMARY KEY AUTOINCREMENT, kot_id TEXT NOT NULL, old_status TEXT, new_status TEXT, at INTEGER NOT NULL);

-- ---------------- Menu & recipes ----------------
CREATE TABLE IF NOT EXISTS menu_items (
  id TEXT PRIMARY KEY, ord INTEGER NOT NULL, name, cat, price, arrays TEXT NOT NULL DEFAULT '', extra TEXT NOT NULL DEFAULT '{}');
CREATE TABLE IF NOT EXISTS recipe_ingredients (
  menu_id TEXT NOT NULL REFERENCES menu_items(id) ON DELETE CASCADE, line INTEGER NOT NULL,
  sid, qty, extra TEXT NOT NULL DEFAULT '{}', PRIMARY KEY (menu_id, line));

-- ---------------- Inventory ----------------
CREATE TABLE IF NOT EXISTS stock_items (
  id TEXT PRIMARY KEY, ord INTEGER NOT NULL, name, unit, qty, rate, cat, extra TEXT NOT NULL DEFAULT '{}');
-- The movement ledger. source = move (D.moves: open, waste, issue, return, adjust, del, merge),
-- purchase (vouchers with mv), sale / cancel (bills with mv). Ids follow the app's own stockMoves() ids,
-- so a bill or purchase can only ever produce its movements once.
CREATE TABLE IF NOT EXISTS stock_movements (
  id TEXT PRIMARY KEY, source TEXT NOT NULL, ref TEXT, sid TEXT NOT NULL, qty REAL NOT NULL, type TEXT, date TEXT, time TEXT);
CREATE INDEX IF NOT EXISTS stock_movements_sid ON stock_movements(sid, date);
CREATE INDEX IF NOT EXISTS stock_movements_ref ON stock_movements(source, ref);
-- D.moves rows themselves (lossless copy of the app's movement records; the ledger above is built from them)
CREATE TABLE IF NOT EXISTS stock_move_records (
  id TEXT PRIMARY KEY, ord INTEGER NOT NULL, sid, qty, type, date, time, extra TEXT NOT NULL DEFAULT '{}');
-- Current balance per stock id, kept by triggers in the same transaction as every movement
CREATE TABLE IF NOT EXISTS stock_balances (sid TEXT PRIMARY KEY, qty REAL NOT NULL DEFAULT 0);
CREATE TRIGGER IF NOT EXISTS stock_movements_ai AFTER INSERT ON stock_movements BEGIN
  INSERT INTO stock_balances(sid, qty) VALUES (NEW.sid, NEW.qty) ON CONFLICT(sid) DO UPDATE SET qty = qty + NEW.qty; END;
CREATE TRIGGER IF NOT EXISTS stock_movements_ad AFTER DELETE ON stock_movements BEGIN
  UPDATE stock_balances SET qty = qty - OLD.qty WHERE sid = OLD.sid; END;

-- ---------------- Vouchers: purchases, supplier payments, expenses, income ----------------
CREATE TABLE IF NOT EXISTS vouchers (
  id TEXT PRIMARY KEY, ord INTEGER NOT NULL, type, date, time, head, party, amount, mode, sid, qty, mv,
  amount_p INTEGER, inv_id TEXT, extra TEXT NOT NULL DEFAULT '{}');
CREATE INDEX IF NOT EXISTS vouchers_date ON vouchers(type, date);
CREATE INDEX IF NOT EXISTS vouchers_party ON vouchers(party);
CREATE INDEX IF NOT EXISTS vouchers_inv ON vouchers(inv_id);
-- Purchase invoice headers (projection of the inv object every purchase line carries)
CREATE TABLE IF NOT EXISTS purchases (inv_id TEXT PRIMARY KEY, no TEXT, party TEXT, date TEXT, total_p INTEGER, paid_p INTEGER, lines INTEGER);
CREATE VIEW IF NOT EXISTS purchase_items AS SELECT * FROM vouchers WHERE type = 'Purchase';
CREATE VIEW IF NOT EXISTS supplier_payments AS SELECT * FROM vouchers WHERE type = 'Expense' AND head = 'Supplier Payment';
CREATE VIEW IF NOT EXISTS expenses AS SELECT * FROM vouchers WHERE type = 'Expense' AND COALESCE(head, '') <> 'Supplier Payment';
CREATE VIEW IF NOT EXISTS income_transactions AS SELECT * FROM vouchers WHERE type = 'Receipt';
CREATE TABLE IF NOT EXISTS purchase_orders (id TEXT PRIMARY KEY, ord INTEGER NOT NULL, party, date, status, extra TEXT NOT NULL DEFAULT '{}');

-- ---------------- Staff, customers, accounting maps ----------------
CREATE TABLE IF NOT EXISTS staff (id TEXT PRIMARY KEY, ord INTEGER NOT NULL, name, role, access, extra TEXT NOT NULL DEFAULT '{}');
CREATE TABLE IF NOT EXISTS attendance (date TEXT NOT NULL, staff_key TEXT NOT NULL, ord INTEGER NOT NULL, v TEXT NOT NULL, PRIMARY KEY (date, staff_key));
CREATE TABLE IF NOT EXISTS cash_drawer_sessions (date TEXT PRIMARY KEY, ord INTEGER NOT NULL, data TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS salary_records (month TEXT PRIMARY KEY, ord INTEGER NOT NULL, data TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS audit_logs (
  id TEXT PRIMARY KEY, ord INTEGER NOT NULL, at, date, action, user, amount, ref, extra TEXT NOT NULL DEFAULT '{}');
CREATE INDEX IF NOT EXISTS audit_logs_date ON audit_logs(date);
CREATE VIEW IF NOT EXISTS customer_loyalty AS
  SELECT phone, COUNT(*) AS bills, SUM(total_p) AS spent_p FROM bills WHERE is_cancelled = 0 AND phone IS NOT NULL AND phone <> '' GROUP BY phone;

-- Lists and maps without a dedicated table (customers list, recurring-expense templates, reservations, assets,
-- gas log, QR log, WhatsApp messages, online orders, error sync, ...): one row per record / entry
CREATE TABLE IF NOT EXISTS ext_records (list TEXT NOT NULL, id TEXT NOT NULL, ord INTEGER NOT NULL, noid INTEGER NOT NULL DEFAULT 0, data TEXT NOT NULL, PRIMARY KEY (list, id));
CREATE INDEX IF NOT EXISTS ext_records_ord ON ext_records(list, ord);
CREATE TABLE IF NOT EXISTS kv_maps (map TEXT NOT NULL, k TEXT NOT NULL, ord INTEGER NOT NULL, v TEXT NOT NULL, PRIMARY KEY (map, k));
CREATE VIEW IF NOT EXISTS customers AS SELECT id, ord, data FROM ext_records WHERE list = 'custList';
CREATE VIEW IF NOT EXISTS recurring_expense_templates AS SELECT id, ord, data FROM ext_records WHERE list = 'expTpl';

-- ---------------- Reliability ----------------
CREATE TABLE IF NOT EXISTS operation_idempotency (
  key TEXT PRIMARY KEY, op TEXT NOT NULL, ref TEXT, request_sha TEXT, actor TEXT, at INTEGER NOT NULL, result TEXT);
CREATE TABLE IF NOT EXISTS sync_outbox (
  seq INTEGER PRIMARY KEY AUTOINCREMENT, op TEXT NOT NULL, ref TEXT, doc_version INTEGER, payload TEXT, at INTEGER NOT NULL, sent_at INTEGER);
CREATE TABLE IF NOT EXISTS sync_inbox_deduplication (key TEXT PRIMARY KEY, at INTEGER NOT NULL);
CREATE TABLE IF NOT EXISTS sync_checkpoints (name TEXT PRIMARY KEY, value TEXT, at INTEGER NOT NULL);
CREATE TABLE IF NOT EXISTS backup_manifest (
  file TEXT PRIMARY KEY, at INTEGER NOT NULL, doc_version INTEGER, bytes INTEGER, sha256 TEXT, bills INTEGER, verified INTEGER NOT NULL DEFAULT 0, note TEXT);
"""

# ---------------------------------------------------------------------------------------------------------
# Mapping of the app's data object to tables
# ---------------------------------------------------------------------------------------------------------
MONEY = lambda v: int((Decimal(str(v)) * 100).quantize(Decimal('1'), rounding=ROUND_HALF_UP))


class Child:
    def __init__(self, key, table, fk, cols):
        self.key, self.table, self.fk, self.cols = key, table, fk, cols


class Spec:
    def __init__(self, key, table, cols, children=(), proj=None):
        self.key, self.table, self.cols, self.children, self.proj = key, table, cols, list(children), proj or {}


def _bill_proj(r):
    tot = r.get('total')
    return {'total_p': MONEY(tot) if _num(tot) else None, 'is_cancelled': 1 if r.get('cancelled') else 0}


def _num(v):
    return isinstance(v, (int, float)) and not isinstance(v, bool)


SPECS = [
    Spec('bills', 'bills', ['no', 'kot', 'date', 'time', 'table', 'channel', 'mode', 'sub', 'disc', 'tax', 'taxable', 'total', 'round', 'cust', 'phone', 'idemKey', 'mv', 'imported', 'cancelled'],
         [Child('items', 'bill_items', 'bill_id', ['mid', 'name', 'price', 'qty']),
          Child('pays', 'bill_payments', 'bill_id', ['mode', 'amt']),
          Child('used', 'bill_used', 'bill_id', ['sid', 'qty'])], {'bills': _bill_proj}),
    Spec('kots', 'kots', ['no', 'date', 'time', 'table', 'channel', 'status'],
         [Child('items', 'kot_items', 'kot_id', ['mid', 'name', 'qty'])]),
    Spec('menu', 'menu_items', ['name', 'cat', 'price'], [Child('recipe', 'recipe_ingredients', 'menu_id', ['sid', 'qty'])]),
    Spec('stock', 'stock_items', ['name', 'unit', 'qty', 'rate', 'cat']),
    Spec('moves', 'stock_move_records', ['sid', 'qty', 'type', 'date', 'time']),
    Spec('txns', 'vouchers', ['type', 'date', 'time', 'head', 'party', 'amount', 'mode', 'sid', 'qty', 'mv']),
    Spec('staff', 'staff', ['name', 'role', 'access']),
    Spec('audit', 'audit_logs', ['at', 'date', 'action', 'user', 'amount', 'ref']),
    Spec('cnotes', 'credit_notes', ['no', 'billId', 'date', 'total']),
    Spec('orders', 'purchase_orders', ['party', 'date', 'status']),
]
SPEC_BY_KEY = {s.key: s for s in SPECS}
# Maps with their own table: key -> (table, key column)
MAP_TABLES = {'kaccha': ('table_orders', 'tbl'), 'cash': ('cash_drawer_sessions', 'date'), 'salarySheets': ('salary_records', 'month')}
CONFIG_KEYS = ('settings', 'auth', 'secure', 'subscription', 'saas')
GUARDED_FOR_DELETE_LOG = ('bills',)


def _scalar(v):
    return isinstance(v, (str, int, float)) and not isinstance(v, bool)


def _dump(v):
    return json.dumps(v, ensure_ascii=False, separators=(',', ':'))


def split_record(cols, rec):
    """(column values, extra dict): known scalar fields move to columns with their exact value; the rest stays."""
    vals, extra = [], {}
    for c in cols:
        v = rec.get(c, None) if c in rec else None
        vals.append(v if c in rec and _scalar(v) else None)
    for k, v in rec.items():
        if k in cols and _scalar(v):
            continue
        extra[k] = v
    return vals, extra


def join_record(cols, vals, extra_text):
    rec = json.loads(extra_text) if extra_text and extra_text != '{}' else {}
    for c, v in zip(cols, vals):
        if v is not None:
            rec[c] = v
    return rec


class StoreError(Exception):
    pass


class SqliteDoc:
    """The SQLite database of one hotel. Thread-safe: one write at a time (`self.wlock`), readers use WAL."""

    def __init__(self, path, hotel_id=None, create=False):
        self.path = path
        self.wlock = threading.RLock()
        self._local = threading.local()
        exists = os.path.exists(path)
        if not exists and not create:
            raise StoreError(f'database not found: {path}')
        con = self.con()
        if exists:
            ok = con.execute('PRAGMA quick_check').fetchone()[0]
            if ok != 'ok':
                raise StoreError(f'database failed its integrity check: {ok}')
        con.executescript(SCHEMA)
        cur = self.meta('schema_version')
        if cur is None:
            with self.tx() as c:
                c.execute("INSERT OR REPLACE INTO meta VALUES ('schema_version', ?)", (str(SCHEMA_VERSION),))
                c.execute('INSERT OR IGNORE INTO database_migrations VALUES (?, ?, ?)', (SCHEMA_VERSION, 'initial relational schema', int(time.time() * 1000)))
        elif int(cur) > SCHEMA_VERSION:
            raise StoreError(f'database schema {cur} is newer than this program ({SCHEMA_VERSION})')
        hid = self.meta('hotel_id')
        if hotel_id and hid and hid != hotel_id:
            raise StoreError(f'this database belongs to hotel {hid}, not {hotel_id}')

    # ---- connections ----
    def con(self):
        c = getattr(self._local, 'con', None)
        if c is None:
            c = sqlite3.connect(self.path, timeout=30, isolation_level=None, check_same_thread=False)
            c.execute('PRAGMA journal_mode=WAL')
            c.execute('PRAGMA synchronous=FULL')        # financial records: a commit is on disk before we answer
            c.execute('PRAGMA foreign_keys=ON')
            c.execute('PRAGMA busy_timeout=30000')
            c.execute('PRAGMA wal_autocheckpoint=1000')
            self._local.con = c
        return c

    class _Tx:
        def __init__(self, doc):
            self.doc = doc

        def __enter__(self):
            self.doc.wlock.acquire()
            self.c = self.doc.con()
            self.c.execute('BEGIN IMMEDIATE')
            return self.c

        def __exit__(self, et, ev, tb):
            try:
                self.c.execute('COMMIT' if et is None else 'ROLLBACK')
            finally:
                self.doc.wlock.release()
            return False

    def tx(self):
        return SqliteDoc._Tx(self)

    def meta(self, k):
        r = self.con().execute('SELECT v FROM meta WHERE k = ?', (k,)).fetchone()
        return r[0] if r else None

    def close(self):
        c = getattr(self._local, 'con', None)
        if c is not None:
            c.close()
            self._local.con = None

    # ---- import (one record) ----
    def _put_record(self, c, spec, rec, ordn):
        cols = spec.cols
        vals, extra = split_record(cols, rec)
        rid = rec.get('id')
        arrays = []
        children = []
        for ch in spec.children:
            if ch.key in rec and isinstance(rec[ch.key], list) and all(isinstance(x, dict) for x in rec[ch.key]):
                arrays.append(ch.key)
                extra.pop(ch.key, None)
                children.append((ch, rec[ch.key]))
        names = ['id', 'ord'] + cols + ['extra']
        args = [rid, ordn] + vals + [_dump(extra)]
        has_arrays = spec.table in ('bills', 'kots', 'menu_items')
        if has_arrays:
            names.append('arrays'); args.append(','.join(arrays))
        if spec.table == 'bills':
            p = _bill_proj(rec)
            names += ['total_p', 'is_cancelled']; args += [p['total_p'], p['is_cancelled']]
        if spec.table == 'vouchers':
            inv = rec.get('inv') if isinstance(rec.get('inv'), dict) else {}
            names += ['amount_p', 'inv_id']; args += [MONEY(rec['amount']) if _num(rec.get('amount')) else None, inv.get('id')]
        if spec.table == 'credit_notes':
            names.append('total_p'); args.append(MONEY(rec['total']) if _num(rec.get('total')) else None)
        q = ','.join('"%s"' % n for n in names)
        c.execute(f'INSERT OR REPLACE INTO {spec.table} ({q}) VALUES ({",".join("?" * len(names))})', args)
        for ch in spec.children:
            c.execute(f'DELETE FROM {ch.table} WHERE {ch.fk} = ?', (rid,))
        for ch, rows in children:
            extra_cols = ['synthetic', 'amount_p'] if ch.table == 'bill_payments' else []
            for i, x in enumerate(rows):
                v, ex = split_record(ch.cols, x)
                more = [0, MONEY(x['amt']) if _num(x.get('amt')) else None] if extra_cols else []
                cn = ','.join([ch.fk, 'line'] + ['"%s"' % k for k in ch.cols] + extra_cols + ['extra'])
                c.execute(f'INSERT INTO {ch.table} ({cn}) VALUES ({",".join("?" * (len(ch.cols) + 3 + len(extra_cols)))})', [rid, i] + v + more + [_dump(ex)])
        if spec.table == 'bills':
            self._bill_side(c, rec)
        elif spec.table == 'vouchers':
            self._voucher_side(c, rec)
        elif spec.table == 'stock_move_records':
            self._move_side(c, rec)

    def _bill_side(self, c, b):
        bid = b['id']
        # Same rule as the app's payParts(): split tenders only for a Split bill that has them, otherwise one
        # synthetic line (bill mode, total) so payments can always be summed by mode
        if not (b.get('mode') == 'Split' and isinstance(b.get('pays'), list) and b.get('pays')):
            c.execute('DELETE FROM bill_payments WHERE bill_id = ? AND synthetic = 1', (bid,))
            if _num(b.get('total')):
                c.execute('INSERT INTO bill_payments (bill_id, line, mode, amt, amount_p, synthetic) VALUES (?, -1, ?, ?, ?, 1)',
                          (bid, b.get('mode') or 'Cash', b.get('total'), MONEY(b['total'])))
        # Stock ledger: exactly the movements the app's stockMoves() derives from this bill
        c.execute("DELETE FROM stock_movements WHERE source IN ('sale', 'cancel') AND ref = ?", (bid,))
        if b.get('mv'):
            seen = set()
            for u in b.get('used') or []:
                if not isinstance(u, dict):
                    continue
                sid = str(u.get('sid')) if u.get('sid') is not None else ''
                q = float(u.get('qty') or 0)
                mid = 's-' + bid + '-' + sid
                if mid in seen:
                    mid += '#' + str(len(seen))
                seen.add(mid)
                c.execute("INSERT INTO stock_movements VALUES (?, 'sale', ?, ?, ?, 'sale', ?, ?)", (mid, bid, sid, -q, b.get('date'), b.get('time') or ''))
                if b.get('cancelled'):
                    c.execute("INSERT INTO stock_movements VALUES (?, 'cancel', ?, ?, ?, 'cancel', ?, ?)", ('x' + mid[1:], bid, sid, q, b.get('date'), b.get('time') or ''))
        if b.get('cancelled'):
            c.execute('INSERT OR IGNORE INTO bill_cancellations VALUES (?, ?, ?)', (bid, str(b.get('cancelledBy') or ''), int(time.time() * 1000)))
        else:
            c.execute('DELETE FROM bill_cancellations WHERE bill_id = ?', (bid,))

    def _voucher_side(self, c, t):
        tid = t['id']
        c.execute("DELETE FROM stock_movements WHERE source = 'purchase' AND ref = ?", (tid,))
        if t.get('type') == 'Purchase' and t.get('mv') and t.get('sid') and _num(t.get('qty')) and t.get('qty'):
            c.execute("INSERT INTO stock_movements VALUES (?, 'purchase', ?, ?, ?, 'purchase', ?, ?)", ('p-' + tid, tid, str(t['sid']), float(t['qty']), t.get('date'), t.get('time') or ''))
        inv = t.get('inv')
        if t.get('type') == 'Purchase' and isinstance(inv, dict) and inv.get('id'):
            c.execute('INSERT OR REPLACE INTO purchases VALUES (?, ?, ?, ?, ?, ?, ?)', (inv['id'], str(inv.get('no') or ''), t.get('party'), t.get('date'),
                      MONEY(inv['total']) if _num(inv.get('total')) else None, MONEY(inv['paid']) if _num(inv.get('paid')) else None, inv.get('n')))

    def _move_side(self, c, m):
        c.execute("DELETE FROM stock_movements WHERE source = 'move' AND ref = ?", (m['id'],))
        if m.get('sid') is not None:
            c.execute("INSERT INTO stock_movements VALUES (?, 'move', ?, ?, ?, ?, ?, ?)",
                      ('m-' + m['id'], m['id'], str(m['sid']), float(m.get('qty') or 0), m.get('type'), m.get('date'), m.get('time') or ''))

    def _del_record(self, c, spec, rid):
        for ch in spec.children:
            c.execute(f'DELETE FROM {ch.table} WHERE {ch.fk} = ?', (rid,))
        if spec.table == 'bills':
            c.execute("DELETE FROM stock_movements WHERE source IN ('sale', 'cancel') AND ref = ?", (rid,))
            c.execute('DELETE FROM bill_cancellations WHERE bill_id = ?', (rid,))
        elif spec.table == 'vouchers':
            c.execute("DELETE FROM stock_movements WHERE source = 'purchase' AND ref = ?", (rid,))
        elif spec.table == 'stock_move_records':
            c.execute("DELETE FROM stock_movements WHERE source = 'move' AND ref = ?", (rid,))
        c.execute(f'DELETE FROM {spec.table} WHERE id = ?', (rid,))

    # ---- whole document in / out ----
    @staticmethod
    def kind_of(k, v):
        """Where a top-level key of the data object lives."""
        spec = SPEC_BY_KEY.get(k)
        if spec and isinstance(v, list) and all(isinstance(x, dict) and isinstance(x.get('id'), str) and x.get('id') for x in v) \
                and len({x['id'] for x in v}) == len(v):
            return 'spec'
        if k == 'seq' and isinstance(v, dict):
            return 'seq'
        if k in MAP_TABLES and isinstance(v, dict):
            return 'maptable'
        if k == 'att' and isinstance(v, dict) and all(isinstance(x, dict) for x in v.values()):
            return 'att'
        if isinstance(v, list) and k not in CONFIG_KEYS:
            return 'extlist'
        if isinstance(v, dict) and k not in CONFIG_KEYS:
            return 'kvmap'
        return 'setting'

    def _clear_key(self, c, k, kind):
        if kind == 'spec':
            spec = SPEC_BY_KEY[k]
            for rid, in c.execute(f'SELECT id FROM {spec.table}').fetchall():
                self._del_record(c, spec, rid)
        elif kind == 'seq':
            c.execute('DELETE FROM sequences')
        elif kind == 'maptable':
            c.execute(f'DELETE FROM {MAP_TABLES[k][0]}')
        elif kind == 'att':
            c.execute('DELETE FROM attendance')
        elif kind == 'extlist':
            c.execute('DELETE FROM ext_records WHERE list = ?', (k,))
        elif kind == 'kvmap':
            c.execute('DELETE FROM kv_maps WHERE map = ?', (k,))
        else:
            c.execute('DELETE FROM hotel_settings WHERE k = ?', (k,))

    def commit_document(self, c, old, new, version, saved_at):
        """Write the difference between two data objects inside the caller's transaction (`c`).
        `old` = the last committed object ({} for a fresh import). Returns the number of top-level keys written."""
        kinds = json.loads(self.meta('doc_kinds') or '{}') if old else {}
        changed = 0
        for k, v in new.items():
            nk = self.kind_of(k, v)
            ok = kinds.get(k)
            if ok == nk and k in old and old[k] == v:
                continue
            if ok is not None and ok != nk:
                self._clear_key(c, k, ok)
                ov = None
            else:
                ov = old.get(k) if ok == nk else None
            self._put_key(c, k, nk, v, ov)
            kinds[k] = nk
            changed += 1
        for k in list(old.keys()):
            if k not in new and k in kinds:
                self._clear_key(c, k, kinds.pop(k))
                changed += 1
        keys = list(new.keys())
        if not old or list(old.keys()) != keys or changed:
            c.execute("INSERT OR REPLACE INTO meta VALUES ('doc_keys', ?)", (_dump(keys),))
            c.execute("INSERT OR REPLACE INTO meta VALUES ('doc_kinds', ?)", (_dump(kinds),))
        c.execute("INSERT OR REPLACE INTO meta VALUES ('doc_version', ?)", (str(int(version)),))
        c.execute("INSERT OR REPLACE INTO meta VALUES ('saved_at', ?)", (str(int(saved_at or 0)),))
        return changed

    def import_document(self, c, doc, version=1, saved_at=0, hotel_id=None):
        """Fresh import (migration), inside the caller's transaction."""
        self.commit_document(c, {}, doc, version, saved_at)
        hid = hotel_id or _hotel_of(doc)
        if hid:
            c.execute("INSERT OR IGNORE INTO meta VALUES ('hotel_id', ?)", (hid,))
            c.execute('INSERT OR IGNORE INTO hotels VALUES (?, ?)', (hid, int(time.time() * 1000)))

    def _put_key(self, c, k, kind, v, old):
        if kind == 'spec':
            self._put_list(c, SPEC_BY_KEY[k], v, old if isinstance(old, list) else [])
        elif kind == 'seq':
            c.execute('DELETE FROM sequences')
            for i, (n, x) in enumerate(v.items()):
                num = _scalar(x) and not isinstance(x, str)
                c.execute('INSERT INTO sequences VALUES (?, ?, ?, ?)', (n, x if num else None, None if num else _dump(x), i))
        elif kind == 'maptable':
            table, kc = MAP_TABLES[k]
            self._put_map_rows(c, table, kc, v, old if isinstance(old, dict) else {})
        elif kind == 'att':
            self._put_att(c, v, old if isinstance(old, dict) else {})
        elif kind == 'extlist':
            self._put_ext_list(c, k, v, old if isinstance(old, list) else None)
        elif kind == 'kvmap':
            self._put_kv_map(c, k, v, old if isinstance(old, dict) else {})
        else:
            c.execute('INSERT OR REPLACE INTO hotel_settings VALUES (?, ?)', (k, _dump(v)))

    def _put_list(self, c, spec, new, old):
        om = {x['id']: (i, x) for i, x in enumerate(old) if isinstance(x, dict) and x.get('id')}
        nids = set()
        now = int(time.time() * 1000)
        for i, x in enumerate(new):
            rid = x['id']
            nids.add(rid)
            o = om.get(rid)
            if o is None:
                self._put_record(c, spec, x, i)
            elif o[1] != x:
                if spec.table == 'bills':
                    c.execute('INSERT INTO bill_modifications (bill_id, action, at, old, new) VALUES (?, ?, ?, ?, ?)',
                              (rid, 'cancel' if x.get('cancelled') and not o[1].get('cancelled') else 'edit', now, _dump(o[1]), _dump(x)))
                if spec.table == 'kots' and o[1].get('status') != x.get('status'):
                    c.execute('INSERT INTO kot_status_history (kot_id, old_status, new_status, at) VALUES (?, ?, ?, ?)', (rid, o[1].get('status'), x.get('status'), now))
                self._put_record(c, spec, x, i)
            elif o[0] != i:
                c.execute(f'UPDATE {spec.table} SET ord = ? WHERE id = ?', (i, rid))
        for rid, (i, x) in om.items():
            if rid not in nids:
                if spec.table == 'bills':
                    c.execute('INSERT INTO bill_modifications (bill_id, action, at, old, new) VALUES (?, ?, ?, ?, NULL)', (rid, 'delete', now, _dump(x)))
                self._del_record(c, spec, rid)

    def _put_map_rows(self, c, table, kc, new, old):
        pos = {k: i for i, k in enumerate(old)}
        for i, (k, v) in enumerate(new.items()):
            if k not in old or old[k] != v or pos[k] != i:
                c.execute(f'INSERT OR REPLACE INTO {table} ({kc}, ord, data) VALUES (?, ?, ?)', (k, i, _dump(v)))
        for k in old:
            if k not in new:
                c.execute(f'DELETE FROM {table} WHERE {kc} = ?', (k,))

    def _put_att(self, c, new, old):
        pos = {k: i for i, k in enumerate(old)}
        for di, (d, m) in enumerate(new.items()):
            if d in old and old[d] == m and pos[d] == di:
                continue
            c.execute('DELETE FROM attendance WHERE date = ?', (d,))
            if not m:
                c.execute("INSERT INTO attendance VALUES (?, '', ?, '__empty__')", (d, di * 100000))
            for si, (sk, v) in enumerate(m.items()):
                c.execute('INSERT INTO attendance VALUES (?, ?, ?, ?)', (d, sk, di * 100000 + si, _dump(v)))
        for d in old:
            if d not in new:
                c.execute('DELETE FROM attendance WHERE date = ?', (d,))

    def _put_ext_list(self, c, k, new, old):
        ids_ok = all(isinstance(x, dict) and isinstance(x.get('id'), str) and x.get('id') for x in new) and len({x['id'] for x in new}) == len(new)
        old_ok = old is not None and all(isinstance(x, dict) and isinstance(x.get('id'), str) for x in old)
        if not ids_ok or not old_ok:
            c.execute('DELETE FROM ext_records WHERE list = ?', (k,))
            for i, x in enumerate(new):
                rid = x['id'] if ids_ok else '#%d' % i
                c.execute('INSERT INTO ext_records VALUES (?, ?, ?, ?, ?)', (k, rid, i, 0 if ids_ok else 1, _dump(x)))
            return
        om = {x['id']: (i, x) for i, x in enumerate(old)}
        for i, x in enumerate(new):
            o = om.get(x['id'])
            if o is None or o[1] != x or o[0] != i:
                c.execute('INSERT OR REPLACE INTO ext_records VALUES (?, ?, ?, 0, ?)', (k, x['id'], i, _dump(x)))
        nids = {x['id'] for x in new}
        for rid in om:
            if rid not in nids:
                c.execute('DELETE FROM ext_records WHERE list = ? AND id = ?', (k, rid))

    def _put_kv_map(self, c, name, new, old):
        if not old or list(old.keys()) != list(new.keys()):
            c.execute('DELETE FROM kv_maps WHERE map = ?', (name,))
            for i, (k, v) in enumerate(new.items()):
                c.execute('INSERT INTO kv_maps VALUES (?, ?, ?, ?)', (name, k, i, _dump(v)))
            return
        for i, (k, v) in enumerate(new.items()):
            if old.get(k) != v:
                c.execute('INSERT OR REPLACE INTO kv_maps VALUES (?, ?, ?, ?)', (name, k, i, _dump(v)))

    def export_document(self):
        c = self.con()
        keys = json.loads(self.meta('doc_keys') or '[]')
        kinds = json.loads(self.meta('doc_kinds') or '{}')
        out = {}
        for k in keys:
            kind = kinds.get(k, 'setting')
            if kind == 'spec':
                out[k] = self._export_list(c, SPEC_BY_KEY[k])
            elif kind == 'seq':
                out[k] = {n: (json.loads(t) if t is not None else v) for n, v, t in c.execute('SELECT name, n, t FROM sequences ORDER BY ord')}
            elif kind == 'maptable':
                table, kc = MAP_TABLES[k]
                out[k] = {r[0]: json.loads(r[1]) for r in c.execute(f'SELECT {kc}, data FROM {table} ORDER BY ord')}
            elif kind == 'att':
                att = {}
                for d, sk, v in c.execute('SELECT date, staff_key, v FROM attendance ORDER BY ord'):
                    m = att.setdefault(d, {})
                    if v != '__empty__':
                        m[sk] = json.loads(v)
                out[k] = att
            elif kind == 'extlist':
                out[k] = [json.loads(r[0]) for r in c.execute('SELECT data FROM ext_records WHERE list = ? ORDER BY ord', (k,))]
            elif kind == 'kvmap':
                out[k] = {r[0]: json.loads(r[1]) for r in c.execute('SELECT k, v FROM kv_maps WHERE map = ? ORDER BY ord', (k,))}
            else:
                r = c.execute('SELECT v FROM hotel_settings WHERE k = ?', (k,)).fetchone()
                out[k] = json.loads(r[0]) if r else None
        return out

    def _export_list(self, c, spec):
        cols = spec.cols
        has_arrays = spec.table in ('bills', 'kots', 'menu_items')
        sel = ','.join(['id'] + ['"%s"' % x for x in cols] + ['extra'] + (['arrays'] if has_arrays else []))
        rows = c.execute(f'SELECT {sel} FROM {spec.table} ORDER BY ord').fetchall()
        kids = {}
        for ch in spec.children:
            m = {}
            for r in c.execute(f'SELECT {ch.fk}, {",".join(chr(34) + x + chr(34) for x in ch.cols)}, extra' + (', synthetic' if ch.table == 'bill_payments' else '') + f' FROM {ch.table} ORDER BY {ch.fk}, line'):
                if ch.table == 'bill_payments' and r[-1]:
                    continue
                m.setdefault(r[0], []).append(join_record(ch.cols, r[1:1 + len(ch.cols)], r[1 + len(ch.cols)]))
            kids[ch.key] = m
        out = []
        for r in rows:
            rid = r[0]
            rec = join_record(cols, r[1:1 + len(cols)], r[1 + len(cols)])
            rec['id'] = rid
            arrays = (r[2 + len(cols)] or '').split(',') if has_arrays else []
            for ch in spec.children:
                if ch.key in arrays:
                    rec[ch.key] = kids[ch.key].get(rid, [])
            out.append(rec)
        return out

    # ---- stock ----
    def stock_balances(self, aliases=None):
        """Quantity per stock item from the ledger, with merged items folded into their target (the app's sidOf)."""
        aliases = aliases or {}

        def root(s):
            n = 0
            while s in aliases and n < 6:
                s, n = aliases[s], n + 1
            return s
        tot = {}
        for sid, q in self.con().execute('SELECT sid, qty FROM stock_balances'):
            r = root(sid)
            tot[r] = tot.get(r, 0) + q
        return tot

    def rebuild_balances(self, c):
        c.execute('DELETE FROM stock_balances')
        c.execute('INSERT INTO stock_balances (sid, qty) SELECT sid, SUM(qty) FROM stock_movements GROUP BY sid')

    # ---- backups ----
    def backup_to(self, dest_gz, doc_version=None, keep=60, verify=True):
        """Online backup (SQLite backup API: consistent while transactions run), gzip, verify, record in the manifest."""
        tmp = dest_gz + '.part.sqlite'
        for p in (tmp, tmp + '-wal', tmp + '-shm'):
            if os.path.exists(p):
                os.remove(p)
        t0 = time.time()
        dst = sqlite3.connect(tmp)
        with self.wlock:
            self.con().backup(dst)
        dst.execute('PRAGMA journal_mode=DELETE')
        dst.close()
        h = hashlib.sha256()
        with open(tmp, 'rb') as f, gzip.open(dest_gz + '.part', 'wb', compresslevel=6) as g:
            for chunk in iter(lambda: f.read(1 << 20), b''):
                h.update(chunk)
                g.write(chunk)
        bills = None
        ok = 0
        if verify:
            v = sqlite3.connect(tmp)
            ok = 1 if v.execute('PRAGMA integrity_check').fetchone()[0] == 'ok' else 0
            bills = v.execute('SELECT COUNT(*) FROM bills').fetchone()[0]
            v.close()
        os.replace(dest_gz + '.part', dest_gz)
        os.remove(tmp)
        size = os.path.getsize(dest_gz)
        with self.tx() as c:
            c.execute('INSERT OR REPLACE INTO backup_manifest VALUES (?, ?, ?, ?, ?, ?, ?, ?)',
                      (os.path.basename(dest_gz), int(time.time() * 1000), doc_version, size, h.hexdigest(), bills, ok, f'{time.time() - t0:.2f}s'))
        if keep:
            d = os.path.dirname(dest_gz)
            files = sorted(x for x in os.listdir(d) if x.startswith('setu-') and x.endswith('.sqlite.gz'))
            for old in files[:-keep]:
                os.remove(os.path.join(d, old))
        return {'file': dest_gz, 'bytes': size, 'sha256': h.hexdigest(), 'bills': bills, 'verified': bool(ok), 'seconds': round(time.time() - t0, 2)}


def restore_backup(backup_gz, dest_db):
    """Decompress a backup next to `dest_db`, check it, then move it into place (old file kept aside)."""
    tmp = dest_db + '.restore'
    with gzip.open(backup_gz, 'rb') as g, open(tmp, 'wb') as f:
        shutil.copyfileobj(g, f)
        f.flush()
        os.fsync(f.fileno())
    con = sqlite3.connect(tmp)
    ok = con.execute('PRAGMA integrity_check').fetchone()[0]
    bills = con.execute('SELECT COUNT(*) FROM bills').fetchone()[0]
    con.close()
    if ok != 'ok':
        os.remove(tmp)
        raise StoreError('backup failed its integrity check: ' + ok)
    if os.path.exists(dest_db):
        aside = dest_db + '.before-restore-' + time.strftime('%Y%m%d-%H%M%S')
        os.replace(dest_db, aside)
        for ext in ('-wal', '-shm'):
            if os.path.exists(dest_db + ext):
                os.replace(dest_db + ext, aside + ext)
    os.replace(tmp, dest_db)
    return {'bills': bills, 'integrity': ok}


def _hotel_of(doc):
    for part in ('settings', 'auth'):
        v = (doc.get(part) or {}).get('hotelId') if isinstance(doc.get(part), dict) else None
        if v:
            return str(v)
    return None


def canonical_hash(doc):
    """sha256 of the canonical form, built record by record (no single huge string for big databases)."""
    h = hashlib.sha256()

    def feed(v):
        if isinstance(v, dict):
            h.update(b'{')
            for k in sorted(v):
                h.update(json.dumps(k, ensure_ascii=False).encode() + b':')
                feed(v[k])
                h.update(b',')
            h.update(b'}')
        elif isinstance(v, list):
            h.update(b'[')
            for x in v:
                feed(x) if isinstance(x, (dict, list)) else h.update(json.dumps(x, ensure_ascii=False).encode())
                h.update(b',')
            h.update(b']')
        else:
            h.update(json.dumps(v, ensure_ascii=False).encode())
    for k in sorted(doc):
        h.update(json.dumps(k, ensure_ascii=False).encode() + b'=')
        feed(doc[k])
    return h.hexdigest()


def canonical(doc):
    """Text used to prove two data objects are identical (key order inside objects does not matter)."""
    return json.dumps(doc, ensure_ascii=False, sort_keys=True, separators=(',', ':'))


def read_flag(data_dir):
    try:
        with open(os.path.join(data_dir, FLAG_FILE), 'r', encoding='utf-8') as f:
            return json.load(f)
    except Exception:
        return {}


def write_flag(data_dir, obj):
    p = os.path.join(data_dir, FLAG_FILE)
    with open(p + '.tmp', 'w', encoding='utf-8') as f:
        json.dump(obj, f, indent=1)
        f.flush()
        os.fsync(f.fileno())
    os.replace(p + '.tmp', p)
