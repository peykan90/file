#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
wifi_win.py — استخراج SSID و رمز وای‌فای‌های ذخیره‌شده در ویندوز و ذخیره در فایل txt

اجرا:
    python wifi_win.py
    python wifi_win.py -o "C:\\Users\\Public\\wifi.txt"
    python wifi_win.py --text-only        (روش جایگزین، بدون export)

روش کار:
  1) netsh wlan export profile folder=... key=clear  → خروجی XML با رمز plaintext
  2) اگر export کار نکرد: netsh wlan show profile name="..." key=clear و پارس متن
"""

import argparse
import ctypes
import datetime
import os
import platform
import re
import shutil
import subprocess
import sys
import tempfile
import xml.etree.ElementTree as ET

DEFAULT_OUT = "wifi_passwords.txt"
CREATE_NO_WINDOW = 0x08000000

KEY_LABELS = ("key content", "محتوای کلید", "محتویات کلید", "رمز عبور", "پسورد")
SKIP_VALUES = {"present", "absent", "not present", "موجود", "ناموجود", ""}


# ----------------------------------------------------------------- ابزارها

def decode_console(data: bytes) -> str:
    """خروجی netsh با کدپیج کنسول ویندوز برمی‌گردد، نه UTF-8"""
    if not data:
        return ""
    candidates = []
    try:
        cp = ctypes.windll.kernel32.GetConsoleOutputCP() or 437
        candidates.append("cp%d" % cp)
    except Exception:
        pass
    candidates += ["utf-8", "cp1256", "cp437", "mbcs"]

    for enc in candidates:
        try:
            return data.decode(enc)
        except (UnicodeDecodeError, LookupError):
            continue
    return data.decode("utf-8", "replace")


def netsh(*args, timeout=45) -> str:
    """اجرای netsh و برگرداندن خروجی متنی"""
    try:
        proc = subprocess.run(
            ["netsh", *args],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            stdin=subprocess.DEVNULL,
            timeout=timeout,
            creationflags=CREATE_NO_WINDOW,
        )
        return decode_console(proc.stdout)
    except (OSError, subprocess.SubprocessError):
        return ""


def short_path(path: str) -> str:
    """مسیر کوتاه 8.3 برای دور زدن مشکل فاصله در آرگومان folder="""
    try:
        buf = ctypes.create_unicode_buffer(260)
        if ctypes.windll.kernel32.GetShortPathNameW(path, buf, 260):
            value = buf.value
            if value and " " not in value:
                return value
    except Exception:
        pass
    return path


def hex_to_text(hex_str: str) -> str:
    try:
        raw = bytes.fromhex(hex_str)
    except ValueError:
        return ""
    raw = raw.replace(b"\x00", b"")
    for enc in ("utf-8", "cp1256", "latin-1"):
        try:
            return raw.decode(enc).strip()
        except UnicodeDecodeError:
            continue
    return raw.decode("utf-8", "replace").strip()


# ------------------------------------------------------- روش ۱: export به XML

def xml_text(root, path: str, default: str = "") -> str:
    node = root.find(path)
    if node is None or node.text is None:
        return default
    return node.text.strip()


def parse_profile_xml(root):
    profile = xml_text(root, "name")
    ssid = xml_text(root, "SSIDConfig/SSID/name")
    if not ssid:
        ssid = hex_to_text(xml_text(root, "SSIDConfig/SSID/hex"))
    if not ssid:
        ssid = profile
    if not ssid:
        return None

    key = xml_text(root, "MSM/security/sharedKey/keyMaterial")
    protected = xml_text(root, "MSM/security/sharedKey/protected").lower()
    if protected == "true":
        key = ""   # رمز رمزنگاری‌شده مانده (export با key=clear انجام نشده)

    auth = xml_text(root, "MSM/security/authEncryption/authentication")
    enc = xml_text(root, "MSM/security/authEncryption/encryption")
    security = " ".join(x for x in (auth, enc) if x)

    return {
        "ssid": ssid,
        "password": key,
        "security": security,
        "profile": profile or ssid,
        "source": "export",
    }


def via_export():
    items = []
    tmpdir = tempfile.mkdtemp(prefix="wifiexport_")
    try:
        target = short_path(tmpdir)
        netsh("wlan", "export", "profile", "folder=%s" % target, "key=clear")
        found = [f for _, _, files in os.walk(tmpdir) for f in files if f.lower().endswith(".xml")]
        if not found:
            # تلاش دوم با کوتیشن
            netsh("wlan", "export", "profile", 'folder="%s"' % tmpdir, "key=clear")

        for root_dir, _, files in os.walk(tmpdir):
            for name in files:
                if not name.lower().endswith(".xml"):
                    continue
                path = os.path.join(root_dir, name)
                try:
                    root = ET.parse(path).getroot()
                except (ET.ParseError, OSError):
                    continue
                data = parse_profile_xml(root)
                if data:
                    items.append(data)
    finally:
        shutil.rmtree(tmpdir, ignore_errors=True)
    return items


# --------------------------------------------- روش ۲: پارس خروجی متنی netsh

def profile_names(text: str):
    """نام پروفایل‌ها را مستقل از زبان ویندوز برمی‌دارد (هر خط «... : مقدار»)"""
    names = []
    for line in text.splitlines():
        if ":" not in line:
            continue
        value = line.rsplit(":", 1)[1].strip().strip('"').strip()
        if value and value not in names:
            names.append(value)
    return names


def parse_profile_text(text: str):
    info = {"ssid": "", "password": "", "security": "", "profile": "", "source": "netsh"}
    for raw in text.splitlines():
        if ":" not in raw:
            continue
        label, _, value = raw.partition(":")
        label = label.strip().lower()
        value = value.strip().strip('"').strip()
        if not value:
            continue

        if "ssid" in label and not info["ssid"]:
            info["ssid"] = value
        elif not info["password"] and any(k in label for k in KEY_LABELS):
            if value.lower() not in SKIP_VALUES:
                info["password"] = value
        elif not info["password"] and "کلید" in label and "امنیتی" not in label:
            if value not in SKIP_VALUES:
                info["password"] = value
        elif not info["security"] and ("authentication" in label or "احراز هویت" in label):
            info["security"] = value

    if not info["security"]:
        match = re.search(r"WPA[0-9]?(?:[-/ ]?(?:Personal|Enterprise))?", text, re.I)
        if match:
            info["security"] = match.group(0)
    return info


def via_text():
    results = []
    for name in profile_names(netsh("wlan", "show", "profiles")):
        if '"' in name:
            continue
        detail = netsh("wlan", "show", "profile", 'name="%s"' % name, "key=clear")
        if ":" not in detail:
            continue
        info = parse_profile_text(detail)
        if not info["ssid"] and not info["password"]:
            continue
        info["profile"] = name
        results.append(info)
    return results


# ------------------------------------------------------------------ خروجی

def dedupe(items):
    seen, out = set(), []
    for item in items:
        key = (item["ssid"], item["password"])
        if item["ssid"] and key not in seen:
            seen.add(key)
            out.append(item)
    out.sort(key=lambda x: x["ssid"].lower())
    return out


def build_report(items) -> str:
    now = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    lines = [
        "WiFi Passwords Report (Windows)",
        "Host      : %s" % platform.node(),
        "User      : %s" % os.environ.get("USERNAME", "?"),
        "Generated : %s" % now,
        "Networks  : %d" % len(items),
        "",
        "=" * 62,
        "",
    ]
    for item in items:
        lines.append("SSID      : %s" % item["ssid"])
        lines.append("Password  : %s" % (item["password"] or "(بدون رمز / نامشخص)"))
        if item["security"]:
            lines.append("Security  : %s" % item["security"])
        lines.append("Profile   : %s" % item["profile"])
        lines.append("-" * 62)

    if not items:
        lines.append("هیچ پروفایل وای‌فای ذخیره‌شده‌ای پیدا نشد.")
        lines.append("نکته: CMD را با Run as administrator اجرا کنید.")

    return "\n".join(lines) + "\n"


def main():
    parser = argparse.ArgumentParser(
        description="ذخیره SSID و رمز وای‌فای‌های ذخیره‌شده ویندوز در فایل txt"
    )
    parser.add_argument("-o", "--output", default=DEFAULT_OUT, help="مسیر فایل خروجی")
    parser.add_argument("--text-only", action="store_true", help="بدون export، فقط پارس خروجی netsh")
    args = parser.parse_args()

    if os.name != "nt":
        print("این اسکریپت مخصوص ویندوز است (netsh لازم دارد).")
        return 1

    items = []
    if not args.text_only:
        items = via_export()
    if not items:
        items = via_text()

    items = dedupe(items)
    report = build_report(items)

    try:
        with open(args.output, "w", encoding="utf-8-sig") as fh:
            fh.write(report)
    except OSError as exc:
        print("خطا در نوشتن فایل: %s" % exc)
        return 1

    print(report)
    print("ذخیره شد در: %s" % os.path.abspath(args.output))
    if not items:
        print("اگر خروجی خالی بود، اسکریپت را با دسترسی Administrator اجرا کنید.")
    return 0


if __name__ == "__main__":
    sys.exit(main())