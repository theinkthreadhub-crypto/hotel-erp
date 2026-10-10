#!/usr/bin/env python3
"""APK ko zipalign (4 byte) karke APK Signature Scheme v2 se sign karta hai (bina Android SDK ke).
   python3 apksign.py in.apk out.apk keystore.p12 password
in.apk pehle se jarsigner (v1) se sign ho sakta hai; v2 block uske upar lagta hai."""
import hashlib, struct, sys, zlib
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import padding
from cryptography.hazmat.primitives.serialization import pkcs12

def read_zip(data):
    eocd = data.rfind(b'PK\x05\x06')
    n, cd_size, cd_off = struct.unpack('<HII', data[eocd + 10:eocd + 20])
    entries, p = [], cd_off
    for _ in range(n):
        (sig, vmade, vneed, flag, meth, mt, md, crc, csz, usz, nl, xl, cl, disk, iattr, eattr, loff) = \
            struct.unpack('<IHHHHHHIIIHHHHHII', data[p:p + 46])
        name = data[p + 46:p + 46 + nl]
        cext = data[p + 46 + nl:p + 46 + nl + xl]
        comment = data[p + 46 + nl + xl:p + 46 + nl + xl + cl]
        lnl, lxl = struct.unpack('<HH', data[loff + 26:loff + 30])
        body = data[loff + 30 + lnl + lxl:loff + 30 + lnl + lxl + csz]
        entries.append(dict(vmade=vmade, vneed=vneed, flag=flag & ~0x08, meth=meth, mt=mt, md=md, crc=crc, csz=csz, usz=usz,
                            name=name, cext=cext, comment=comment, iattr=iattr, eattr=eattr, body=body))
        p += 46 + nl + xl + cl
    return entries

def write_zip(entries):
    out, cd = bytearray(), bytearray()
    for e in entries:
        off = len(out)
        extra = b''
        if e['meth'] == 0:  # stored: data 4 byte par align (resources.arsc ke liye zaroori)
            pad = (4 - (off + 30 + len(e['name'])) % 4) % 4
            extra = b'\x00' * pad
        out += struct.pack('<IHHHHHIIIHH', 0x04034b50, e['vneed'], e['flag'], e['meth'], e['mt'], e['md'],
                           e['crc'], e['csz'], e['usz'], len(e['name']), len(extra)) + e['name'] + extra + e['body']
        cd += struct.pack('<IHHHHHHIIIHHHHHII', 0x02014b50, e['vmade'], e['vneed'], e['flag'], e['meth'], e['mt'], e['md'],
                          e['crc'], e['csz'], e['usz'], len(e['name']), 0, len(e['comment']), 0, e['iattr'], e['eattr'], off) \
            + e['name'] + e['comment']
    eocd = struct.pack('<IHHHHIIH', 0x06054b50, 0, 0, len(entries), len(entries), len(cd), len(out), 0)
    return bytes(out), bytes(cd), eocd

def lp(b): return struct.pack('<I', len(b)) + b

def chunk_digest(parts):
    chunks = []
    for part in parts:
        for i in range(0, len(part), 1 << 20):
            c = part[i:i + (1 << 20)]
            chunks.append(hashlib.sha256(b'\xa5' + struct.pack('<I', len(c)) + c).digest())
    return hashlib.sha256(b'\x5a' + struct.pack('<I', len(chunks)) + b''.join(chunks)).digest()

def sign(inp, outp, ks, pw):
    key, cert, _ = pkcs12.load_key_and_certificates(open(ks, 'rb').read(), pw.encode())
    entries, cd, eocd = write_zip(read_zip(open(inp, 'rb').read()))
    zip_entries = entries
    digest = chunk_digest([zip_entries, cd, eocd])  # EOCD mein CD offset = signing block ka offset (abhi wahi hai)
    ALG = 0x0103  # RSASSA-PKCS1-v1_5 + SHA-256
    cert_der = cert.public_bytes(serialization.Encoding.DER)
    signed_data = lp(lp(struct.pack('<I', ALG) + lp(digest))) + lp(lp(cert_der)) + lp(b'')
    sig = key.sign(signed_data, padding.PKCS1v15(), hashes.SHA256())
    pub = key.public_key().public_bytes(serialization.Encoding.DER, serialization.PublicFormat.SubjectPublicKeyInfo)
    signer = lp(signed_data) + lp(lp(struct.pack('<I', ALG) + lp(sig))) + lp(pub)
    value = lp(lp(signer))
    pair = struct.pack('<QI', 4 + len(value), 0x7109871a) + value
    size = len(pair) + 8 + 16
    block = struct.pack('<Q', size) + pair + struct.pack('<Q', size) + b'APK Sig Block 42'
    new_eocd = eocd[:16] + struct.pack('<I', len(zip_entries) + len(block)) + eocd[20:]
    open(outp, 'wb').write(zip_entries + block + cd + new_eocd)

if __name__ == '__main__':
    sign(*sys.argv[1:5])
    print('signed (v2):', sys.argv[2])
