"""Setu security core for the main-counter server (app_main.py). The cloud Worker has the same rules in
cloud/src/security.js; keep both in step (tests/p0-security.js checks both).

1. Credentials never live in the shared data as plain text. Owner password, manager / cashier PIN and staff
   PINs are kept as salted PBKDF2-SHA256 hashes in data['secure'], which only the main counter and the cloud
   sync see. Every other response gets public_view() (no 'secure', no plain PINs, only "is set" flags).
2. absorb_secrets(): a plain PIN that arrives in a save (older screens, first set-up) becomes a hash and is
   removed. Only the owner / manager (or the counter's own cloud sync) may set or change one.
3. sanitize_write(): a save from a cashier / captain / kitchen login cannot change settings, logins, staff,
   the licence, the audit log, the menu or past bills / vouchers / stock movements. Such changes are put
   back to the stored values (the rest of the save, e.g. a new bill, is kept) and listed as 'blocked'.
"""
import base64
import copy
import hashlib
import hmac
import ipaddress
import json
import os
import secrets
import time

ITERATIONS = 100000          # the Cloudflare Worker's WebCrypto allows at most 100,000 PBKDF2 iterations
ADMIN_ROLES = ('admin', 'sync', 'local')

# ---------- password hashing ----------

def hash_secret(secret, iterations=ITERATIONS):
    salt = secrets.token_bytes(16)
    dk = hashlib.pbkdf2_hmac('sha256', str(secret).encode('utf-8'), salt, iterations)
    return 'pbkdf2_sha256$%d$%s$%s' % (iterations, base64.b64encode(salt).decode(), base64.b64encode(dk).decode())


def verify_secret(secret, stored):
    try:
        algo, it, salt, dk = str(stored).split('$')
        if algo != 'pbkdf2_sha256':
            return False
        got = hashlib.pbkdf2_hmac('sha256', str(secret).encode('utf-8'), base64.b64decode(salt), int(it))
        return hmac.compare_digest(got, base64.b64decode(dk))
    except Exception:
        return False


WEAK = {'0000', '1111', '1234', '12345', '123456', '2222', '9999', '0123', '4321', '1212', 'admin', 'password'}


def is_weak(pin):
    p = str(pin or '')
    return len(p) < 4 or p.lower() in WEAK or len(set(p)) == 1


# ---------- credentials in the data ----------

def _staff_key(s, i):
    return str(s.get('id') or ('idx%d' % i))


def absorb_secrets(new, old, can_set):
    """Turn plain credentials in `new` into hashes (when can_set) and remove them. Returns True if `new` changed.
    The stored hashes always come from `old` first, so a save without them never deletes a login."""
    changed = False
    old = old if isinstance(old, dict) else {}
    # Hashes come only from the stored data: a device can never send its own
    sec = copy.deepcopy(old.get('secure')) if isinstance(old.get('secure'), dict) else {}
    sec.setdefault('v', 1)
    sec.setdefault('staff', {})
    st = new.get('settings') if isinstance(new.get('settings'), dict) else None
    auth = new.get('auth') if isinstance(new.get('auth'), dict) else None

    def take(container, key, slot, weak_flag=None):
        nonlocal changed
        if container is None or key not in container:
            return
        val = container.pop(key)
        changed = True
        if can_set and isinstance(val, (str, int)) and str(val) != '':
            prev = sec.get(slot)
            if not (prev and verify_secret(val, prev)):
                sec[slot] = hash_secret(val)
                if slot in ('admin', 'owner') and sec.get('rotateNeeded'):
                    sec['rotateNeeded'] = False     # the owner chose a new one after the migration
            if weak_flag and st is not None:
                st[weak_flag] = is_weak(val)

    take(st, 'adminPin', 'admin', 'adminPinWeak')
    take(st, 'cashierPin', 'cashier', 'cashierPinWeak')
    take(auth, 'password', 'owner')
    staff = new.get('staff') if isinstance(new.get('staff'), list) else []
    keep = set()
    for i, s in enumerate(staff):
        if not isinstance(s, dict):
            continue
        k = _staff_key(s, i)
        keep.add(k)
        if 'pin' in s:
            val = s.pop('pin')
            changed = True
            if can_set and isinstance(val, (str, int)) and str(val) != '':
                prev = sec['staff'].get(k)
                if not (prev and verify_secret(val, prev)):
                    sec['staff'][k] = hash_secret(val)
                s['pinWeak'] = is_weak(val)
        has = bool(sec['staff'].get(k))
        if s.get('hasPin') != has:
            s['hasPin'] = has
            changed = True
    if can_set:
        for k in list(sec['staff']):
            if k not in keep:
                del sec['staff'][k]          # staff removed by the manager: the PIN goes too
    # "Is set" flags for the screens (never the values)
    if st is not None:
        for flag, slot in (('adminPinSet', 'admin'), ('cashierPinSet', 'cashier')):
            if st.get(flag) != bool(sec.get(slot)):
                st[flag] = bool(sec.get(slot))
                changed = True
        rot = bool(sec.get('rotateNeeded'))
        if bool(st.get('credRotate')) != rot:
            if rot:
                st['credRotate'] = True
            else:
                st.pop('credRotate', None)
            changed = True
    if auth is not None and auth.get('passwordSet') != bool(sec.get('owner')):
        auth['passwordSet'] = bool(sec.get('owner'))
        changed = True
    if new.get('secure') != sec:
        new['secure'] = sec
        changed = True
    return changed


