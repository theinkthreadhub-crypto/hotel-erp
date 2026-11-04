"""Builds the CSV deliverables from the benchmark output (bench.cjs / scale.cjs JSON files).

    python3 tools/db-benchmark/report.py <benchOutDir> <docsOutDir>

Everything marked "measured" comes straight from those files. Projections are arithmetic on the
measured bytes per day and are labelled "estimate".
"""
import csv, json, os, sys, glob

OUT, DOCS = sys.argv[1], sys.argv[2]
os.makedirs(DOCS, exist_ok=True)
MB = 1048576
USD_INR = 95.0   # assumption, see Hosting-Cost-Comparison notes


def load(p):
    with open(p) as f:
        return json.load(f)


def pool(s):
    return load(os.path.join(OUT, 'data-' + s, 'setu-db.json'))['data']


def jb(x):
    return len(json.dumps(x, ensure_ascii=False, separators=(',', ':')).encode())


scen = {s: load(os.path.join(OUT, s + '.json')) for s in 'ABC' if os.path.exists(os.path.join(OUT, s + '.json'))}

# ---------- Module-Storage-Breakdown.csv (measured, real records from the app's own code) ----------
MODULES = [
    ('POS & Billing', 'bills', 'Sales bills incl. items, taxes, discounts, split tenders, cancel flags, stock used'),
    ('KOT & Kitchen', 'kots', 'Kitchen tickets (app keeps only the last 7 days)'),
    ('Purchases & Supplier', 'txns:Purchase', 'One row per purchase line with invoice header copy'),
    ('Supplier payments', 'txns:Supplier Payment', 'Part payments on credit purchases'),
    ('Expenses / Accounting', 'txns:Expense', 'Expense vouchers'),
    ('Inventory movements', 'moves', 'Opening stock, waste, issues, returns, counts (sales are derived from bills, not stored twice)'),
    ('Audit trail', 'audit', 'Manager actions, cancellations, purchases (capped at 20,000 entries)'),
    ('Staff attendance', 'att', 'One map per day'),
    ('Running tables', 'kaccha', 'Open table orders (cleared when billed)'),
    ('Masters: menu + recipes', 'menu', '120 dishes, 2-4 ingredient recipe lines each'),
    ('Masters: stock items', 'stock', '60 raw materials'),
    ('Masters: staff', 'staff', '12 employees'),
    ('Settings + licence', 'settings', 'Restaurant settings'),
]
rows = []
for s, r in scen.items():
    d = pool(s)
    days = r['days']
    for name, key, what in MODULES:
        if key.startswith('txns:'):
            t = key.split(':', 1)[1]
            recs = [x for x in d.get('txns', []) if (x.get('head') == 'Supplier Payment') == (t == 'Supplier Payment') and x.get('type') == ('Expense' if t == 'Supplier Payment' else t)]
        else:
            v = d.get(key)
            recs = v if isinstance(v, list) else [v] if key == 'settings' else list((v or {}).values()) if isinstance(v, dict) else []
        n = len(recs)
        b = sum(jb(x) for x in recs)
        per_day = b / days if key in ('bills', 'audit', 'att') or key.startswith('txns') else ''
        if key == 'moves':
            grow = [x for x in recs if x.get('type') != 'open']
            per_day = sum(jb(x) for x in grow) / days
        if key == 'kots':
            per_day = 0   # bounded: 7-day window
        rows.append({'scenario': s, 'bills_per_day': r['billsPerDay'], 'days_simulated': days, 'module': name, 'data_key': key,
                     'records': n, 'json_bytes': b, 'avg_bytes_per_record': round(b / n) if n else 0,
                     'growth_bytes_per_day': round(per_day) if per_day != '' else 'fixed', 'share_of_database_pct': '',
                     'source': 'measured (app functions, synthetic data)', 'notes': what})
    tot = sum(x['json_bytes'] for x in rows if x['scenario'] == s)
    for x in rows:
        if x['scenario'] == s:
            x['share_of_database_pct'] = round(100 * x['json_bytes'] / tot, 1) if tot else 0
with open(os.path.join(DOCS, 'Module-Storage-Breakdown.csv'), 'w', newline='') as f:
    w = csv.DictWriter(f, fieldnames=list(rows[0].keys()))
    w.writeheader(); w.writerows(rows)

