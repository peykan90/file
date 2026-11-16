import random
import time
import os

chars = "01アイウエオカキクケコ"

while True:
    line = "".join(random.choice(chars) for _ in range(80))
    print("\033[92m" + line + "\033[0m")
    time.sleep(0.05)