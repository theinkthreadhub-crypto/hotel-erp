"""Synthetic hotel data in the app's own format (setu-db.json), for scale tests on any OS. Development tool.

    python tools/db-benchmark/make_dataset.py <dataFolder> <bills> [--per-day 1000] [--end 2026-01-05]

Writes <dataFolder>/setu-db.json: menu (120 dishes with recipes), stock (60 items with opening movements),
<bills> bills at <per-day> a day (items, recipe use, Cash / UPI / Card / Split / Credit / Wallet, customers with
mobile numbers and loyalty points, a few Zomato / Swiggy, about 1% cancelled), KOTs of the last 7 days,
purchases on credit with part payments, expenses, wastage, staff with PINs, audit (last 20,000).
Logins: owner password Bench@Owner2026, Manager PIN 739146, cashier PIN 520000 (test values only).
"""
import json
import os
import random
import sys
import time
from datetime import date, timedelta

args = sys.argv[1:]
DIR, N = args[0], int(args[1])
opt = lambda k, d: args[args.index(k) + 1] if k in args else d   # noqa: E731
PER_DAY, END = int(opt('--per-day', '1000')), opt('--end', '2026-01-05')
rnd = random.Random(42)
days = (N + PER_DAY - 1) // PER_DAY
end = date.fromisoformat(END)
start = end - timedelta(days=days - 1)

stock = [{'id': f'stk{i}', 'name': f'Ingredient {i}', 'unit': 'kg' if i % 3 else 'pc', 'qty': 0, 'rate': 20 + i, 'cat': ['Dry', 'Dairy', 'Veg', 'Meat'][i % 4]} for i in range(60)]
menu = [{'id': f'mnu{i}', 'name': f'Dish {i}', 'cat': ['Starters', 'Main', 'Breads', 'Drinks', 'Desserts'][i % 5], 'price': 40 + (i * 13) % 400,
         'recipe': [{'sid': f'stk{(i * 7 + k) % 60}', 'qty': round(0.05 + 0.05 * k, 2)} for k in range(1 + i % 3)]} for i in range(120)]