# ---------- per-day growth (measured) used for projections ----------
growth = {}
for s, r in scen.items():
    f0, f1 = r['daysOut'][0], r['daysOut'][-1]
    span = len(r['daysOut']) - 1
    # whole database JSON growth per day, excluding KOTs (bounded) — measured between first and last day
    k0 = f0['keyBytes']; k1 = f1['keyBytes']
    grow = sum(k1[k] - k0.get(k, 0) for k in k1 if k not in ('__total', 'kots', 'kaccha', 'menu', 'stock', 'staff', 'settings'))
    fileRatio = f1['fileBytes'] / k1['__total']
    kotSteady = k1['kots'] / max(1, f1['counts']['kots']) * r['billsPerDay'] * 8
    growth[s] = {'bpd': r['billsPerDay'], 'jsonPerDay': grow / span, 'filePerDay': grow / span * fileRatio, 'fileRatio': fileRatio,
                 'base': (k1['menu'] + k1['stock'] + k1['staff'] + k1['settings']) * fileRatio + kotSteady * fileRatio}

json.dump(growth, open(os.path.join(DOCS, 'growth.json'), 'w'), indent=1)

# ---------- Restaurant-Database-Capacity-Projection.csv (estimates from measured growth) ----------
# Profiles: A = busy cafe 200 bills/day, B = 500, C = 1000. Portfolio "typical" = A.
GZ = 0.11        # measured gzip ratio, overwritten below when scale results exist
scale = {os.path.basename(p)[6:-5]: load(p) for p in glob.glob(os.path.join(OUT, 'scale-*.json')) if 'smoke' not in p}
gz = [v['gzipBytes'] / v['fileBytes'] for v in scale.values() if v.get('gzipBytes') and v.get('fileBytes')]
if gz:
    GZ = sum(gz) / len(gz)
proj = []
for s, g in growth.items():
    for years in (1, 3, 5, 10):
        live = g['base'] + g['filePerDay'] * 365 * years
        for n in (1, 10, 50, 100, 500, 1000):
            for case, mult in (('base', 1.0), ('high-growth (+25%/yr volume)', None), ('safety margin (x1.5 of base)', 1.5)):
                if mult is None:
                    days = sum(365 * 1.25 ** y for y in range(years))
                    l = g['base'] + g['filePerDay'] * days
                else:
                    l = live * mult
                # local counter PC: live file + 60 daily backup copies of (up to) the live file
                local_pc = l + 60 * l
                # cloud: live data + 30 compressed end-of-day snapshots
                cloud = l + 30 * l * GZ
                proj.append({'profile': s, 'bills_per_day': g['bpd'], 'restaurants': n, 'years': years, 'case': case,
                             'live_db_per_restaurant_MB': round(l / MB, 1), 'live_db_total_GB': round(n * l / 1024 ** 3, 2),
                             'cloud_incl_30_gz_snapshots_total_GB': round(n * cloud / 1024 ** 3, 2),
                             'counter_pc_incl_60_backups_per_restaurant_GB': round(local_pc / 1024 ** 3, 2),
                             'fits_one_durable_object_10GB': l < 10 * 1024 ** 3,
                             'basis': 'estimate from measured bytes/day (scenario %s)' % s})
with open(os.path.join(DOCS, 'Restaurant-Database-Capacity-Projection.csv'), 'w', newline='') as f:
    w = csv.DictWriter(f, fieldnames=list(proj[0].keys()))
    w.writeheader(); w.writerows(proj)
print(json.dumps(growth, indent=1))
print('gzip ratio', GZ)

# ---------- Hosting-Cost-Comparison.csv (estimate) ----------
# Prices: official pages / docs as found on 2026-11-04 (see Hosting-Cost-Comparison notes in the report).
# Workload model per restaurant (profile A, 200 bills/day, measured): data GB after Y years; writes per day.
GB = 1024 ** 3
gA = growth.get('A') or next(iter(growth.values()))
def live_gb(years, g=gA):
    return (g['base'] + g['jsonPerDay'] * 365 * years) / GB
bills_day = gA['bpd']
cost_rows = []
def add(provider, n, years, usd, notes, kind):
    cost_rows.append({'provider': provider, 'architecture': kind, 'restaurants': n, 'data_years': years,
                      'total_data_GB': round(live_gb(years) * n, 2), 'monthly_USD_total': round(usd, 2),
                      'monthly_INR_total': round(usd * USD_INR), 'monthly_INR_per_restaurant': round(usd * USD_INR / n, 1),
                      'notes': notes})
