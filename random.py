import random
import string

chars = string.ascii_letters + string.digits + "!@#$%^&*"

length = int(input("طول رمز را وارد کن: "))

password = "".join(random.choice(chars) for _ in range(length))

print("رمز اختصاصی تو:")
print(password)