moves = [{'id': f'open-stk{i}', 'at': 0, 'date': start.isoformat(), 'time': '08:00', 'sid': f'stk{i}', 'qty': 1000000, 'type': 'open', 'by': 'Owner', 'note': 'Starting stock'} for i in range(60)]
bills, kots, txns, audit = [], [], [], []
phones = ['98' + str(10000000 + c * 7919)[-8:] for c in range(2000)]
no = kno = 0
for d in range(days):
    day = (start + timedelta(days=d)).isoformat()
    for i in range(min(PER_DAY, N - len(bills))):
        no += 1
        kno += 1
        items = []
        for k in range(1 + rnd.randrange(4)):
            m = menu[rnd.randrange(len(menu))]
            items.append({'mid': m['id'], 'name': m['name'], 'price': m['price'], 'qty': 1 + rnd.randrange(3)})
        sub = sum(x['price'] * x['qty'] for x in items)
        disc = 0 if rnd.random() > 0.1 else round(sub * 0.05, 2)
        taxable = round(sub - disc, 2)
        tax = round(taxable * 0.05, 2)
        total = round(taxable + tax)
        used = {}
        for x in items:
            for r in next(m for m in menu if m['id'] == x['mid'])['recipe']:
                used[r['sid']] = round(used.get(r['sid'], 0) + r['qty'] * x['qty'], 3)
        mode = rnd.choice(['Cash', 'Cash', 'UPI', 'UPI', 'Card', 'Split', 'Credit'])
        b = {'id': f'b{d}-{i}', 'idemKey': f'idem_b{d}-{i}', 'orderSessionId': f's{d}-{i}', 'mv': 1, 'no': no, 'kot': kno, 'date': day,
             'time': f'{11 + i * 12 // max(1, PER_DAY):02d}:{(i * 7) % 60:02d}', 'channel': 'Dine-In', 'orderId': '', 'table': f'T-{1 + i % 20}',
             'cust': '', 'phone': '', 'note': '', 'mode': mode, 'paymentStatus': 'recorded', 'gstRate': 5, 'scheme': 'regular', 'items': items,
             'sub': sub, 'disc': disc, 'taxable': taxable, 'tax': tax, 'round': round(total - taxable - tax, 2), 'total': total,
             'ptsUsed': 0, 'ptsEarned': 0, 'loyaltyDisc': 0, 'token': 0, 'by': 'Cashier', 'used': [{'sid': s, 'qty': q} for s, q in used.items()]}
        if mode == 'Split':
            a = round(total / 2)
            b['pays'] = [{'mode': 'Cash', 'amt': a}, {'mode': 'UPI', 'amt': total - a}]
        if i % 4 == 0:
            p = phones[(d * 37 + i) % len(phones)]
            b.update(phone=p, cust=f'Customer {int(p[-4:])}', ptsEarned=total // 100)
        if i % 97 == 0:
            b['channel'] = 'Zomato' if i % 2 else 'Swiggy'
            b['ptsEarned'] = 0
        if i % 101 == 0:
            b.update(cancelled=True, cancelledBy='Owner')
        bills.append(b)
        if d >= days - 7:
            kots.append({'id': f'k{d}-{i}', 'no': kno, 'date': day, 'time': b['time'], 'table': b['table'], 'channel': 'Dine-In',
                         'items': [{'mid': x['mid'], 'name': x['name'], 'qty': x['qty']} for x in items], 'status': 'served'})
    for j in range(3):
        s = stock[(d * 3 + j) % 60]
        inv = {'id': f'inv{d}-{j}', 'no': f'P-{d}-{j}', 'total': 50 * s['rate'], 'paid': 20 * s['rate'], 'n': 1}
        txns.append({'id': f'p{d}-{j}', 'type': 'Purchase', 'date': day, 'time': '10:00', 'head': s['name'], 'party': f'Supplier {j}', 'amount': inv['total'],
                     'mode': 'Credit', 'sid': s['id'], 'qty': 50, 'mv': 1, 'inv': inv})
        txns.append({'id': f'sp{d}-{j}', 'type': 'Expense', 'date': day, 'time': '10:05', 'head': 'Supplier Payment', 'party': f'Supplier {j}', 'amount': inv['paid'],
                     'mode': 'Cash', 'inv': {'id': inv['id']}})
    txns.append({'id': f'e{d}', 'type': 'Expense', 'date': day, 'time': '18:00', 'head': 'Electricity', 'party': '', 'amount': 1500, 'mode': 'UPI'})
    moves.append({'id': f'w{d}', 'at': 0, 'date': day, 'time': '22:00', 'sid': stock[d % 60]['id'], 'qty': -0.5, 'type': 'waste', 'by': 'Chef', 'note': 'spoiled'})
    audit.append({'id': f'a{d}', 'at': 0, 'date': day, 'time': '09:00', 'user': 'Owner', 'role': 'admin', 'action': 'Login', 'detail': '', 'amount': 0, 'ref': ''})
for p in phones[:300]:
    txns.append({'id': f'wt{p}', 'type': 'Receipt', 'date': start.isoformat(), 'time': '09:00', 'head': 'Customer Wallet Topup', 'party': 'Customer', 'phone': p, 'amount': 5000, 'mode': 'Cash'})
data = {
    'settings': {'name': 'Bench Hotel', 'hotelId': 'BENCHWIN', 'gst': 5, 'gstScheme': 'regular', 'adminPin': '739146', 'cashierPin': '520000',
                 'loyalty': True, 'ptsPer100': 1, 'ptValue': 1, 'tables': [f'T-{i}' for i in range(1, 21)], 'theme': 'horeca_light', 'dashStyle': 'modern'},
    'auth': {'isRegistered': True, 'hotelId': 'BENCHWIN', 'userId': 'owner', 'password': 'Bench@Owner2026', 'ownerName': 'Owner', 'paidUntil': int(time.time() * 1000) + 365 * 86400000},
    'subscription': {'status': 'active', 'validUntil': (end + timedelta(days=365)).isoformat()},
    'staff': [{'id': 'st1', 'name': 'Manager', 'role': 'admin', 'access': 'manager', 'pin': '739146'}, {'id': 'st2', 'name': 'Cashier', 'role': 'cashier', 'access': 'cashier', 'pin': '520000'}],
    'menu': menu, 'stock': stock, 'bills': bills, 'kots': kots, 'txns': txns, 'moves': moves, 'audit': audit[-20000:], 'att': {}, 'kaccha': {}, 'cash': {},
    'seq': {'bill': no, 'kot': kno, 'token': 0, 'tokenDate': END}, 'cnotes': [], 'orders': [], 'custList': [], 'supInfo': {}, 'supAlias': {}, 'stockAlias': {},
}
# Stock now = opening + purchases - sales + cancellations + wastage (the app's stockRecalc rule)
tot = {}
for m in moves:
    tot[m['sid']] = tot.get(m['sid'], 0) + m['qty']
for t in txns:
    if t.get('type') == 'Purchase' and t.get('mv'):
        tot[t['sid']] = tot.get(t['sid'], 0) + t['qty']
for b in bills:
    for u in b['used']:
        tot[u['sid']] = tot.get(u['sid'], 0) - u['qty'] + (u['qty'] if b.get('cancelled') else 0)
for s in stock:
    s['qty'] = round(tot.get(s['id'], 0), 3)
os.makedirs(DIR, exist_ok=True)
with open(os.path.join(DIR, 'setu-db.json'), 'w', encoding='utf-8') as f:
    json.dump({'version': 1, 'savedAt': int(time.time() * 1000), 'data': data}, f, ensure_ascii=False)
print(json.dumps({'bills': len(bills), 'days': days, 'from': start.isoformat(), 'to': END, 'MB': round(os.path.getsize(os.path.join(DIR, 'setu-db.json')) / 1048576, 1)}))
