# -*- coding: utf-8 -*-
"""
Aghanya Devanya Enterprises - Multi-Tier Activation Key Generator Tool
Supports:
- 1 Month (30 Days)
- 2 Months (60 Days)
- 3 Months (Quarterly - 90 Days)
- 6 Months (Half-Yearly - 180 Days)
- 1 Year (Annual - 365 Days)
- Lifetime (Universal Common Key & Individual Keys)
Auto-saves to Excel (.xlsx), CSV (.csv), and text files in Activation_Keys/
"""
import os
import sys
import random
import datetime
import csv
import json

SALT = "AGHANYA_DEVANYA_2026"
CHARS = "ABCDEFGHJKLMNPQRSTUVWXYZ23456789"

TIER_CONFIGS = {
    "1": {"id": "01M", "name": "1 Month (30 Days)", "days": 30, "is_lifetime": False},
    "2": {"id": "02M", "name": "2 Months (60 Days)", "days": 60, "is_lifetime": False},
    "3": {"id": "03M", "name": "3 Months (Quarterly - 90 Days)", "days": 90, "is_lifetime": False},
    "4": {"id": "06M", "name": "6 Months (Half-Yearly - 180 Days)", "days": 180, "is_lifetime": False},
    "5": {"id": "01Y", "name": "1 Year (Annual - 365 Days)", "days": 365, "is_lifetime": False},
    "6": {"id": "LIFE", "name": "Lifetime Unlimited Access", "days": 99999, "is_lifetime": True}
}

UNIVERSAL_LIFETIME_KEY = "AD-LIFETIME-MASTER-ENTERPRISE-2026"

def compute_checksum(code: str) -> str:
    val = 5381
    for c in (code + SALT):
        val = ((val << 5) + val + ord(c)) & 0xFFFFFFFF
    return format(val, '08X')[:4]

def generate_key(tier_id: str) -> str:
    code = ''.join(random.choice(CHARS) for _ in range(4))
    csum = compute_checksum(code)
    return f"AD-{tier_id}-{code}-{csum}"

def verify_key(key: str) -> dict:
    k = key.strip().upper()
    if k in [UNIVERSAL_LIFETIME_KEY, "AD-LIFETIME-ALL-HOTELS-COMMON-KEY", "AD-LIFETIME-PRO-2026"]:
        return {"valid": True, "plan": "Lifetime Enterprise", "days": 99999, "lifetime": True}
    parts = k.split('-')
    if len(parts) == 4 and parts[0] == 'AD':
        tier, code, csum = parts[1], parts[2], parts[3]
        if csum == compute_checksum(code):
            for cfg in TIER_CONFIGS.values():
                if cfg["id"] == tier:
                    return {"valid": True, "plan": cfg["name"], "days": cfg["days"], "lifetime": cfg["is_lifetime"]}
    return {"valid": False, "plan": None, "days": 0, "lifetime": False}

def append_to_vault(new_keys_info: list):
    base_dir = os.path.dirname(os.path.abspath(__file__))
    vault_dir = os.path.join(base_dir, "Activation_Keys")
    os.makedirs(vault_dir, exist_ok=True)
    csv_path = os.path.join(vault_dir, "Aghanya_Devanya_Activation_Keys.csv")
    xlsx_path = os.path.join(vault_dir, "Aghanya_Devanya_Activation_Keys.xlsx")

    # Append to CSV
    file_exists = os.path.exists(csv_path)
    with open(csv_path, 'a', newline='', encoding='utf-8') as cf:
        writer = csv.writer(cf)
        if not file_exists:
            writer.writerow(["Sr_No", "Activation_Key", "Plan_Duration", "Days_Validity", "License_Type", "Assigned_Hotel_Name", "Status", "Notes"])
        for item in new_keys_info:
            writer.writerow([
                "NEW",
                item["key"],
                item["plan"],
                "Lifetime" if item["lifetime"] else item["days"],
                "Generated Key",
                item.get("hotel", "Unassigned"),
                "Available",
                f"Generated on {datetime.datetime.now().strftime('%Y-%m-%d %H:%M')}"
            ])

    # Also update Excel if openpyxl available
    try:
        import openpyxl
        if os.path.exists(xlsx_path):
            wb = openpyxl.load_workbook(xlsx_path)
            ws = wb["All_Keys_Master"] if "All_Keys_Master" in wb.sheetnames else wb.active
            for item in new_keys_info:
                ws.append([
                    ws.max_row,
                    item["key"],
                    item["plan"],
                    "Lifetime" if item["lifetime"] else item["days"],
                    "Generated Key",
                    item.get("hotel", "Unassigned"),
                    "Available",
                    f"Generated on {datetime.datetime.now().strftime('%Y-%m-%d %H:%M')}"
                ])
            wb.save(xlsx_path)
    except Exception:
        pass

