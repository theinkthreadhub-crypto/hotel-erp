# -*- coding: utf-8 -*-
"""
Foodpiolet Enterprise License & WhatsApp Voucher Generator (Desktop GUI)
Powered by Aghanya Devanya Enterprises

Allows generating digitally signed ECDSA P-256 license keys,
Master onboarding keys, and WhatsApp message credit recharge vouchers
from a clean, easy-to-use Windows desktop interface.
"""

import os
import sys
import csv
import datetime
import tkinter as tk
from tkinter import ttk, messagebox

# Ensure current directory is on sys.path
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
if BASE_DIR not in sys.path:
    sys.path.insert(0, BASE_DIR)

import keygen

class KeygenApp(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title("Foodpiolet — Vendor License & Voucher Generator")
        self.geometry("640x720")
        self.minsize(580, 640)
        self.configure(bg="#f8fafc")

        # Initialize keygen private key if needed
        self._ensure_private_key()

        self._apply_styles()
        self._build_ui()

    def _ensure_private_key(self):
        pem_path = os.path.join(BASE_DIR, "setu-license-private.pem")
        if not os.path.exists(pem_path):
            try:
                keygen.cmd_init()
            except Exception as e:
                messagebox.showwarning("Private Key Notice", f"Private key initialized: {e}")

    def _apply_styles(self):
        style = ttk.Style(self)
        try:
            style.theme_use("clam")
        except Exception:
            pass

        style.configure("TNotebook", background="#f8fafc", borderwidth=0)
        style.configure("TNotebook.Tab", padding=[16, 9], font=("Segoe UI", 10, "bold"), background="#e2e8f0", foreground="#475569")
        style.map("TNotebook.Tab",
                  background=[("selected", "#0284c7"), ("active", "#cbd5e1")],
                  foreground=[("selected", "#ffffff"), ("active", "#0f172a")])

        style.configure("TLabel", background="#f8fafc", font=("Segoe UI", 9), foreground="#334155")
        style.configure("Header.TLabel", font=("Segoe UI", 13, "bold"), foreground="#0f172a")
        style.configure("SubHeader.TLabel", font=("Segoe UI", 9), foreground="#64748b")
        style.configure("FieldLabel.TLabel", font=("Segoe UI", 9, "bold"), foreground="#1e293b")

        style.configure("Primary.TButton", font=("Segoe UI", 10, "bold"), background="#0284c7", foreground="#ffffff", padding=[12, 8])
        style.map("Primary.TButton", background=[("active", "#0369a1")])

        style.configure("Success.TButton", font=("Segoe UI", 10, "bold"), background="#16a34a", foreground="#ffffff", padding=[12, 8])
        style.map("Success.TButton", background=[("active", "#15803d")])

        style.configure("Outline.TButton", font=("Segoe UI", 9, "bold"), background="#ffffff", foreground="#475569", padding=[8, 6])

    def _build_ui(self):
        # Top Banner
        header_frame = tk.Frame(self, bg="#0f172a", padx=20, pady=16)
        header_frame.pack(fill="x")

        title_lbl = tk.Label(header_frame, text="FOODPIOLET VENDOR KEYGEN", font=("Segoe UI", 14, "bold"), fg="#ffffff", bg="#0f172a")
        title_lbl.pack(anchor="w")

        sub_lbl = tk.Label(header_frame, text="Enterprise License Keys & WhatsApp Quota Dispatcher • Aghanya Devanya", font=("Segoe UI", 9), fg="#94a3b8", bg="#0f172a")
        sub_lbl.pack(anchor="w", pady=(2, 0))

        # Main Tabs
        notebook = ttk.Notebook(self)
        notebook.pack(fill="both", expand=True, padx=16, pady=12)

        # Tab 1: License Keys
        tab_license = tk.Frame(notebook, bg="#f8fafc", padx=14, pady=14)
        notebook.add(tab_license, text="  🔑 License Key  ")
        self._build_license_tab(tab_license)

        # Tab 2: WhatsApp Vouchers
        tab_wa = tk.Frame(notebook, bg="#f8fafc", padx=14, pady=14)
        notebook.add(tab_wa, text="  💬 WhatsApp Voucher  ")
        self._build_wa_tab(tab_wa)

        # Tab 3: History & Logs
        tab_hist = tk.Frame(notebook, bg="#f8fafc", padx=14, pady=14)
        notebook.add(tab_hist, text="  📋 Issued History  ")
        self._build_history_tab(tab_hist)

        # Status Bar
        self.status_var = tk.StringVar(value="Ready to generate license keys.")
        status_bar = tk.Label(self, textvariable=self.status_var, font=("Segoe UI", 8), bg="#e2e8f0", fg="#475569", anchor="w", padx=12, pady=4)
        status_bar.pack(fill="x", side="bottom")

    def _build_license_tab(self, parent):
        # Target Install ID / Hotel ID
        f1 = tk.Frame(parent, bg="#f8fafc")
        f1.pack(fill="x", pady=(0, 10))

        tk.Label(f1, text="Target Install ID / Hotel ID *", font=("Segoe UI", 9, "bold"), bg="#f8fafc", fg="#1e293b").pack(anchor="w")
        
        id_box = tk.Frame(f1, bg="#f8fafc")
        id_box.pack(fill="x", pady=(4, 0))

        self.lic_id_var = tk.StringVar()
        self.lic_id_entry = tk.Entry(id_box, textvariable=self.lic_id_var, font=("Consolas", 11, "bold"), bg="#ffffff", fg="#0f172a", relief="solid", bd=1)
        self.lic_id_entry.pack(side="left", fill="x", expand=True, ipady=5, padx=(0, 6))

        btn_any_pc = tk.Button(id_box, text="Any PC / Master", font=("Segoe UI", 8, "bold"), bg="#f1f5f9", fg="#0284c7", relief="solid", bd=1, padx=8,
                               command=lambda: self.lic_id_var.set("MASTER-ANY-PC"))
        btn_any_pc.pack(side="right")

        # Hotel Name
        f2 = tk.Frame(parent, bg="#f8fafc")
        f2.pack(fill="x", pady=(0, 10))

        tk.Label(f2, text="Hotel / Restaurant Name (Optional)", font=("Segoe UI", 9, "bold"), bg="#f8fafc", fg="#1e293b").pack(anchor="w")
        self.lic_hotel_var = tk.StringVar()
        tk.Entry(f2, textvariable=self.lic_hotel_var, font=("Segoe UI", 10), bg="#ffffff", relief="solid", bd=1).pack(fill="x", pady=(4, 0), ipady=4)

        # Plan Selection
        f3 = tk.Frame(parent, bg="#f8fafc")
        f3.pack(fill="x", pady=(0, 14))

        tk.Label(f3, text="Select Subscription Plan *", font=("Segoe UI", 9, "bold"), bg="#f8fafc", fg="#1e293b").pack(anchor="w")

        self.plan_map = {
            "1 Month (30 Days)": "1m",
            "2 Months (60 Days)": "2m",
            "3 Months (90 Days)": "3m",
            "6 Months (180 Days)": "6m",
            "1 Year (365 Days)": "1y",
            "Lifetime / Unlimited (10 Years)": "life",
            "Master Key (Any PC / 7 Days Onboarding)": "master",
            "Demo (24 Hours)": "demo24h",
            "Demo (1 Hour)": "demo1h",
            "Owner Password Reset Key": "reset"
        }

        self.plan_var = tk.StringVar(value="1 Month (30 Days)")
        self.plan_combo = ttk.Combobox(f3, textvariable=self.plan_var, values=list(self.plan_map.keys()), state="readonly", font=("Segoe UI", 10))
        self.plan_combo.pack(fill="x", pady=(4, 0), ipady=3)

        # Generate Button
        btn_gen = tk.Button(parent, text="🔑  Generate Activation Key", font=("Segoe UI", 11, "bold"), bg="#0284c7", fg="#ffffff", activebackground="#0369a1", activeforeground="#ffffff", relief="flat", cursor="hand2", pady=8,
                            command=self._generate_license_key)
        btn_gen.pack(fill="x", pady=(0, 14))

        # Output Box
        tk.Label(parent, text="Generated Activation Key:", font=("Segoe UI", 9, "bold"), bg="#f8fafc", fg="#1e293b").pack(anchor="w")
        self.lic_output = tk.Text(parent, height=5, font=("Consolas", 10, "bold"), bg="#ffffff", fg="#0f172a", wrap="char", relief="solid", bd=1, padx=8, pady=8)
        self.lic_output.pack(fill="x", pady=(4, 10))

        # Copy & Share Actions
        btn_box = tk.Frame(parent, bg="#f8fafc")
        btn_box.pack(fill="x")

        tk.Button(btn_box, text="📋 Copy Key", font=("Segoe UI", 9, "bold"), bg="#ffffff", fg="#0284c7", relief="solid", bd=1, padx=12, pady=5, cursor="hand2",
                  command=lambda: self._copy_to_clip(self.lic_output.get("1.0", "end-1c"))).pack(side="left", padx=(0, 8))

        tk.Button(btn_box, text="💬 Copy WhatsApp Format", font=("Segoe UI", 9, "bold"), bg="#ffffff", fg="#16a34a", relief="solid", bd=1, padx=12, pady=5, cursor="hand2",
                  command=self._copy_wa_license_msg).pack(side="left")

        tk.Button(btn_box, text="Clear", font=("Segoe UI", 9), bg="#f1f5f9", fg="#64748b", relief="solid", bd=1, padx=10, pady=5, cursor="hand2",
                  command=lambda: self.lic_output.delete("1.0", "end")).pack(side="right")

    def _build_wa_tab(self, parent):
        tk.Label(parent, text="Recharge client WhatsApp balance by issuing signed voucher codes.", font=("Segoe UI", 9), fg="#64748b", bg="#f8fafc").pack(anchor="w", pady=(0, 12))

        # Client Install ID / Hotel ID
        f1 = tk.Frame(parent, bg="#f8fafc")
        f1.pack(fill="x", pady=(0, 10))

        tk.Label(f1, text="Client Install ID / Hotel ID *", font=("Segoe UI", 9, "bold"), bg="#f8fafc", fg="#1e293b").pack(anchor="w")
        self.wa_id_var = tk.StringVar()
        tk.Entry(f1, textvariable=self.wa_id_var, font=("Consolas", 11, "bold"), bg="#ffffff", relief="solid", bd=1).pack(fill="x", pady=(4, 0), ipady=5)

        # Message Credits Quantity
        f2 = tk.Frame(parent, bg="#f8fafc")
        f2.pack(fill="x", pady=(0, 14))

        tk.Label(f2, text="Select WhatsApp Message Pack *", font=("Segoe UI", 9, "bold"), bg="#f8fafc", fg="#1e293b").pack(anchor="w")
        
        self.wa_credits_var = tk.IntVar(value=500)
        packs_box = tk.Frame(f2, bg="#f8fafc")
        packs_box.pack(fill="x", pady=(4, 0))

        for cr in [50, 100, 500, 1000, 2000, 5000]:
            r = tk.Radiobutton(packs_box, text=f"{cr} Msgs", value=cr, variable=self.wa_credits_var, font=("Segoe UI", 9, "bold"), bg="#f8fafc", fg="#0f172a", activebackground="#f8fafc")
            r.pack(side="left", padx=4)

        # Generate Button
        btn_wa_gen = tk.Button(parent, text="💬  Generate WhatsApp Voucher Code", font=("Segoe UI", 11, "bold"), bg="#16a34a", fg="#ffffff", activebackground="#15803d", activeforeground="#ffffff", relief="flat", cursor="hand2", pady=8,
                               command=self._generate_wa_voucher)
        btn_wa_gen.pack(fill="x", pady=(0, 14))

        # Output Box
        tk.Label(parent, text="Voucher Code:", font=("Segoe UI", 9, "bold"), bg="#f8fafc", fg="#1e293b").pack(anchor="w")
        self.wa_output = tk.Entry(parent, font=("Consolas", 13, "bold"), bg="#ffffff", fg="#166534", relief="solid", bd=1, justify="center")
        self.wa_output.pack(fill="x", pady=(4, 10), ipady=8)

        # Copy & Share Actions
        btn_box = tk.Frame(parent, bg="#f8fafc")
        btn_box.pack(fill="x")

        tk.Button(btn_box, text="📋 Copy Voucher", font=("Segoe UI", 9, "bold"), bg="#ffffff", fg="#16a34a", relief="solid", bd=1, padx=12, pady=5, cursor="hand2",
                  command=lambda: self._copy_to_clip(self.wa_output.get())).pack(side="left", padx=(0, 8))

        tk.Button(btn_box, text="💬 Copy Client Message", font=("Segoe UI", 9, "bold"), bg="#ffffff", fg="#0284c7", relief="solid", bd=1, padx=12, pady=5, cursor="hand2",
                  command=self._copy_wa_voucher_msg).pack(side="left")

    def _build_history_tab(self, parent):
        tk.Label(parent, text="Recently Issued Keys (from issued-licenses.csv):", font=("Segoe UI", 9, "bold"), bg="#f8fafc", fg="#1e293b").pack(anchor="w", pady=(0, 8))

        columns = ("date", "hotel", "plan", "install_id", "key")
        self.tree = ttk.Treeview(parent, columns=columns, show="headings", height=14)
        self.tree.heading("date", text="Date")
        self.tree.heading("hotel", text="Hotel Name")
        self.tree.heading("plan", text="Plan")
        self.tree.heading("install_id", text="Install / Hotel ID")
        self.tree.heading("key", text="License Key Preview")

        self.tree.column("date", width=80, anchor="center")
        self.tree.column("hotel", width=120)
        self.tree.column("plan", width=80, anchor="center")
        self.tree.column("install_id", width=110, anchor="center")
        self.tree.column("key", width=180)

        scrollbar = ttk.Scrollbar(parent, orient="vertical", command=self.tree.yview)
        self.tree.configure(yscrollcommand=scrollbar.set)

        self.tree.pack(side="left", fill="both", expand=True)
        scrollbar.pack(side="right", fill="y")

        # Refresh button at top
        btn_box = tk.Frame(parent, bg="#f8fafc")
        btn_box.pack(fill="x", pady=8)
        tk.Button(btn_box, text="🔄 Refresh History", font=("Segoe UI", 9, "bold"), bg="#ffffff", relief="solid", bd=1, padx=10, pady=4, cursor="hand2",
                  command=self._load_history).pack(side="left")
        
        self._load_history()

    def _load_history(self):
        for item in self.tree.get_children():
            self.tree.delete(item)

        csv_path = os.path.join(BASE_DIR, "issued-licenses.csv")
        if not os.path.exists(csv_path):
            return

        try:
            with open(csv_path, "r", encoding="utf-8-sig") as f:
                reader = csv.reader(f)
                rows = list(reader)
                # Reverse to show newest on top (skip header if present)
                start = 1 if rows and rows[0] and "date" in rows[0][0].lower() else 0
                for r in reversed(rows[start:]):
                    if len(r) >= 5:
                        key_preview = r[4][:20] + "..." if len(r[4]) > 20 else r[4]
                        self.tree.insert("", "end", values=(r[0], r[2], r[1], r[3], key_preview))
        except Exception:
            pass

    def _generate_license_key(self):
        target_id = self.lic_id_var.get().strip().upper()
        hotel_name = self.lic_hotel_var.get().strip()
        plan_label = self.plan_var.get()
        plan_code = self.plan_map.get(plan_label, "1m")

        if plan_code == "master":
            target_id = "MASTER-ANY-PC"
            self.lic_id_var.set(target_id)

        if not target_id:
            messagebox.showwarning("Missing ID", "Please enter Client Install ID or Hotel ID (e.g. HOTEL4820 or SETU-7F3K-92QD).")
            self.lic_id_entry.focus_set()
            return

        try:
            key = keygen.make_key(target_id, plan_code)
            keygen.log_key(target_id, plan_code, hotel_name or "Vendor Issue", key)

            self.lic_output.delete("1.0", "end")
            self.lic_output.insert("1.0", key)

            self.status_var.set(f"Generated {plan_label} for {target_id} successfully!")
            self._copy_to_clip(key, show_toast=False)
            messagebox.showinfo("Key Generated", f"Key generated and copied to clipboard!\n\nPlan: {plan_label}\nTarget: {target_id}")
            self._load_history()
        except Exception as e:
            messagebox.showerror("Error", f"Failed to generate license key: {e}")

    def _generate_wa_voucher(self):
        target_id = self.wa_id_var.get().strip().upper()
        credits = self.wa_credits_var.get()

        if not target_id:
            messagebox.showwarning("Missing ID", "Please enter Client Install ID or Hotel ID.")
            return

        try:
            voucher = keygen.make_compact_voucher(target_id, credits)
            self.wa_output.delete(0, "end")
            self.wa_output.insert(0, voucher)

            self.status_var.set(f"Generated {credits} WA credits voucher for {target_id}!")
            self._copy_to_clip(voucher, show_toast=False)
            messagebox.showinfo("Voucher Created", f"WhatsApp voucher generated and copied to clipboard!\n\nCode: {voucher}\nCredits: {credits} Messages")
        except Exception as e:
            messagebox.showerror("Error", f"Failed to generate voucher: {e}")

    def _copy_to_clip(self, text, show_toast=True):
        text = str(text or "").strip()
        if not text:
            return
        self.clipboard_clear()
        self.clipboard_append(text)
        self.status_var.set(f"Copied to clipboard: {text[:24]}...")
        if show_toast:
            messagebox.showinfo("Copied", "Copied to clipboard!")

    def _copy_wa_license_msg(self):
        key = self.lic_output.get("1.0", "end-1c").strip()
        if not key:
            messagebox.showwarning("No Key", "Please generate a key first.")
            return
        hotel = self.lic_hotel_var.get().strip() or "Client"
        plan = self.plan_var.get()
        target = self.lic_id_var.get().strip()

        msg = (
            f"Namaste {hotel},\n\n"
            f"Here is your official Foodpiolet ERP License Activation Key:\n\n"
            f"🔑 Activation Key:\n{key}\n\n"
            f"📅 Plan: {plan}\n"
            f"🏨 Hotel / Device ID: {target}\n\n"
            f"Steps to Activate:\n"
            f"1. Open Foodpiolet software\n"
            f"2. Paste this Activation Key in the activation box\n"
            f"3. Click 'Activate Hotel & Open Dashboard'\n\n"
            f"Thank you for choosing Foodpiolet!\n"
            f"— Aghanya Devanya Enterprises"
        )
        self._copy_to_clip(msg)

    def _copy_wa_voucher_msg(self):
        voucher = self.wa_output.get().strip()
        if not voucher:
            messagebox.showwarning("No Voucher", "Please generate a voucher first.")
            return
        target = self.wa_id_var.get().strip()
        credits = self.wa_credits_var.get()

        msg = (
            f"Namaste,\n\n"
            f"Here is your WhatsApp Message Balance Recharge Code for Foodpiolet ERP:\n\n"
            f"💬 Recharge Code: {voucher}\n"
            f"⚡ Credits Added: {credits} Messages\n"
            f"🏨 Device ID: {target}\n\n"
            f"Steps to Recharge:\n"
            f"Go to Settings → WhatsApp Billing → Enter Voucher Code → Click Redeem.\n\n"
            f"— Aghanya Devanya Enterprises"
        )
        self._copy_to_clip(msg)

if __name__ == "__main__":
    app = KeygenApp()
    app.mainloop()