def migrate_plaintext(d):
    """One-time move of plain credentials in an existing database into hashes. Returns True if something moved."""
    if not isinstance(d, dict):
        return False
    st, auth = d.get('settings') or {}, d.get('auth') or {}
    had = any(k in st for k in ('adminPin', 'cashierPin')) or 'password' in auth or any(isinstance(s, dict) and 'pin' in s for s in d.get('staff') or [])
    if not had:
        return False
    absorb_secrets(d, {'secure': d.get('secure')}, True)
    d['secure']['migrated'] = int(time.time() * 1000)
    d['secure']['rotateNeeded'] = True    # the old PINs were readable by every login: ask for new ones
    absorb_secrets(d, {'secure': d['secure']}, False)   # refresh the flags
    return True


def public_view(d):
    """What a device may see: no hashes, no plain credentials."""
    if not isinstance(d, dict):
        return d
    out = dict(d)
    out.pop('secure', None)
    if isinstance(out.get('settings'), dict):
        out['settings'] = {k: v for k, v in out['settings'].items() if k not in ('adminPin', 'cashierPin')}
    if isinstance(out.get('auth'), dict):
        out['auth'] = {k: v for k, v in out['auth'].items() if k != 'password'}
    if isinstance(out.get('staff'), list):
        out['staff'] = [{k: v for k, v in s.items() if k != 'pin'} if isinstance(s, dict) else s for s in out['staff']]
    return out


def check_pin(d, pin):
    """(role, name) for a PIN / owner password, using the hashes; plain values only before migration."""
    pin = str(pin or '')
    if not pin or not isinstance(d, dict):
        return None
    sec = d.get('secure') if isinstance(d.get('secure'), dict) else {}
    st, auth = d.get('settings') or {}, d.get('auth') or {}
    owner_name = auth.get('ownerName') or 'Manager'

    def match(slot, plain):
        if sec.get(slot):
            return verify_secret(pin, sec[slot])
        return plain not in (None, '') and hmac.compare_digest(str(plain), pin)

    if match('admin', st.get('adminPin')) or match('owner', auth.get('password')):
        return 'admin', owner_name
    for i, s in enumerate(d.get('staff') or []):
        if not isinstance(s, dict) or s.get('left'):
            continue
        access = s.get('access') or s.get('role')
        if not access:
            continue
        k = _staff_key(s, i)
        ok = verify_secret(pin, sec['staff'][k]) if (sec.get('staff') or {}).get(k) else (s.get('pin') not in (None, '') and hmac.compare_digest(str(s.get('pin')), pin))
        if ok:
            return {'manager': 'admin'}.get(access, access), s.get('name') or 'Staff'
    if match('cashier', st.get('cashierPin')):
        return 'cashier', 'Cashier'
    return None


def check_master(d, password):
    """Gate-1 hotel password: the owner password or the manager PIN (hashes; plain only before migration)."""
    pw = str(password or '')
    if not pw or not isinstance(d, dict):
        return False
    sec = d.get('secure') if isinstance(d.get('secure'), dict) else {}
    st, auth = d.get('settings') or {}, d.get('auth') or {}
    for slot, plain in (('owner', auth.get('password')), ('admin', st.get('adminPin'))):
        if sec.get(slot):
            if verify_secret(pw, sec[slot]):
                return True
        elif plain not in (None, '') and hmac.compare_digest(str(plain), pw):
            return True
    return False


