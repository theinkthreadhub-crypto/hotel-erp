"""Restaurant's own dish photos (Smart Food Visuals) on the counter PC.

Kept apart from the financial data: <data>/media/<id>.img (512 px) and <id>.t.img (160 px thumbnail).
The browser resizes and re-encodes every photo to WebP/JPEG before upload; this module only accepts
those two formats, checks the file signature and size, and names the file after its own SHA-256, so
a name can never point anywhere else (no paths from the device are used) and the same photo is stored once.
"""
import base64
import hashlib
import os
import re
import threading

ID_RE = re.compile(r'^m_[0-9a-f]{32}$')
MAX_FULL = 400 * 1024       # a 512 px WebP is ~30-80 KB
MAX_THUMB = 60 * 1024
MAX_FILES = 6000            # photos (each has a thumbnail)
MAX_TOTAL = 600 * 1024 * 1024


def sniff(b):
    """'image/webp' / 'image/jpeg' for a real file of that kind, else None (PNG, SVG, HTML… are refused)."""
    if len(b) >= 12 and b[:4] == b'RIFF' and b[8:12] == b'WEBP':
        return 'image/webp'
    if len(b) >= 4 and b[:3] == b'\xff\xd8\xff':
        return 'image/jpeg'
    return None


def media_id(full):
    return 'm_' + hashlib.sha256(full).hexdigest()[:32]


def decode(b64, limit):
    if not isinstance(b64, str) or len(b64) > limit * 4 // 3 + 8:
        raise ValueError('photo too large')
    try:
        raw = base64.b64decode(b64, validate=True)
    except Exception:
        raise ValueError('not a photo')
    if not raw or len(raw) > limit:
        raise ValueError('photo too large')
    if not sniff(raw):
        raise ValueError('only WebP or JPEG photos (the app converts them for you)')
    return raw


class MediaStore:
    def __init__(self, data_dir):
        self.dir = os.path.join(data_dir, 'media')
        self.lock = threading.Lock()

    def path(self, mid, thumb=False):
        if not ID_RE.match(str(mid or '')):
            return None
        return os.path.join(self.dir, mid + ('.t' if thumb else '') + '.img')

    def ids(self):
        try:
            return sorted(f[:-4] for f in os.listdir(self.dir) if f.endswith('.img') and not f.endswith('.t.img') and ID_RE.match(f[:-4]))
        except OSError:
            return []

    def usage(self):
        n = total = 0
        try:
            for f in os.listdir(self.dir):
                if f.endswith('.img'):
                    n += 1
                    total += os.path.getsize(os.path.join(self.dir, f))
        except OSError:
            pass
        return n, total

    def put(self, full_b64, thumb_b64, want_id=None):
        """Store one photo; returns its id. Raises ValueError for anything that is not a small WebP/JPEG."""
        full = decode(full_b64, MAX_FULL)
        thumb = decode(thumb_b64, MAX_THUMB)
        mid = media_id(full)
        if want_id and want_id != mid:
            raise ValueError('photo id does not match its content')
        with self.lock:
            p = self.path(mid)
            if os.path.exists(p) and os.path.exists(self.path(mid, True)):
                return mid
            n, total = self.usage()
            if n + 2 > MAX_FILES * 2 or total + len(full) + len(thumb) > MAX_TOTAL:
                raise ValueError('photo storage is full: remove unused photos first')
            os.makedirs(self.dir, exist_ok=True)
            for path, data in ((p, full), (self.path(mid, True), thumb)):
                tmp = path + '.tmp'
                with open(tmp, 'wb') as f:
                    f.write(data)
                os.replace(tmp, path)
        return mid

    def get(self, mid, thumb=False):
        """(bytes, content type) or None."""
        p = self.path(mid, thumb)
        if not p or not os.path.isfile(p):
            return None
        with open(p, 'rb') as f:
            b = f.read()
        t = sniff(b)
        return (b, t) if t else None

    def export(self, after='', limit=40):
        """A page of photos for a backup file: [{id, full, thumb}], next cursor."""
        out, ids = [], [i for i in self.ids() if i > (after or '')]
        for mid in ids[:limit]:
            a, b = self.get(mid), self.get(mid, True)
            if a and b:
                out.append({'id': mid, 'full': base64.b64encode(a[0]).decode(), 'thumb': base64.b64encode(b[0]).decode()})
        return out, (ids[limit - 1] if len(ids) > limit else '')

    def copy_to(self, folder):
        """Auto backup: copy photos not yet in <folder> (same name = same content)."""
        import shutil
        os.makedirs(folder, exist_ok=True)
        have = set(os.listdir(folder))
        n = 0
        for mid in self.ids():
            for th in (False, True):
                name = mid + ('.t' if th else '') + '.img'
                if name not in have:
                    shutil.copy2(self.path(mid, th), os.path.join(folder, name))
                    n += 1
        return n

    def restore_from(self, folder):
        """Bring back photos from an auto-backup folder (only valid, matching files)."""
        n = 0
        try:
            names = os.listdir(folder)
        except OSError:
            return 0
        for f in names:
            m = re.match(r'^(m_[0-9a-f]{32})\.img$', f)
            if not m or (m.group(1) + '.t.img') not in names:
                continue
            try:
                with open(os.path.join(folder, f), 'rb') as a, open(os.path.join(folder, m.group(1) + '.t.img'), 'rb') as b:
                    full, thumb = a.read(), b.read()
                self.put(base64.b64encode(full).decode(), base64.b64encode(thumb).decode(), m.group(1))
                n += 1
            except (OSError, ValueError):
                continue
        return n
