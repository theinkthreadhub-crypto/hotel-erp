"""HoReCa One inbound licence verification — no private signing key is stored here.

Canonical SETU key: 13-byte payload + 64-byte ECDSA P-256 raw (r||s) signature,
encoded in Base32 and prefixed with SETU-. Format agrees with keygen.py and
cloud/src/worker.js. Invalid keys FAIL CLOSED.

`cryptography` must be bundled with the Windows counter; missing dependency
does not trigger an unsafe bypass.
"""
import base64
import hashlib
from datetime import date, timedelta, timezone, datetime

# Public verification keys from cloud/src/worker.js LIC_PUBKEYS at Phase 3.4.
# Never add private material to this file.
TRUSTED_PUBLIC_KEYS = (
    "BLqTi3yiy2JnNcdhuUtUD4psUtpVU9/SjOOwYqkNLwSgA9I3s86nKT8u1rDhLU4CGzIjWnwdERCdri/jAH7Tttc=",
    "BIaSZabMX2d0YUMVTeNbvQvwWGvewBdIUMBTDu83hyD84V2ursUn7/DNMjWY5yQcQULZ3zgHMuJCTwZol9WrPg0=",
    "BM5bUDY3UM7RlEK5DtWhEq0N3mySWG27xZA3gmkCzNETrSpwrM1GaubNvi0XKGLeBZHPE8HeXlzpFeUBzFS25/M=",
)
B32 = "ABCDEFGHIJKLMNOPQRSTUVWXYZ234567"
EPOCH = date(2026, 1, 1)
DAY_MS = 86_400_000


class InvalidLicence(ValueError):
    pass


def clean_install_id(install_id):
    return "".join(c for c in str(install_id or "").upper() if c in "ABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789")


def verify_signed_license(key, install_id, *, public_keys=TRUSTED_PUBLIC_KEYS, now_ms=None):
    """Verify genuine ECDSA, device binding, type and expiration.

    Kind 6 (master/unbound) keys are intentionally not accepted over inbound
    cloud sync; they must follow the dedicated first-install activation process.
    Kind 4 password-reset and kind 7 WhatsApp-credit keys cannot grant a licence.
    Test callers may inject a newly-generated PUBLIC key (never a private key).
    """
    if not isinstance(key, str):
        raise InvalidLicence("signed SETU key required")
    text = key.strip().upper().replace("-", "").replace(" ", "")
    if len(text) != 128 or not text.startswith("SETU") or any(c not in B32 for c in text):
        raise InvalidLicence("invalid signed SETU key format")
    try:
        raw = base64.b32decode(text[4:] + ('=' * (-len(text[4:]) % 8)), casefold=False)
    except (ValueError, base64.binascii.Error) as exc:
        raise InvalidLicence("invalid signed SETU key encoding") from exc
    if len(raw) != 77:
        raise InvalidLicence("invalid signed SETU key length")
    # Base32 final character has unused padding bits; noncanonical changes
    # must be rejected even if they decode to the same 77 bytes.
    canonical = base64.b32encode(raw).decode("ascii").rstrip("=")
    if canonical != text[4:]:
        raise InvalidLicence("noncanonical signed SETU key encoding")
    payload, sig = raw[:13], raw[13:]
    if payload[0] != 1 or payload[1] not in (1, 2, 3, 5):
        raise InvalidLicence("unsupported inbound licence key type")

    clean = clean_install_id(install_id)
    if len(clean) < 8:
        raise InvalidLicence("registered installation ID required")
    expected = hashlib.sha256(clean.encode("ascii")).digest()[:4]
    if payload[4:8] != expected:
        raise InvalidLicence("licence belongs to another installation")

    try:
        from cryptography.hazmat.primitives import hashes, serialization
        from cryptography.hazmat.primitives.asymmetric import ec
        from cryptography.hazmat.primitives.asymmetric.utils import encode_dss_signature
        from cryptography.exceptions import InvalidSignature
    except ImportError as exc:
        raise InvalidLicence("cryptography verifier unavailable; refusing licence") from exc

    r = int.from_bytes(sig[:32], "big")
    s = int.from_bytes(sig[32:], "big")
    signature_der = encode_dss_signature(r, s)
    verified = False
    for encoded in public_keys:
        try:
            public_raw = base64.b64decode(encoded, validate=True)
            public = ec.EllipticCurvePublicKey.from_encoded_point(ec.SECP256R1(), public_raw)
            public.verify(signature_der, payload, ec.ECDSA(hashes.SHA256()))
            verified = True
            break
        except (InvalidSignature, ValueError, TypeError):
            continue
    if not verified:
        raise InvalidLicence("licence cryptographic signature not genuine")

    kind = payload[1]
    value = int.from_bytes(payload[2:4], "big")
    issued = EPOCH + timedelta(days=int.from_bytes(payload[11:13], "big"))
    issued_ms = int(datetime(issued.year, issued.month, issued.day, tzinfo=timezone.utc).timestamp() * 1000)
    if now_ms is None:
        now_ms = int(datetime.now(timezone.utc).timestamp() * 1000)
    if issued_ms > now_ms + DAY_MS:
        raise InvalidLicence("licence issue date is in the future")
    lifetime = kind == 3
    valid_until_ms = None
    if not lifetime:
        if value < 1:
            raise InvalidLicence("licence duration invalid")
        valid_until_ms = issued_ms + (value + 1) * DAY_MS if kind in (1, 5) else issued_ms + DAY_MS + value * 60_000
        if now_ms >= valid_until_ms:
            raise InvalidLicence("signed licence expired")
    return {
        "key_id": hashlib.sha256(raw).hexdigest(),
        "kind": kind,
        "value": value,
        "lifetime": lifetime,
        "valid_until_ms": valid_until_ms,
        "issued_ms": issued_ms,
    }