for years in (1, 3):
    for n in (1, 10, 50, 100, 500, 1000):
        data = live_gb(years) * n
        # 1) Cloudflare Durable Objects as built today: whole JSON rewritten in 500k-char rows on every save
        rows_per_save = max(1, int(live_gb(years) * GB / 500000 / 1.0) + 2)
        saves_month = bills_day * 30 * 1.2
        rw = n * rows_per_save * saves_month
        snaps = n * 30 * live_gb(years) * GZ
        usd = 5 + max(0, data + snaps - 5) * 0.20 + max(0, rw - 50e6) / 1e6 * 1.00
        add('Cloudflare Durable Objects (current design)', n, years, usd,
            f'$5 Workers Paid + $0.20/GB-mo over 5 GB (incl. 30 gz snapshots) + $1/M rows written over 50M; ~{rows_per_save} rows rewritten per save. Compute (GB-s) not included. NOT VIABLE past ~25-40 MB per hotel (128 MB memory, see report).', 'one JSON document per hotel')
        # 2) Cloudflare D1 after migration to tables: one row per bill + ~4 item rows, indexes x1.5
        d1_data = data * 1.5
        d1_rw = n * bills_day * 30 * 8
        usd = 5 + max(0, d1_data - 5) * 0.75 + max(0, d1_rw - 50e6) / 1e6
        add('Cloudflare D1 (relational, after migration)', n, years, usd,
            '$5 Workers Paid + $0.75/GB-mo over 5 GB + $1/M rows written over 50M; 10 GB max per database -> shard by hotel (50,000 DBs allowed). Storage = JSON size x1.5 for indexes (assumption).', 'tables, one DB per hotel or shard')
        # 3) Supabase Pro
        sizes = [(50, 0), (200, 5), (600, 50), (10**9, 100)]   # extra compute USD over the $10 credit (assumption)
        extra = next(c for lim, c in sizes if n <= lim)
        usd = 25 + extra + max(0, data * 1.5 - 8) * 0.125
        add('Supabase Pro (PostgreSQL)', n, years, usd,
            '$25/org incl. $10 compute credit + 8 GB disk; $0.125/GB disk beyond; compute size grows with tenants (assumption: Small at <=200, Medium <=600, Large above). PITR extra.', 'shared multi-tenant Postgres')
        # 4) Neon Launch
        cu = 0.25 if n <= 50 else 0.5 if n <= 200 else 1 if n <= 600 else 2
        usd = data * 1.5 * 0.35 + cu * 730 * 0.106
        add('Neon Launch (PostgreSQL)', n, years, usd,
            f'$0.35/GB-mo storage + $0.106/CU-h; assumed average {cu} CU always-on for POS traffic (no scale-to-zero during trading hours).', 'shared multi-tenant Postgres')
        # 5) Managed PostgreSQL (DigitalOcean-class), primary + standby
        node = 15 if n <= 50 else 30 if n <= 200 else 60 if n <= 600 else 120
        usd = node * 2 + max(0, data * 1.5 - 10) * 0.21
        add('Managed PostgreSQL (DigitalOcean-class) with HA', n, years, usd,
            f'Primary + standby node (${node}/mo each, size grows with tenants, assumption); extra storage ~$0.21/GB (assumption). Daily backups included.', 'shared multi-tenant Postgres')
        # 6) Self-hosted Postgres on a VPS
        vps = 9 if n <= 100 else 18 if n <= 500 else 36
        ops_hours = 4 if n <= 100 else 8
        usd = vps * 2 * 1.2 + data * 1.5 * 0.05 + ops_hours * 12
        add('Self-hosted PostgreSQL on VPS (Hetzner-class)', n, years, usd,
            f'2 VPS (primary + replica) ${vps}/mo each +20% backups, volume ~$0.05/GB, plus {ops_hours} h/month admin at ~$12/h (~Rs 1,140/h) for patching, backups, restore drills (assumption).', 'shared multi-tenant Postgres')
with open(os.path.join(DOCS, 'Hosting-Cost-Comparison.csv'), 'w', newline='') as f:
    w = csv.DictWriter(f, fieldnames=list(cost_rows[0].keys()))
    w.writeheader(); w.writerows(cost_rows)
print('cost rows', len(cost_rows))
