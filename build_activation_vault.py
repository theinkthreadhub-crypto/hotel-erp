# -*- coding: utf-8 -*-
"""
Build the complete Activation Keys Vault for Aghanya Devanya Enterprises:
- Generates pre-filled keys for:
  * 1 Month (30 Days)
  * 2 Months (60 Days)
  * 3 Months (90 Days - Quarterly)
  * 6 Months (180 Days - Half-Yearly)
  * 1 Year (365 Days - Annual)
  * Lifetime (Universal Master Key + Individual Lifetime Keys)
- Outputs to:
  * Activation_Keys/Aghanya_Devanya_Activation_Keys.xlsx (Multi-sheet styled Excel workbook)
  * Activation_Keys/Aghanya_Devanya_Activation_Keys.csv
  * Category text files (1_Month_Keys.txt, etc.)
  * Synced JSON database
"""
import os
import random
import csv
import json
import openpyxl
from openpyxl.styles import Font, PatternFill, Alignment, Border, Side
from openpyxl.utils import get_column_letter

SALT = "AGHANYA_DEVANYA_2026"
CHARS = "ABCDEFGHJKLMNPQRSTUVWXYZ23456789"

TIERS = [
    {
        "id": "01M",
        "name": "1 Month (30 Days)",
        "duration_label": "30 Days",
        "days": 30,
        "is_lifetime": False,
        "prefix": "AD-01M-",
        "count": 25
    },
    {
        "id": "02M",
        "name": "2 Months (60 Days)",
        "duration_label": "60 Days",
        "days": 60,
        "is_lifetime": False,
        "prefix": "AD-02M-",
        "count": 25
    },
    {
        "id": "03M",
        "name": "3 Months (Quarterly)",
        "duration_label": "90 Days",
        "days": 90,
        "is_lifetime": False,
        "prefix": "AD-03M-",
        "count": 25
    },
    {
        "id": "06M",
        "name": "6 Months (Half-Yearly)",
        "duration_label": "180 Days",
        "days": 180,
        "is_lifetime": False,
        "prefix": "AD-06M-",
        "count": 25
    },
    {
        "id": "01Y",
        "name": "1 Year (Annual)",
        "duration_label": "365 Days",
        "days": 365,
        "is_lifetime": False,
        "prefix": "AD-01Y-",
        "count": 25
    },
    {
        "id": "LIFE",
        "name": "Lifetime Unlimited Access",
        "duration_label": "Lifetime (No Expiry)",
        "days": 99999,
        "is_lifetime": True,
        "prefix": "AD-LIFE-",
        "count": 25
    }
]

UNIVERSAL_LIFETIME_KEYS = [
    "AD-LIFETIME-MASTER-ENTERPRISE-2026",
    "AD-LIFETIME-ALL-HOTELS-COMMON-KEY",
    "AD-LIFETIME-PRO-2026",
    "AD-LIFETIME-HOTEL-ERP-VIP"
]

def compute_checksum(code: str) -> str:
    val = 5381
    for c in (code + SALT):
        val = ((val << 5) + val + ord(c)) & 0xFFFFFFFF
    return format(val, '08X')[:4]

def generate_key_for_tier(tier_id: str) -> str:
    code = ''.join(random.choice(CHARS) for _ in range(4))
    csum = compute_checksum(code)
    return f"AD-{tier_id}-{code}-{csum}"

