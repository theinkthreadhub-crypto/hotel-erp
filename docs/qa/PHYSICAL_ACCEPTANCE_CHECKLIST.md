# HoReCa One — Physical Hardware Acceptance Checklist (Gates B, C, D)

**Purpose:** Comprehensive field verification runbook for deploying engineers. Required to clear Release Gates B, C, and D prior to commercial General Sale.

---

## 1. Thermal Printer Hardware QA (Gate B)

### 1.1 58mm Thermal Printer (USB)
- [ ] Connect physical 58mm USB ESC/POS thermal printer (e.g. Everycom, POS-58, TVS, Epson).
- [ ] Verify printer driver or Windows Generic / Text Only mapping.
- [ ] Print test receipt: Verify 32-column text alignment.
- [ ] Check line wrap: Long dish names wrap neatly without cutting numbers or prices.
- [ ] Verify auto-cutter: Clean paper cut leaving 1cm feed margin above header.
- [ ] Double-press test: Click "Print Bill" twice within 3 seconds. Verify only 1 physical ticket prints.
- [ ] Paper-out test: Open printer lid mid-print. Verify counter surfaces "Printer Out of Paper" notification. Close lid and click retry; verify receipt finishes without corruption.
- [ ] Unplug test: Pull USB cable mid-billing. Verify billing does not crash; error toast appears; bill remains committed in database.

### 1.2 80mm Thermal Printer (USB & LAN)
- [ ] Connect 80mm USB printer. Verify 48-column text and GST breakdown table columns align.
- [ ] Connect 80mm Ethernet (LAN) printer to counter router. Assign static IP (e.g. `192.168.1.200:9100`).
- [ ] In POS Settings, route "Kitchen" section to LAN printer IP.
- [ ] Punch table order with Kitchen and Bar items.
- [ ] Verify Kitchen KOT prints only kitchen items at the kitchen station; bar items print at the bar printer.

### 1.3 Hindi / Unicode & Rupee Symbol
- [ ] Add Hindi menu items (e.g. "मटर पनीर", "दाल मखनी", "तंदूरी रोटी").
- [ ] Print receipt in Graphic/Raster mode.
- [ ] Verify Rupee symbol (₹) and Devanagari script print crisply without question marks (`???`) or garbled hex codes.

### 1.4 RJ11 Cash Drawer
- [ ] Connect cash drawer cable to thermal printer RJ11 drawer kick port.
- [ ] Settle bill with **Cash**: Verify drawer kicks open immediately.
- [ ] Settle bill with **UPI / Card**: Verify drawer remains firmly closed.

---

## 2. Low-Spec Client PC & Power Loss QA (Gate C)

### 2.1 4GB RAM Target PC Load
- [ ] Install HoReCa One on a physical Windows 10/11 computer with 4GB RAM and Intel Celeron / Core i3 CPU.
- [ ] Monitor memory in Task Manager: Peak RAM of `Aghanya-Devanya-Hotel-ERP.exe` must remain < 250 MB.
- [ ] Run 50 continuous bill operations with KOT. Verify UI does not freeze or stutter.
- [ ] Verify WebView2 runtime boots smoothly without GPU acceleration crashes.

### 2.2 Sudden Power Cut & Reboot
- [ ] Start an order settlement; immediately pull the PC power plug from the wall socket.
- [ ] Power the PC back on.
- [ ] Launch HoReCa One: Verify application starts cleanly without prompt for manual repair.
- [ ] Verify SQLite WAL integrity: `PRAGMA integrity_check` returns `ok`.
- [ ] Verify last confirmed bill is present and complete; partial unfinished transaction is cleanly discarded.

---

## 3. Physical Guest Phone QR Flow (Gate D)

### 3.1 Live Smartphone Table Scan
- [ ] Generate Table QR code tag from POS Masters. Print or display on phone screen.
- [ ] Scan QR tag using Android Chrome camera.
- [ ] Verify menu loads in mobile browser (`cloud/public/qr.html`) with hotel branding and table number pre-selected.
- [ ] Add 2 items and tap "Place Order".
- [ ] Verify sound chime and review badge appear on counter POS within 3 seconds.
- [ ] Counter cashier taps "Accept": Verify items append to table cart and KOT prints.
- [ ] Scan QR tag using iOS Safari camera: Repeat flow; verify cross-platform responsiveness.
