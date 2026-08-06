import hashlib
import hmac
import base64
import struct
import time
from datetime import datetime, timezone

secret_b32 = "4I4JJXXFCFQYIGKAGHMDTCM7V7IFBGJK"
key = base64.b32decode(secret_b32, casefold=True)

# signature observed for goals/check-in
target = "05b1d79812e65520b73d00f1c6c85d2524780cc4fd70ee13d3f07ed2318d03feb9b29bb2a8c5f6eb90e127540658b407fff4bb234b903b0f7969e54ecac4f01d"
# signature observed for goals/main (later)
target2 = "814fa6afd946efa24054b93f6dffdffa8e358f409e8996de609e5307016aed0bd757163ca7793af71bad49defd2c57c50a39fab45746cd1c5588a98fa17aac99"
# signature for user/card x3
target3 = "d1e4265a508535bfd33c568310db2fc1634725768644831b1cc5019a7569b39c1b09eecf5b89297d09cb880f6964a1956d463ae5742fcb806df9d34a6209b938"
# totp/generate request signature (computed with previous/persistent secret)
target0 = "c4d294fb115f0354772f1c548c923b8d9bc643564f4273bef197117f4594b66f2c26f8c8fc2fcb18b538428a8d4dc211838c086447662db6fc8a55d02cdf1142"

def totp(timestamp, period=300, length=6, algo=hashlib.sha1):
    counter = int(timestamp) // period
    msg = struct.pack(">Q", counter)
    digest = hmac.new(key, msg, algo).digest()
    offset = digest[-1] & 0x0F
    value = (struct.unpack(">I", digest[offset:offset+4])[0] & 0x7FFFFFFF) % (10 ** length)
    return str(value).zfill(length)

# rough timestamps (unix seconds): otp/check at ~1785996590 (from JWT iat), check-in a few sec later
for ts in [1785996590, 1785996593, 1785996595, 1785996600, 1785996620, 1785996650, 1785996700]:
    code = totp(ts)
    counter = ts // 300
    cands = {
        "hmac_sha512_key=counter": hmac.new(key, str(counter).encode(), hashlib.sha512).hexdigest(),
        "hmac_sha512_key=counter_bin": hmac.new(key, struct.pack(">Q", counter), hashlib.sha512).hexdigest(),
        "hmac_sha512_key=code": hmac.new(key, code.encode(), hashlib.sha512).hexdigest(),
        "hmac_sha512_key=code,txt=counter": hmac.new(code.encode(), str(counter).encode(), hashlib.sha512).hexdigest(),
        "hmac_sha512_key=secretB32": hmac.new(secret_b32.encode(), str(counter).encode(), hashlib.sha512).hexdigest(),
        "hmac_sha512_key=secretB32,msg=code": hmac.new(secret_b32.encode(), code.encode(), hashlib.sha512).hexdigest(),
        "hmac_sha512_key=code,msg=secretB32": hmac.new(code.encode(), secret_b32.encode(), hashlib.sha512).hexdigest(),
        "sha512_code": hashlib.sha512(code.encode()).hexdigest(),
        "sha512_counter": hashlib.sha512(str(counter).encode()).hexdigest(),
        "sha512_key+counter": hashlib.sha512(key + str(counter).encode()).hexdigest(),
        "sha512_key_b32+counter": hashlib.sha512(secret_b32.encode() + str(counter).encode()).hexdigest(),
        "hmac_sha256_twice": hashlib.sha512(hmac.new(key, str(counter).encode(), hashlib.sha256).hexdigest().encode()).hexdigest(),
    }
    for name, val in cands.items():
        if val in (target, target2, target3, target0):
            print(f"MATCH ts={ts} {name}")

print("--- no match demo: show a couple of computed values ---")
ts = 1785996595
print("counter", ts//300, "totp", totp(ts))