def main():
    print("=" * 68)
    print("      AGHANYA DEVANYA ENTERPRISES — ACTIVATION KEY GENERATOR")
    print("=" * 68)
    print("Plan / Duration Options:")
    print("  [1] 1 Month   (30 Days)")
    print("  [2] 2 Months  (60 Days)")
    print("  [3] 3 Months  (Quarterly - 90 Days)")
    print("  [4] 6 Months  (Half-Yearly - 180 Days)")
    print("  [5] 1 Year    (Annual - 365 Days)")
    print("  [6] Lifetime  (Permanent Unlimited Access)")
    print("  [7] View Universal Master Lifetime Key")
    print("  [8] Re-build Full Master Excel Catalog & Vault")
    print("=" * 68)

    choice = sys.argv[1] if len(sys.argv) > 1 else input("Select Plan Option (1-8, Default 1): ").strip()
    if not choice:
        choice = "1"

    if choice == "7":
        print("\n" + "*" * 68)
        print("  UNIVERSAL COMMON LIFETIME KEY (WORKS ON ALL CONNECTED HOTELS):")
        print(f"  --> {UNIVERSAL_LIFETIME_KEY} <--")
        print("*" * 68)
        print("Note: Provide this key to any hotel for one-click lifetime permanent unlock!\n")
        return

    if choice == "8":
        import build_activation_vault
        build_activation_vault.build_vault()
        import sync_keys
        sync_keys.sync_keys()
        print("\nMaster Excel Catalog re-built & synchronized with software!")
        return

    if choice not in TIER_CONFIGS:
        choice = "1"

    cfg = TIER_CONFIGS[choice]
    count_str = sys.argv[2] if len(sys.argv) > 2 else input(f"How many keys to generate for '{cfg['name']}'? (Default 5): ").strip()
    try:
        count = int(count_str) if count_str else 5
    except ValueError:
        count = 5

    hotel_name = input("Assigned Hotel / Client Name (Optional, Press Enter to skip): ").strip()

    print(f"\nGenerating {count} keys for: {cfg['name']}...")
    generated = []
    for i in range(1, count + 1):
        k = generate_key(cfg["id"])
        item = {
            "key": k,
            "plan": cfg["name"],
            "days": cfg["days"],
            "lifetime": cfg["is_lifetime"],
            "hotel": hotel_name or "Unassigned"
        }
        generated.append(item)
        print(f"  {i:2d}. {k}  -->  {cfg['name']}")

    # Save to vault & sync
    append_to_vault(generated)
    
    # Run sync so software immediately accepts new keys
    try:
        import sync_keys
        sync_keys.sync_keys()
    except Exception:
        pass

    # Save output to text file
    ts = datetime.datetime.now().strftime('%Y%m%d_%H%M%S')
    fname = f"New-Keys-{cfg['id']}-{ts}.txt"
    with open(fname, 'w', encoding='utf-8') as f:
        f.write("=" * 68 + "\n")
        f.write(f"   AGHANYA DEVANYA ENTERPRISES — {cfg['name'].upper()}\n")
        f.write(f"   Generated on: {datetime.datetime.now().strftime('%d-%b-%Y %I:%M %p')}\n")
        if hotel_name:
            f.write(f"   Client / Hotel: {hotel_name}\n")
        f.write("=" * 68 + "\n\n")
        for i, itm in enumerate(generated, 1):
            f.write(f"{i:2d}. {itm['key']}\n")
    print(f"\nKeys successfully added to Excel/CSV and saved in: {fname}")
    print("=" * 68)

if __name__ == "__main__":
    main()
