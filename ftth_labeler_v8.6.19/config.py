# -*- coding: utf-8 -*-
"""
FTTH Labeler — License Configuration
====================================
EDIT THIS FILE before packaging the plugin for each user.

How to use:
1. Open this file
2. Change EXPIRATION_DATE to the desired expiry date
3. Save and ZIP the plugin
4. Share the ZIP — the date is locked inside

Examples:
  "2026-06-30"  → 1 month trial
  "2026-12-31"  → 6 month license
  "2028-12-31"  → 2 year license
  ""             → no expiration (leave empty for permanent)
"""

# ============================================================
# EXPIRATION DATE — CHANGE THIS BEFORE SHARING
# Format: "YYYY-MM-DD" or "" for no expiration
# ============================================================
EXPIRATION_DATE = "2026-12-31"

# Contact info shown in expiry messages
CONTACT_NAME = "Mustafa M M Ellaham"
CONTACT_EMAIL = "Mustafaellaham@gmail.com"

# Warning threshold (days before expiry to show warning)
WARNING_DAYS = 30