def build_vault():
    vault_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), "Activation_Keys")
    os.makedirs(vault_dir, exist_ok=True)
    
    random.seed(2026)  # reproducible master catalog
    master_catalog = []
    keys_by_tier = {}

    # 1. Add Universal Common Lifetime Keys first
    for ukey in UNIVERSAL_LIFETIME_KEYS:
        item = {
            "key": ukey,
            "tier_id": "LIFE",
            "tier_name": "Lifetime Unlimited Access",
            "duration": "Lifetime (Common Master Key for All Hotels)",
            "days": 99999,
            "is_lifetime": True,
            "type": "Universal Common Key",
            "assigned_hotel": "Common (Any Hotel)",
            "status": "Available / Reusable"
        }
        master_catalog.append(item)
        keys_by_tier.setdefault("LIFE", []).append(item)

    # 2. Generate pre-filled keys for each tier
    used_codes = set()
    for t in TIERS:
        t_id = t["id"]
        for _ in range(t["count"]):
            while True:
                code = ''.join(random.choice(CHARS) for _ in range(4))
                if code not in used_codes:
                    used_codes.add(code)
                    break
            csum = compute_checksum(code)
            k = f"AD-{t_id}-{code}-{csum}"
            item = {
                "key": k,
                "tier_id": t_id,
                "tier_name": t["name"],
                "duration": t["duration_label"],
                "days": t["days"],
                "is_lifetime": t["is_lifetime"],
                "type": "Single Hotel Unique Key",
                "assigned_hotel": "Unassigned",
                "status": "Available"
            }
            master_catalog.append(item)
            keys_by_tier.setdefault(t_id, []).append(item)

    # 3. Create CSV Master File
    csv_path = os.path.join(vault_dir, "Aghanya_Devanya_Activation_Keys.csv")
    with open(csv_path, 'w', newline='', encoding='utf-8') as cf:
        writer = csv.writer(cf)
        writer.writerow(["Sr_No", "Activation_Key", "Plan_Duration", "Days_Validity", "License_Type", "Assigned_Hotel_Name", "Status", "Notes"])
        for idx, item in enumerate(master_catalog, 1):
            writer.writerow([
                idx,
                item["key"],
                item["tier_name"],
                item["days"] if not item["is_lifetime"] else "Lifetime",
                item["type"],
                item["assigned_hotel"],
                item["status"],
                "Official key by Aghanya Devanya Enterprises"
            ])

    # 4. Create Multi-Sheet Styled Excel Workbook
    wb = openpyxl.Workbook()
    # Remove default sheet
    default_sheet = wb.active
    wb.remove(default_sheet)

    navy_fill = PatternFill(start_color="0F172A", end_color="0F172A", fill_type="solid")
    gold_fill = PatternFill(start_color="D97706", end_color="D97706", fill_type="solid")
    blue_fill = PatternFill(start_color="0284C7", end_color="0284C7", fill_type="solid")
    light_fill = PatternFill(start_color="F8FAFC", end_color="F8FAFC", fill_type="solid")
    white_font = Font(name="Calibri", size=11, bold=True, color="FFFFFF")
    bold_font = Font(name="Calibri", size=11, bold=True, color="0F172A")
    regular_font = Font(name="Calibri", size=11, color="1E293B")
    mono_font = Font(name="Consolas", size=11, bold=True, color="0369A1")
    center_align = Alignment(horizontal="center", vertical="center")
    left_align = Alignment(horizontal="left", vertical="center")
    thin_border = Border(
        left=Side(style='thin', color='E2E8F0'),
        right=Side(style='thin', color='E2E8F0'),
        top=Side(style='thin', color='E2E8F0'),
        bottom=Side(style='thin', color='E2E8F0')
    )

    # Sheet A: Master Catalog (All Keys)
    ws_master = wb.create_sheet(title="All_Keys_Master")
    headers = ["Sr No", "Activation Key", "Plan Duration", "Days", "Type", "Assigned Hotel", "Status", "Notes"]
    ws_master.append(headers)
    for col_num in range(1, len(headers) + 1):
        cell = ws_master.cell(row=1, column=col_num)
        cell.fill = navy_fill
        cell.font = white_font
        cell.alignment = center_align

    for idx, item in enumerate(master_catalog, 1):
        ws_master.append([
            idx,
            item["key"],
            item["tier_name"],
            item["days"] if not item["is_lifetime"] else "Lifetime",
            item["type"],
            item["assigned_hotel"],
            item["status"],
            "Aghanya Devanya License"
        ])
        r = idx + 1
        ws_master.cell(row=r, column=1).alignment = center_align
        ws_master.cell(row=r, column=2).font = mono_font
        ws_master.cell(row=r, column=4).alignment = center_align
        ws_master.cell(row=r, column=7).alignment = center_align
        for c in range(1, len(headers) + 1):
            ws_master.cell(row=r, column=c).border = thin_border
            if idx % 2 == 0:
                ws_master.cell(row=r, column=c).fill = light_fill

    # Sheet B: Individual Sheets for each Tier
    sheet_configs = [
        ("1_Month_Keys", "01M", blue_fill),
        ("2_Months_Keys", "02M", blue_fill),
        ("3_Months_Quarterly", "03M", blue_fill),
        ("6_Months_HalfYearly", "06M", blue_fill),
        ("1_Year_Annual", "01Y", blue_fill),
        ("Lifetime_Master_Keys", "LIFE", gold_fill)
    ]

    for sheet_title, tier_id, fill_color in sheet_configs:
        ws = wb.create_sheet(title=sheet_title)
        ws.append(headers)
        for col_num in range(1, len(headers) + 1):
            cell = ws.cell(row=1, column=col_num)
            cell.fill = fill_color
            cell.font = white_font
            cell.alignment = center_align
        
        tier_items = keys_by_tier.get(tier_id, [])
        for idx, item in enumerate(tier_items, 1):
            ws.append([
                idx,
                item["key"],
                item["tier_name"],
                item["days"] if not item["is_lifetime"] else "Lifetime",
                item["type"],
                item["assigned_hotel"],
                item["status"],
                "Aghanya Devanya Enterprises"
            ])
            r = idx + 1
            ws.cell(row=r, column=1).alignment = center_align
            ws.cell(row=r, column=2).font = mono_font
            ws.cell(row=r, column=4).alignment = center_align
            ws.cell(row=r, column=7).alignment = center_align
            for c in range(1, len(headers) + 1):
                ws.cell(row=r, column=c).border = thin_border
                if idx % 2 == 0:
                    ws.cell(row=r, column=c).fill = light_fill

    # Auto-fit columns across all sheets
    for sheet in wb.worksheets:
        sheet.row_dimensions[1].height = 26
        for col in sheet.columns:
            max_len = max(len(str(cell.value or '')) for cell in col)
            col_letter = get_column_letter(col[0].column)
            sheet.column_dimensions[col_letter].width = max(max_len + 4, 12)

    xlsx_path = os.path.join(vault_dir, "Aghanya_Devanya_Activation_Keys.xlsx")
    wb.save(xlsx_path)

    # 5. Output individual text files for quick copy-pasting
    text_file_map = {
        "01M": "1_Month_Keys.txt",
        "02M": "2_Months_Keys.txt",
        "03M": "3_Months_Quarterly_Keys.txt",
        "06M": "6_Months_HalfYearly_Keys.txt",
        "01Y": "1_Year_Annual_Keys.txt",
        "LIFE": "Lifetime_Keys.txt"
    }

    for tid, fname in text_file_map.items():
        fpath = os.path.join(vault_dir, fname)
        items = keys_by_tier.get(tid, [])
        with open(fpath, 'w', encoding='utf-8') as tf:
            tf.write("=" * 65 + "\n")
            tf.write(f"   AGHANYA DEVANYA ENTERPRISES — {items[0]['tier_name'].upper()}\n")
            tf.write("=" * 65 + "\n\n")
            if tid == "LIFE":
                tf.write(">>> UNIVERSAL MASTER LIFETIME KEY (WORKS FOR ALL HOTELS) <<<\n")
                tf.write("    AD-LIFETIME-MASTER-ENTERPRISE-2026\n")
                tf.write("    (You can provide this single master key to any hotel for permanent lifetime access!)\n\n")
                tf.write("-" * 65 + "\n")
                tf.write(">>> INDIVIDUAL UNIQUE LIFETIME KEYS (1 PER HOTEL) <<<\n\n")
            for idx, itm in enumerate(items, 1):
                tf.write(f"{idx:2d}. {itm['key']}  -->  {itm['duration']}\n")

    # 6. Create JSON file for direct software embedding
    json_path = os.path.join(vault_dir, "activation_keys.json")
    with open(json_path, 'w', encoding='utf-8') as jf:
        json.dump({
            "universal_lifetime_keys": UNIVERSAL_LIFETIME_KEYS,
            "catalog": master_catalog
        }, jf, indent=2)

    # 7. Create README instructions in the folder
    readme_path = os.path.join(vault_dir, "HOW_TO_USE_KEYS.txt")
    with open(readme_path, 'w', encoding='utf-8') as rf:
        rf.write("====================================================================\n")
        rf.write("      AGHANYA DEVANYA ENTERPRISES — ACTIVATION KEY VAULT GUIDE\n")
        rf.write("====================================================================\n\n")
        rf.write("Aapke paas alag-alag plans ke liye activation keys is folder mein hain:\n\n")
        rf.write("1. EXCEL SPREADSHEET:\n")
        rf.write("   - 'Aghanya_Devanya_Activation_Keys.xlsx' ko Microsoft Excel mein kholein.\n")
        rf.write("   - Isme alag-alag tabs bane hain: 1 Month, 2 Months, 3 Months, 6 Months, 1 Year, Lifetime.\n")
        rf.write("   - Aap isme 'Assigned Hotel' column mein hotel ka naam note kar sakte hain.\n\n")
        rf.write("2. CSV FORMAT:\n")
        rf.write("   - 'Aghanya_Devanya_Activation_Keys.csv' ko bhi Excel ya Notepad mein edit kar sakte hain.\n\n")
        rf.write("3. TEXT FILES:\n")
        rf.write("   - Har duration ke liye alag text file hai jahan se aap direct key copy kar sakte hain.\n\n")
        rf.write("4. UNIVERSAL COMMON LIFETIME KEY:\n")
        rf.write("   - Sabhi hotels ke liye permanent lifetime key:\n")
        rf.write("     AD-LIFETIME-MASTER-ENTERPRISE-2026\n")
        rf.write("   - Jab bhi kisi ko Lifetime dena ho, ye key sabhi hotels par kaam karegi.\n\n")
        rf.write("5. SYNC WITH SOFTWARE:\n")
        rf.write("   - Jab bhi aap nayi keys add karein ya change karein, 'Sync-Activation-Keys.bat' chalayein.\n\n")

    print(f"Vault successfully created at: {vault_dir}")
    print(f"Total keys generated: {len(master_catalog)}")

if __name__ == "__main__":
    build_vault()
