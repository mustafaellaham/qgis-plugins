# -*- coding: utf-8 -*-
"""
FTTH Labeler — License Checker
==============================
Validates plugin expiration and detects system clock tampering.

Tamper detection method:
- Stores first-use date and last-use date in QSettings
- If current date < last-use date → user rolled back clock → LOCKED
- If current date < first-use date → user rolled back clock → LOCKED
- All dates are stored with a simple hash to prevent manual editing
"""

import hashlib
from datetime import datetime, timedelta
from qgis.PyQt.QtCore import QSettings

from .config import EXPIRATION_DATE, CONTACT_NAME, CONTACT_EMAIL, WARNING_DAYS


# Settings keys (obfuscated names to deter casual tampering)
_S_FIRST = "ftth_labeler/_init_ts"
_S_LAST = "ftth_labeler/_last_ts"
_S_WARN = "ftth_labeler/_warn_shown"


def _hash_date(date_str):
    """Simple hash to detect manual editing of stored dates."""
    return hashlib.md5(f"{date_str}::FTTH".encode()).hexdigest()[:12]


def _store_date(key, date_obj):
    """Store a date with its hash."""
    date_str = date_obj.strftime("%Y%m%d")
    QSettings().setValue(key, f"{date_str}:{_hash_date(date_str)}")


def _read_date(key):
    """Read a stored date. Returns datetime or None if tampered/missing."""
    try:
        raw = QSettings().value(key, "")
        if not raw or ":" not in raw:
            return None
        date_str, stored_hash = raw.split(":", 1)
        if _hash_date(date_str) != stored_hash:
            return "TAMPERED"
        return datetime.strptime(date_str, "%Y%m%d")
    except Exception:
        return None


def check_license():
    """
    Check if the plugin license is valid.

    Returns:
        (is_valid: bool, message: str, days_left: int or None)
        is_valid = True  → plugin can run
        is_valid = False → plugin is locked, message explains why
    """
    # --- No expiration set → always valid ---
    if not EXPIRATION_DATE or not EXPIRATION_DATE.strip():
        return True, "No expiration configured", None

    # --- Parse expiry date ---
    try:
        expiry = datetime.strptime(EXPIRATION_DATE.strip(), "%Y-%m-%d")
    except ValueError:
        return False, f"Invalid expiration date in config: {EXPIRATION_DATE}", None

    today = datetime.now()

    # --- Tamper detection: check stored dates ---
    first_use = _read_date(_S_FIRST)
    last_use = _read_date(_S_LAST)

    if first_use == "TAMPERED" or last_use == "TAMPERED":
        return False, (
            f"License validation failed: settings appear to have been modified.\n\n"
            f"Contact {CONTACT_NAME} at {CONTACT_EMAIL} for support."
        ), None

    # Clock rolled back: today is before first-use date
    if first_use and today.date() < first_use.date():
        return False, (
            f"License validation failed: system clock appears to have been rolled back.\n"
            f"First use was recorded on {first_use.strftime('%Y-%m-%d')}.\n\n"
            f"Contact {CONTACT_NAME} at {CONTACT_EMAIL} for support."
        ), None

    # Clock rolled back: today is before last-use date
    if last_use and today.date() < last_use.date():
        return False, (
            f"License validation failed: system clock appears to have been rolled back.\n"
            f"Last use was recorded on {last_use.strftime('%Y-%m-%d')}.\n\n"
            f"Contact {CONTACT_NAME} at {CONTACT_EMAIL} for support."
        ), None

    # Record/update usage dates
    if not first_use:
        _store_date(_S_FIRST, today)
    _store_date(_S_LAST, today)

    # --- Check expiration ---
    if today.date() > expiry.date():
        return False, (
            f"Plugin license expired on {EXPIRATION_DATE}.\n\n"
            f"Contact {CONTACT_NAME} at {CONTACT_EMAIL} to renew your license."
        ), 0

    # --- Calculate days left ---
    days_left = (expiry.date() - today.date()).days

    return True, "License valid", days_left


def clear_license_data():
    """Clear all stored license data. Call this when uninstalling."""
    s = QSettings()
    s.remove(_S_FIRST)
    s.remove(_S_LAST)
    s.remove(_S_WARN)