def has_credentials(d):
    if not isinstance(d, dict):
        return False
    sec = d.get('secure') or {}
    st, auth = d.get('settings') or {}, d.get('auth') or {}
    return bool(sec.get('admin') or sec.get('owner') or sec.get('cashier') or (sec.get('staff') or {})
                or st.get('adminPin') or st.get('cashierPin') or auth.get('password') or d.get('staff'))


# ---------- role-aware saves ----------

# Settings a cashier's device changes during normal work (printer found, app version, WhatsApp counters)
SETTINGS_OPEN = {'appVersion', 'printAuto', 'billPrinter', 'kotPrinter', 'waTotalSent', 'waCredits', 'adminPinSet', 'cashierPinSet',
                 'adminPinWeak', 'cashierPinWeak', 'credRotate'}
# New settings a device may add when missing (defaults of a newer screen) — never these
SETTINGS_SENSITIVE = {'adminPin', 'cashierPin', 'maxDiscPct', 'discLimit', 'upi', 'gstin', 'gst', 'gstScheme', 'gstInclusive', 'name',
                      'address', 'phone', 'owner', 'email', 'hotelId', 'installId', 'waProvider', 'waReceiptMode', 'waWebhook', 'orderWa', 'caWa',
                      'zomatoComm', 'swiggyComm', 'loyalty', 'ptsPer100', 'ptValue', 'tables', 'archiveKeep'}
BILL_LOCKED = ('no', 'date', 'time', 'items', 'sub', 'disc', 'taxable', 'tax', 'round', 'total', 'mode', 'pays', 'cancelled', 'cancelledBy',
               'channel', 'table', 'gstRate', 'scheme', 'gstin', 'cust', 'phone', 'loyaltyDisc', 'ptsUsed', 'ptsEarned', 'used')
TXN_LOCKED = ('type', 'date', 'time', 'amount', 'head', 'mode', 'party', 'qty', 'sid', 'inv', 'desc')
MENU_OPEN = ('qrOff', 'out')


def _by_id(lst):
    return {x['id']: x for x in (lst or []) if isinstance(x, dict) and x.get('id') is not None}


def _today():
    return time.strftime('%Y-%m-%d')


def _days_ago(n):
    return time.strftime('%Y-%m-%d', time.localtime(time.time() - n * 86400))


