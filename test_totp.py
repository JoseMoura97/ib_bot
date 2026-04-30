import pyotp, time
s = "3LIWICNOAIU3D6WOL3627WN3A3HGDEBP"
t = int(time.time())
r = 30 - (t % 30)
print("Server time:", t, "Remaining:", r)
print("SHA1:", pyotp.TOTP(s).now())
print("SHA256:", pyotp.TOTP(s, digest="sha256").now())
print("SHA512:", pyotp.TOTP(s, digest="sha512").now())
