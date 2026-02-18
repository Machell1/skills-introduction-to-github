#!/usr/bin/env python3
"""
CLAWBOT Credential Manager
============================
Encrypts and stores Deriv MT5 login credentials.
Works both standalone (python credential_manager.py) and as an import.
"""

import os
import sys
import json
import hashlib
import getpass
import platform
import stat
from pathlib import Path

try:
    from cryptography.fernet import Fernet
    HAS_CRYPTO = True
except ImportError:
    HAS_CRYPTO = False

CONFIG_DIR = Path(__file__).parent.parent.resolve() / "Config"
ENV_FILE   = CONFIG_DIR / ".env.encrypted"


# ── Key derivation ───────────────────────────────────────────────────
def _machine_id() -> str:
    parts = [platform.node(), platform.machine(), platform.processor()]
    try:
        parts.append(str(os.getuid()))
    except AttributeError:
        parts.append(os.getlogin())
    return hashlib.sha256("|".join(parts).encode()).hexdigest()[:32]


def _derive_key(passphrase: str) -> bytes:
    import base64
    salt = (passphrase + _machine_id()).encode()
    raw = hashlib.pbkdf2_hmac("sha256", passphrase.encode(), salt, 100000)
    return base64.urlsafe_b64encode(raw[:32])


# ── Encrypt / decrypt ────────────────────────────────────────────────
def _encrypt(data: dict, passphrase: str) -> bytes:
    if not HAS_CRYPTO:
        import base64
        print("  [WARN] 'cryptography' not installed - using base64 only.")
        return base64.b64encode(json.dumps(data).encode())
    return Fernet(_derive_key(passphrase)).encrypt(json.dumps(data).encode())


def _decrypt(blob: bytes, passphrase: str) -> dict:
    if not HAS_CRYPTO:
        import base64
        return json.loads(base64.b64decode(blob))
    return json.loads(Fernet(_derive_key(passphrase)).decrypt(blob))


# ── Public API (imported by main.py) ─────────────────────────────────
def collect_credentials() -> dict:
    """Interactive prompt for Deriv MT5 credentials."""
    print("\n  Deriv MT5 Servers:")
    print("    1. Deriv-Demo")
    print("    2. Deriv-Server")
    print("    3. Deriv-Server-02")
    print("    4. Custom")

    server = ""
    while not server:
        c = input("\n  Select server [1-4]: ").strip()
        server = {"1": "Deriv-Demo", "2": "Deriv-Server", "3": "Deriv-Server-02"}.get(c)
        if c == "4":
            server = input("  Enter server address: ").strip()
        if not server:
            print("  Invalid choice.")

    while True:
        login = input("\n  MT5 Login ID (numeric): ").strip()
        if login.isdigit() and len(login) >= 4:
            break
        print("  Must be at least 4 digits.")

    while True:
        pw = getpass.getpass("  MT5 Password: ")
        if len(pw) >= 4:
            if getpass.getpass("  Confirm password: ") == pw:
                break
            print("  Mismatch.")
        else:
            print("  Too short.")

    return {"server": server, "login": login, "password": pw}


def setup_encryption_passphrase() -> str:
    """Prompt for a passphrase to encrypt the credential file."""
    while True:
        pp = getpass.getpass("  Encryption passphrase (>=6 chars): ")
        if len(pp) < 6:
            print("  Too short.")
            continue
        if getpass.getpass("  Confirm: ") == pp:
            return pp
        print("  Mismatch.")


def save_credentials(creds: dict, passphrase: str):
    CONFIG_DIR.mkdir(parents=True, exist_ok=True)
    ENV_FILE.write_bytes(_encrypt(creds, passphrase))
    try:
        os.chmod(ENV_FILE, stat.S_IRUSR | stat.S_IWUSR)
    except (OSError, AttributeError):
        pass
    print(f"  [OK] Credentials saved: {ENV_FILE}")


def load_credentials(passphrase: str) -> dict:
    if not ENV_FILE.exists():
        return None
    try:
        return _decrypt(ENV_FILE.read_bytes(), passphrase)
    except Exception as e:
        print(f"  [ERROR] Decrypt failed: {e}")
        return None


# ── Standalone entry ─────────────────────────────────────────────────
if __name__ == "__main__":
    print("\n  CLAWBOT Credential Manager")
    print("  " + "=" * 40)
    creds = collect_credentials()
    pp = setup_encryption_passphrase()
    save_credentials(creds, pp)
    print("\n  Done. Re-run main.py to launch live trading.")