def sanitize_write(role, old, new, elevated=False):
    """Mutates `new`: changes a non-manager login may not make are put back from `old`.
    Returns the list of what was put back (empty = nothing blocked)."""
    if role in ADMIN_ROLES or elevated or not isinstance(old, dict):
        return []
    blocked = []

    def restore_key(k):
        if k in old:
            if new.get(k) != old[k]:
                new[k] = copy.deepcopy(old[k])
                blocked.append(k)
        elif k in new:
            del new[k]
            blocked.append(k)

    for k in ('auth', 'staff', 'saas', 'secure'):
        restore_key(k)
    # Licence: the device may only note when Setu last ran (clock check)
    if 'subscription' in old or 'subscription' in new:
        last = (new.get('subscription') or {}).get('lastSeen') if isinstance(new.get('subscription'), dict) else None
        restore_key('subscription')
        if last is not None and isinstance(new.get('subscription'), dict) and last != new['subscription'].get('lastSeen'):
            new['subscription']['lastSeen'] = last
            if 'subscription' in blocked and new.get('subscription') == {**(old.get('subscription') or {}), 'lastSeen': last}:
                blocked.remove('subscription')
    # Settings
    os_, ns = old.get('settings') or {}, new.get('settings') if isinstance(new.get('settings'), dict) else {}
    fixed = dict(ns)
    for k in set(os_) | set(ns):
        if k in SETTINGS_OPEN:
            if k == 'waCredits' and k in os_ and isinstance(ns.get(k), (int, float)) and isinstance(os_.get(k), (int, float)) and ns[k] > os_[k]:
                fixed[k] = os_[k]
                blocked.append('settings.waCredits')
            continue
        if k in os_:
            if ns.get(k) != os_[k]:
                fixed[k] = copy.deepcopy(os_[k])
                blocked.append('settings.' + k)
        elif k in SETTINGS_SENSITIVE:
            fixed.pop(k, None)
            blocked.append('settings.' + k)
    new['settings'] = fixed
    # Menu: only "out of stock / hide on QR" may change
    om, nm = _by_id(old.get('menu')), _by_id(new.get('menu'))
    if om or nm:
        menu = []
        for mid, o in om.items():
            n = nm.get(mid)
            item = copy.deepcopy(o)
            if n is None:
                blocked.append('menu.delete')
            else:
                for f in MENU_OPEN:
                    if f in n:
                        item[f] = n[f]
                    else:
                        item.pop(f, None)
                if {k: v for k, v in n.items() if k not in MENU_OPEN} != {k: v for k, v in o.items() if k not in MENU_OPEN}:
                    blocked.append('menu.' + str(mid))
            menu.append(item)
        if any(mid not in om for mid in nm):
            blocked.append('menu.add')
        new['menu'] = menu
    # Append-only lists: past records cannot be deleted or have their money fields changed
    def guard_list(key, locked, may_drop=None):
        ol, nl = _by_id(old.get(key)), new.get(key) if isinstance(new.get(key), list) else []
        nmap = _by_id(nl)
        out = list(nl)
        for rid, o in ol.items():
            n = nmap.get(rid)
            if n is None:
                if may_drop and may_drop(o):
                    continue
                out.append(copy.deepcopy(o))
                blocked.append(key + '.delete')
                continue
            fields = locked if locked else set(o) | set(n)
            for f in fields:
                if o.get(f) != n.get(f):
                    if f in o:
                        n[f] = copy.deepcopy(o[f])
                    else:
                        n.pop(f, None)
                    blocked.append(key + '.' + f)
        if ol or nl:
            new[key] = out
    guard_list('bills', BILL_LOCKED)
    guard_list('txns', TXN_LOCKED)
    guard_list('moves', None)
    guard_list('cnotes', None)
    guard_list('kots', ('no', 'items', 'table', 'date'), may_drop=lambda k: str(k.get('date') or '') < _days_ago(6))
    a_old = old.get('audit') or []
    guard_list('audit', None, may_drop=lambda a: len(a_old) >= 19000)
    # Running numbers never go back
    os2, ns2 = old.get('seq') or {}, new.get('seq') if isinstance(new.get('seq'), dict) else {}
    for k in ('bill', 'kot', 'cn'):
        if isinstance(os2.get(k), (int, float)) and (not isinstance(ns2.get(k), (int, float)) or ns2[k] < os2[k]):
            ns2[k] = os2[k]
            blocked.append('seq.' + k)
    if ns2:
        new['seq'] = ns2
    # Stock items may change (counts, rates) but are never deleted by a cashier
    so, sn = _by_id(old.get('stock')), _by_id(new.get('stock'))
    for sid, o in so.items():
        if sid not in sn:
            new.setdefault('stock', []).append(copy.deepcopy(o))
            blocked.append('stock.delete')
    return sorted(set(blocked))


# ---------- request checks (local counter server) ----------

def host_allowed(host_header):
    """Host must be an IP literal or localhost (a DNS name pointing at 127.0.0.1 = DNS rebinding)."""
    h = str(host_header or '').strip().lower()
    if not h:
        return False
    if h.startswith('['):
        name = h[1:h.find(']')] if ']' in h else h[1:]
    else:
        name = h.rsplit(':', 1)[0] if h.count(':') == 1 else h
    if name in ('localhost',):
        return True
    try:
        ipaddress.ip_address(name)
        return True
    except ValueError:
        return False


def origin_allowed(origin, host_header):
    """No Origin (same-origin GET, apps, curl) is fine; else it must be this server's own address."""
    if not origin:
        return True
    o = str(origin).strip().lower()
    if o == 'null':
        return False
    h = str(host_header or '').strip().lower()
    return o in ('http://' + h, 'https://' + h)


def is_network_path(path):
    """UNC paths (\\\\server\\share, //server/share) or a mapped network drive on Windows."""
    p = str(path or '').strip()
    if p.startswith('\\\\') or p.startswith('//'):
        return True
    if os.name == 'nt' and len(p) >= 2 and p[1] == ':':
        try:
            import ctypes
            return ctypes.windll.kernel32.GetDriveTypeW(p[:2] + '\\') == 4   # DRIVE_REMOTE
        except Exception:
            return False
    return False


def json_dumps(d):
    return json.dumps(d, ensure_ascii=False)
