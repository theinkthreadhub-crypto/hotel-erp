# -*- coding: utf-8 -*-
"""
Sync Activation Keys Tool for Aghanya Devanya Enterprises:
Reads custom and pre-filled keys from Excel (.xlsx) or CSV (.csv) in Activation_Keys/
and synchronizes them into hotel_erp.html and standalone desktop files.
"""
import os
import csv
import json
import re

def sync_keys():
    base_dir = os.path.dirname(os.path.abspath(__file__))
    vault_dir = os.path.join(base_dir, "Activation_Keys")
    xlsx_path = os.path.join(vault_dir, "Aghanya_Devanya_Activation_Keys.xlsx")
    csv_path = os.path.join(vault_dir, "Aghanya_Devanya_Activation_Keys.csv")
    html_path = os.path.join(base_dir, "hotel_erp.html")

    print("=" * 65)
    print("   AGHANYA DEVANYA ENTERPRISES — ACTIVATION KEY SYNC ENGINE")
    print("=" * 65)

    catalog = []
    seen_keys = set()

    # Priority 1: Try reading Excel if openpyxl is available
    excel_loaded = False
    if os.path.exists(xlsx_path):
        try:
            import openpyxl
            wb = openpyxl.load_workbook(xlsx_path, data_only=True)
            # Read from All_Keys_Master or first sheet
            ws = wb["All_Keys_Master"] if "All_Keys_Master" in wb.sheetnames else wb.active
            for row in ws.iter_rows(min_row=2, values_only=True):
                if not row or not row[1]:
                    continue
                k = str(row[1]).strip().upper()
                plan = str(row[2] or "Custom").strip()
                days_val = row[3]
                try:
                    days = int(days_val) if days_val and str(days_val).isdigit() else (99999 if "LIFE" in plan.upper() else 30)
                except ValueError:
                    days = 99999 if "LIFE" in plan.upper() else 30
                hotel = str(row[5] or "").strip()
                status = str(row[6] or "Available").strip()
                if k and k not in seen_keys:
                    seen_keys.add(k)
                    catalog.append({
                        "key": k,
                        "plan": plan,
                        "days": days,
                        "is_lifetime": days >= 99999 or "LIFE" in k or "LIFE" in plan.upper(),
                        "hotel": hotel,
                        "status": status
                    })
            excel_loaded = True
            print(f"Loaded {len(catalog)} keys directly from Excel: {os.path.basename(xlsx_path)}")
        except Exception as e:
            print(f"Note: Excel read skipped ({e}), falling back to CSV.")

    # Priority 2: Fallback or supplement from CSV
    if not excel_loaded and os.path.exists(csv_path):
        with open(csv_path, 'r', encoding='utf-8', errors='ignore') as f:
            reader = csv.reader(f)
            header = next(reader, None)
            for row in reader:
                if not row or len(row) < 2 or not row[1].strip():
                    continue
                k = row[1].strip().upper()
                plan = row[2].strip() if len(row) > 2 else "Custom"
                days_raw = row[3].strip() if len(row) > 3 else "30"
                days = 99999 if "LIFE" in days_raw.upper() or "LIFE" in plan.upper() or "LIFE" in k else (int(days_raw) if days_raw.isdigit() else 30)
                hotel = row[5].strip() if len(row) > 5 else ""
                status = row[6].strip() if len(row) > 6 else "Available"
                if k and k not in seen_keys:
                    seen_keys.add(k)
                    catalog.append({
                        "key": k,
                        "plan": plan,
                        "days": days,
                        "is_lifetime": days >= 99999 or "LIFE" in k or "LIFE" in plan.upper(),
                        "hotel": hotel,
                        "status": status
                    })
        print(f"Loaded {len(catalog)} keys from CSV: {os.path.basename(csv_path)}")

    # Add universal master keys if not present
    universal_keys = [
        ("AD-LIFETIME-MASTER-ENTERPRISE-2026", "Lifetime Universal Master"),
        ("AD-LIFETIME-ALL-HOTELS-COMMON-KEY", "Lifetime Common Key"),
        ("AD-LIFETIME-PRO-2026", "Lifetime Professional"),
        ("AD-LIFETIME-HOTEL-ERP-VIP", "Lifetime VIP Key")
    ]
    for uk, pname in universal_keys:
        if uk not in seen_keys:
            seen_keys.add(uk)
            catalog.append({
                "key": uk,
                "plan": pname,
                "days": 99999,
                "is_lifetime": True,
                "hotel": "Common (All Hotels)",
                "status": "Universal"
            })

    # Save to synced JSON
    synced_json_path = os.path.join(vault_dir, "synced_keys.json")
    with open(synced_json_path, 'w', encoding='utf-8') as f:
        json.dump(catalog, f, indent=2)

    # Now update hotel_erp.html with this master catalog
    if os.path.exists(html_path):
        with open(html_path, 'r', encoding='utf-8') as f:
            html = f.read()

        # Build replacement JS code
        key_list_json = json.dumps([item["key"] for item in catalog], indent=2)
        catalog_compact = json.dumps({item["key"]: {"days": item["days"], "plan": item["plan"], "lifetime": item["is_lifetime"]} for item in catalog})

        pattern = r"const PREINSTALLED_KEYS = \[[\s\S]*?\];\s*(?:const VAULT_KEY_MAP = \{[\s\S]*?\};)?"
        replacement = f"const PREINSTALLED_KEYS = {key_list_json};\nconst VAULT_KEY_MAP = {catalog_compact};"

        if re.search(pattern, html):
            html = re.sub(pattern, replacement, html, count=1)
            with open(html_path, 'w', encoding='utf-8') as f:
                f.write(html)
            print(f"Successfully synchronized {len(catalog)} keys into hotel_erp.html!")
        else:
            print("Warning: Could not find PREINSTALLED_KEYS marker in hotel_erp.html")

    print("\nSync completed successfully!")
    print(f"Total synchronized keys: {len(catalog)}")
    print("=" * 65)

if __name__ == "__main__":
    sync_keys()
