from pathlib import Path
import re

html_path = Path("hotel-erp/hotel_erp.html")
c = html_path.read_text(encoding="utf-8")
print(f"Initial length: {len(c)}")

# =========================================================================
# 1. TOP BAR CLEANUP & HOTEL BRANDING
# =========================================================================
# User requests:
# - Remove Help button
# - Remove Zomato & Swiggy pills
# - Remove Search from top bar (moved to sidebar above Gateway Dashboard)
# - In Top Bar: Show Hotel Logo & Hotel Name prominently (HoReCa One ERP badge)

# Locate <header id="top"> ... </header>
topbar_pattern = re.compile(r'<header id="top">.*?</header>', re.DOTALL)
topbar_match = topbar_pattern.search(c)
if not topbar_match:
    print("ERROR: could not find <header id=\"top\">")
else:
    print("Found <header id=\"top\">")

new_topbar = '''<header id="top">
  <button id="sidebtn" onclick="toggleHoReCaSidebar()" title="Toggle Sidebar (Expanded / Compact / Full Screen)">☰</button>
  <div class="brand-wrap" onclick="go('gateway')" title="Open Hotel Dashboard" style="max-width:none!important;cursor:pointer">
    <img id="top-hotel-logo" src="horeca-icon-dark.png" alt="Hotel Logo" style="width:38px;height:38px;border-radius:10px;box-shadow:0 3px 10px rgba(255,151,7,0.25);flex-shrink:0;border:1px solid rgba(255,151,7,0.3);object-fit:cover">
    <div style="display:flex;flex-direction:column;line-height:1.2">
      <div style="display:flex;align-items:center;gap:6px">
        <b id="hname" style="font-size:16px;font-weight:900;letter-spacing:-0.3px;color:var(--text)!important;max-width:320px;overflow:hidden;text-overflow:ellipsis;white-space:nowrap">Hotel ERP</b>
        <span class="horeca-sub-badge" style="font-size:9px;font-weight:800;background:rgba(255,151,7,0.18);color:#ea7e00;border:1px solid rgba(255,151,7,0.4);padding:1px 5px;border-radius:4px;text-transform:uppercase;letter-spacing:0.5px">ERP</span>
      </div>
      <div style="display:flex;align-items:center;gap:6px;font-size:10px;font-weight:700;color:var(--text-muted)">
        <span id="hsub">Hotel • Restaurant • Café</span>
      </div>
    </div>
  </div>

  <span class="scr" id="scrname"><span class="dot"></span>Gateway</span>

  <div style="flex:1"></div>

  <!-- RIGHT ALIGNED AREA -->
  <!-- WhatsApp Status (Icon Only) & Message Balance Chip -->
  <div class="top-wa-container" id="top-wa-container" style="display:inline-flex;align-items:center">
    <button class="top-wa-btn disconnected" id="top-wa-btn" onclick="openWaModal()" title="WhatsApp Disconnected — Click to scan QR & connect">
      <span class="top-wa-icon-slot" id="top-wa-icon-slot" style="display:inline-flex;align-items:center;justify-content:center;width:24px;height:24px">
        <svg viewBox="0 0 24 24" width="22" height="22" style="display:block">
          <path fill="#ef4444" d="M12.04 2c-5.46 0-9.91 4.45-9.91 9.91 0 1.75.46 3.45 1.32 4.95L2.05 22l5.25-1.38c1.45.79 3.08 1.21 4.74 1.21 5.46 0 9.91-4.45 9.91-9.91 0-2.65-1.03-5.14-2.9-7.01A9.816 9.816 0 0012.04 2z"/>
          <path fill="#fff" d="M17.47 14.38c-.3-.15-1.77-.87-2.04-.97-.27-.1-.47-.15-.67.15-.2.3-.77.97-.94 1.17-.17.2-.35.22-.65.07-.3-.15-1.27-.47-2.42-1.49-.89-.8-1.5-1.78-1.67-2.08-.17-.3-.02-.46.13-.61.13-.13.3-.35.45-.52.15-.17.2-.3.3-.5.1-.2.05-.37-.02-.52-.08-.15-.67-1.62-.92-2.22-.24-.58-.49-.5-.67-.51-.17-.01-.37-.01-.57-.01-.2 0-.52.07-.79.37-.27.3-1.04 1.02-1.04 2.48s1.07 2.87 1.22 3.07c.15.2 2.1 3.2 5.08 4.49.71.31 1.26.49 1.69.63.71.23 1.36.2 1.87.12.57-.09 1.77-.72 2.02-1.42.25-.7.25-1.3.17-1.42-.07-.13-.27-.2-.57-.35z"/>
        </svg>
      </span>
    </button>
  </div>

  <span id="licbadge" class="lic-chip-wrap" onclick="openSubscriptionModal()" title="License Details">
    <span class="lic-chip ok" id="lictext">License: Active</span>
  </span>

  <span class="cloud-pill" id="cloud-pill" onclick="srvShowSyncDetails()" title="Cloud Live Sync Active">
    <span class="cloud-dot"></span>
    <span class="cloud-t" id="cloud-pill-text">All saved</span>
  </span>

  <button class="ho-guide-header" onclick="triggerPWAInstall()" title="Install Native PC/Desktop App" aria-label="Install PC App" style="margin-left:4px;background:var(--surface);border:1px solid var(--border);color:var(--text);font-weight:700">Install PC App</button>

  <span id="clock" style="font-size:11.5px;font-weight:600;color:var(--text-muted);white-space:nowrap;padding:0 6px"></span>

  <div class="user-chip" id="uchip">
    <span id="uname" style="font-weight:800;color:var(--text)">Owner</span>
    <span id="urole" class="role-badge">ADMIN</span>
  </div>

  <button class="ho-guide-header" onclick="logout()" title="Logout of current staff shift" style="font-size:11px;padding:3px 8px;margin-left:4px">Staff Logout</button>
</header>'''

c = topbar_pattern.sub(new_topbar, c, count=1)
print("Updated top bar HTML (removed Help, Zomato, Swiggy, moved search)")

# =========================================================================
# 2. SIDEBAR BRANDING & SEARCH BOX ABOVE GATEWAY DASHBOARD
# =========================================================================
# In drawSide():
# Add Search box right above Gateway Dashboard
# Single HoReCa One brand header in sidebar
old_drawside_start = '''  let html = `
    <div class="horeca-side-brand" aria-label="HoReCa One — Hotel Restaurant Café">
      <img src="horeca-icon-dark.png" alt="HoReCa One" style="width:38px;height:38px;border-radius:10px;box-shadow:0 3px 10px rgba(255,151,7,0.3);flex:0 0 38px;border:1px solid rgba(255,151,7,0.3)">
      <div><b>HoReCa <span style="color:#FF9707">One</span></b><small style="color:#94a3b8">HOTEL • RESTAURANT • CAFE</small></div>
    </div>
    <button class="nav-item ${cur==='gateway'?'active':''}" onclick="go('gateway')" title="Gateway Command Center (Esc)">'''

new_drawside_start = '''  let html = `
    <div class="horeca-side-brand" aria-label="HoReCa One — Hotel Restaurant Café">
      <img src="horeca-icon-dark.png" alt="HoReCa One" style="width:38px;height:38px;border-radius:10px;box-shadow:0 3px 10px rgba(255,151,7,0.3);flex:0 0 38px;border:1px solid rgba(255,151,7,0.3)">
      <div><b>HoReCa <span style="color:#FF9707">One</span></b><small style="color:#94a3b8">HOTEL • RESTAURANT • CAFE</small></div>
    </div>
    <!-- Search Box above Gateway Dashboard -->
    <div class="side-search-box" onclick="ckOpen()" title="Search modules, settings, bills, dishes… (Ctrl+K)">
      <span class="nav-icon"><svg viewBox="0 0 24 24" width="16" height="16" fill="none" stroke="currentColor" stroke-width="2"><circle cx="11" cy="11" r="7"/><path d="m20 20-4-4"/></svg></span>
      <span class="nav-label side-search-label">Search anything…</span>
      <kbd class="nav-kbd">Ctrl K</kbd>
    </div>
    <button class="nav-item ${cur==='gateway'?'active':''}" onclick="go('gateway')" title="Gateway Command Center (Esc)">'''

if old_drawside_start in c:
    c = c.replace(old_drawside_start, new_drawside_start, 1)
    print("Patched drawSide with search box (exact)")
else:
    old_crlf = old_drawside_start.replace("\n", "\r\n")
    if old_crlf in c:
        c = c.replace(old_crlf, new_drawside_start, 1)
        print("Patched drawSide with search box (CRLF)")
    else:
        print("Warning: old_drawside_start not matched directly, using regex...")
        c = re.sub(
            r'let html = `\s*<div class="horeca-side-brand".*?</div>\s*<button class="nav-item \$\{cur===\'gateway\'\?\'active\':\'\'\}"',
            new_drawside_start,
            c,
            flags=re.DOTALL
        )

# =========================================================================
# 3. COMPACT SIDEBAR STYLING (MATCHING IMAGE 3)
# =========================================================================
# Compact mode (side-compact):
# Vertically stack icon and label centered underneath!
compact_css = '''
/* Compact Sidebar Mode (Matching Vertical Stack Icon + Centered Label) */
body.side-compact #side {
  width: 76px !important;
  min-width: 76px !important;
  padding: 8px 4px !important;
  align-items: center !important;
}
body.side-compact #side .horeca-side-brand {
  flex-direction: column !important;
  justify-content: center !important;
  align-items: center !important;
  padding: 6px 0 10px !important;
  gap: 4px !important;
}
body.side-compact #side .horeca-side-brand > div:last-child {
  display: none !important;
}
body.side-compact #side .side-search-box {
  width: 60px !important;
  min-height: 48px !important;
  flex-direction: column !important;
  justify-content: center !important;
  align-items: center !important;
  padding: 6px 2px !important;
  margin: 4px auto 8px !important;
  text-align: center !important;
  border-radius: 8px !important;
  background: rgba(255,255,255,0.06) !important;
  border: 1px solid rgba(255,255,255,0.15) !important;
  cursor: pointer !important;
}
body.side-compact #side .side-search-box .nav-kbd {
  display: none !important;
}
body.side-compact #side .side-search-label {
  display: block !important;
  font-size: 9.5px !important;
  font-weight: 700 !important;
  color: #cbd5e1 !important;
  margin-top: 3px !important;
  text-align: center !important;
}
body.side-compact #side .nav-item {
  width: 64px !important;
  min-height: 52px !important;
  flex-direction: column !important;
  justify-content: center !important;
  align-items: center !important;
  padding: 6px 2px !important;
  margin: 3px auto !important;
  text-align: center !important;
  gap: 3px !important;
  border-radius: 9px !important;
}
body.side-compact #side .nav-icon {
  width: 22px !important;
  height: 22px !important;
  margin: 0 auto !important;
  display: flex !important;
  align-items: center !important;
  justify-content: center !important;
}
body.side-compact #side .nav-label {
  display: block !important;
  font-size: 9.5px !important;
  font-weight: 700 !important;
  line-height: 1.15 !important;
  text-align: center !important;
  white-space: normal !important;
  max-width: 60px !important;
  word-break: break-word !important;
}
body.side-compact #side .nav-right,
body.side-compact #side .nav-kbd {
  display: none !important;
}
body.side-compact #side .side-section-header {
  padding: 4px 0 !important;
  margin: 8px auto 4px !important;
  text-align: center !important;
  font-size: 8.5px !important;
  border-top: 1px solid rgba(255,255,255,0.1) !important;
  width: 50px !important;
}
body.side-compact #side .side-section-header span:last-child {
  display: none !important;
}
body.side-compact #side .side-footer-toggle {
  width: 60px !important;
  min-height: 44px !important;
  flex-direction: column !important;
  justify-content: center !important;
  align-items: center !important;
  margin: 10px auto 4px !important;
  padding: 6px 2px !important;
  text-align: center !important;
}
body.side-compact #side .side-footer-toggle .toggle-label {
  display: block !important;
  font-size: 9px !important;
  margin-top: 2px !important;
}

/* Sidebar Search Box in Expanded Mode */
.side-search-box {
  display: flex;
  align-items: center;
  gap: 8px;
  background: rgba(255,255,255,0.06);
  border: 1px solid rgba(255,255,255,0.16);
  color: #cbd5e1;
  padding: 8px 10px;
  border-radius: 9px;
  margin: 4px 0 8px;
  cursor: pointer;
  transition: all 0.15s ease;
}
.side-search-box:hover {
  background: rgba(255,255,255,0.12);
  border-color: rgba(255,151,7,0.4);
  color: #fff;
}
.side-search-box .nav-icon {
  color: #FF9707;
  display: flex;
  align-items: center;
}
.side-search-box .side-search-label {
  font-size: 12px;
  font-weight: 600;
  color: #cbd5e1;
  flex: 1;
}
.side-search-box .nav-kbd {
  font-size: 10px;
  padding: 2px 5px;
  border-radius: 4px;
  background: rgba(255,255,255,0.08);
  border: 1px solid rgba(255,255,255,0.18);
  color: #94a3b8;
}
'''

# Append compact CSS before </style>
if '</style>' in c:
    c = c.replace('</style>', compact_css + '\n</style>', 1)
    print("Added compact sidebar styles matching Image 3")

# =========================================================================
# 4. ENHANCED DAY BOOK & CANCELLED BILLS REPORT (MATCHING IMAGE 1 & 2)
# =========================================================================
# Rewrite scrDaybook to:
# - Support filter view mode (Image 2):
#   * Start Date
#   * End Date
#   * School / Hotel / Outlet dropdown
#   * User dropdown
#   * Type dropdown (All, Active Bills, Cancelled Bills, All Bills, Expenses, Sales & Expenses, Purchases, Cash, Bank, Credit)
#   * Order (Date Ascending, Date Descending, Voucher No)
#   * Submit button
# - Support report view mode (Image 1):
#   * Print, PDF, Excel buttons
#   * Date, Time, Voucher Type, Particulars, Mode, Inward (₹), Outward (₹)
#   * Cancelled bills marked clearly in red (CANCELLED), inward as — (or strikethrough), 
#   * Change Filter button to go back to filter anytime

daybook_js = '''
let dbFilterType = 'all';
let dbUser = 'all';
let dbOrder = 'date_asc';
let dbSubmitted = false;

function scrDaybook(){
  if(dbTo < dbFrom) dbTo = dbFrom;
  
  // If not yet submitted and user just opened Day Book, show the Filter Screen (Image 2)
  if(!dbSubmitted){
    renderDaybookFilterScreen();
    return;
  }
  
  renderDaybookReportScreen();
}

function renderDaybookFilterScreen(){
  const st = D.settings || {};
  const hotelName = st.name || 'Main Outlet';
  const users = (D.auth && D.auth.users) ? D.auth.users : [];
  const userOptions = [['all', 'All Users / Cashiers']].concat(users.map(u => [u.username || u.name, u.name || u.username]));

  main.innerHTML = `
  <div style="max-width:680px;margin:24px auto;padding:0 16px">
    <div class="card" style="padding:28px 32px;border-radius:14px;box-shadow:0 8px 30px rgba(0,0,0,0.07);border:1px solid var(--border)">
      <div style="border-bottom:1px solid var(--border);padding-bottom:16px;margin-bottom:24px;display:flex;align-items:center;justify-content:space-between">
        <div>
          <h2 style="margin:0 0 4px;font-size:20px;font-weight:800;color:var(--text)">Day Book & Ledger Filter</h2>
          <p style="margin:0;font-size:12px;color:var(--text-muted)">Select dates, voucher type and parameters to generate the day book ledger</p>
        </div>
        <button class="btn sm" onclick="dbSubmitted=true;scrDaybook()" style="font-weight:700">Quick View Today &rarr;</button>
      </div>

      <form onsubmit="event.preventDefault();submitDaybookFilter();" style="display:flex;flex-direction:column;gap:18px">
        <div style="display:grid;grid-template-columns:140px 1fr;align-items:center;gap:16px">
          <label style="font-size:13px;font-weight:700;color:var(--text)">Start Date</label>
          <input type="date" id="db_form_start" value="${dbFrom}" style="padding:9px 12px;border-radius:8px;border:1px solid var(--border);background:var(--surface);color:var(--text);font-weight:600;font-size:13px" required>
        </div>

        <div style="display:grid;grid-template-columns:140px 1fr;align-items:center;gap:16px">
          <label style="font-size:13px;font-weight:700;color:var(--text)">End Date</label>
          <input type="date" id="db_form_end" value="${dbTo}" style="padding:9px 12px;border-radius:8px;border:1px solid var(--border);background:var(--surface);color:var(--text);font-weight:600;font-size:13px" required>
        </div>

        <div style="display:grid;grid-template-columns:140px 1fr;align-items:center;gap:16px">
          <label style="font-size:13px;font-weight:700;color:var(--text)">Outlet / Hotel</label>
          <select id="db_form_outlet" style="padding:9px 12px;border-radius:8px;border:1px solid var(--border);background:var(--surface);color:var(--text);font-weight:600;font-size:13px">
            <option value="main">${esc(hotelName)}</option>
          </select>
        </div>

        <div style="display:grid;grid-template-columns:140px 1fr;align-items:center;gap:16px">
          <label style="font-size:13px;font-weight:700;color:var(--text)">User / Cashier</label>
          <select id="db_form_user" style="padding:9px 12px;border-radius:8px;border:1px solid var(--border);background:var(--surface);color:var(--text);font-weight:600;font-size:13px">
            ${userOptions.map(([val, lbl]) => `<option value="${esc(val)}" ${dbUser===val?'selected':''}>${esc(lbl)}</option>`).join('')}
          </select>
        </div>

        <div style="display:grid;grid-template-columns:140px 1fr;align-items:center;gap:16px">
          <label style="font-size:13px;font-weight:700;color:var(--text)">Type</label>
          <select id="db_form_type" style="padding:9px 12px;border-radius:8px;border:1px solid var(--border);background:var(--surface);color:var(--text);font-weight:600;font-size:13px">
            <option value="all" ${dbFilterType==='all'?'selected':''}>All Transactions (Day Book)</option>
            <option value="active_sales" ${dbFilterType==='active_sales'?'selected':''}>Sales Bills (Active Only)</option>
            <option value="cancelled_sales" ${dbFilterType==='cancelled_sales'?'selected':''}>Cancelled Bills Only (रद्द किए गए बिल)</option>
            <option value="all_sales" ${dbFilterType==='all_sales'?'selected':''}>All Bills (Active + Cancelled Bills)</option>
            <option value="expense" ${dbFilterType==='expense'?'selected':''}>Expenses Only (खर्च)</option>
            <option value="sales_expense" ${dbFilterType==='sales_expense'?'selected':''}>Sales & Expenses (बिक्री और खर्च)</option>
            <option value="purchase" ${dbFilterType==='purchase'?'selected':''}>Stock Purchases Only (खरीद)</option>
            <option value="cash" ${dbFilterType==='cash'?'selected':''}>Cash Drawer Movements Only (रोकड़ बही)</option>
            <option value="bank" ${dbFilterType==='bank'?'selected':''}>Bank / UPI / Online Collections</option>
            <option value="credit" ${dbFilterType==='credit'?'selected':''}>Credit / Customer Outstandings</option>
          </select>
        </div>

        <div style="display:grid;grid-template-columns:140px 1fr;align-items:center;gap:16px">
          <label style="font-size:13px;font-weight:700;color:var(--text)">Order</label>
          <select id="db_form_order" style="padding:9px 12px;border-radius:8px;border:1px solid var(--border);background:var(--surface);color:var(--text);font-weight:600;font-size:13px">
            <option value="date_asc" ${dbOrder==='date_asc'?'selected':''}>Date & Time (Oldest First)</option>
            <option value="date_desc" ${dbOrder==='date_desc'?'selected':''}>Date & Time (Newest First)</option>
            <option value="voucher" ${dbOrder==='voucher'?'selected':''}>Voucher Type</option>
          </select>
        </div>

        <div style="display:grid;grid-template-columns:140px 1fr;gap:16px;margin-top:10px">
          <div></div>
          <div style="display:flex;gap:10px">
            <button type="submit" class="btn ok" style="padding:10px 28px;font-size:14px;font-weight:800;border-radius:8px;background:#1e293b;color:#fff">Submit</button>
            <button type="button" class="btn" onclick="dbFrom=dbTo=today();dbFilterType='all';dbSubmitted=true;scrDaybook()" style="padding:10px 18px;font-size:13px;font-weight:700">Today's Quick Book</button>
          </div>
        </div>
      </form>
    </div>
  </div>
  `;
}

function submitDaybookFilter(){
  dbFrom = $('#db_form_start').value || today();
  dbTo = $('#db_form_end').value || dbFrom;
  dbFilterType = $('#db_form_type').value || 'all';
  dbUser = $('#db_form_user').value || 'all';
  dbOrder = $('#db_form_order').value || 'date_asc';
  dbSubmitted = true;
  scrDaybook();
}

function renderDaybookReportScreen(){
  const {allEntries, t, days} = daybookData(dbFrom, dbTo, 'all');
  const many = dbFrom !== dbTo;
  
  // Filter entries based on dbFilterType
  let filtered = allEntries.slice();

  // User filter
  if(dbUser !== 'all'){
    filtered = filtered.filter(x => (x.user && (x.user === dbUser || x.by === dbUser)));
  }

  // Type filter
  if(dbFilterType === 'active_sales'){
    filtered = filtered.filter(x => x.vtype === 'Sales' && !x.x);
  } else if(dbFilterType === 'cancelled_sales'){
    filtered = filtered.filter(x => x.vtype === 'Sales' && x.x);
  } else if(dbFilterType === 'all_sales'){
    filtered = filtered.filter(x => x.vtype === 'Sales');
  } else if(dbFilterType === 'expense'){
    filtered = filtered.filter(x => x.vtype === 'Expense');
  } else if(dbFilterType === 'sales_expense'){
    filtered = filtered.filter(x => x.vtype === 'Sales' || x.vtype === 'Expense');
  } else if(dbFilterType === 'purchase'){
    filtered = filtered.filter(x => x.vtype === 'Purchase');
  } else if(dbFilterType === 'cash'){
    filtered = filtered.filter(x => x.cashIn > 0 || x.cashOut > 0);
  } else if(dbFilterType === 'bank'){
    filtered = filtered.filter(x => x.bankIn > 0 || x.bankOut > 0);
  } else if(dbFilterType === 'credit'){
    filtered = filtered.filter(x => x.creditIn > 0 || x.creditOut > 0 || x.isCredit);
  }

  // Sorting
  if(dbOrder === 'date_desc'){
    filtered.sort((a, b) => ((b.date + ' ' + (b.time||'')) > (a.date + ' ' + (a.time||'')) ? 1 : -1));
  } else if(dbOrder === 'voucher'){
    filtered.sort((a, b) => ((a.type || '').localeCompare(b.type || '')));
  } else {
    // date_asc (default)
    filtered.sort((a, b) => ((a.date + ' ' + (a.time||'')) > (b.date + ' ' + (b.time||'')) ? 1 : -1));
  }

  const cancelledCount = filtered.filter(x => x.x).length;
  const activeCount = filtered.filter(x => !x.x && x.vtype === 'Sales').length;
  const totalInward = sum(filtered, 'in');
  const totalOutward = sum(filtered, 'out');

  const filterNames = {
    all: 'General Day Book (All Entries)',
    active_sales: 'Sales Bills (Active Only)',
    cancelled_sales: 'Cancelled Bills Only',
    all_sales: 'All Bills (Active + Cancelled)',
    expense: 'Expenses Only',
    sales_expense: 'Sales & Expenses',
    purchase: 'Stock Purchases Only',
    cash: 'Cash Drawer Movements',
    bank: 'Bank / Digital Inflows',
    credit: 'Credit Outstandings'
  };

  main.innerHTML = `
  <div style="margin-bottom:14px;display:flex;align-items:center;justify-content:space-between;flex-wrap:wrap;gap:10px">
    <div style="display:flex;align-items:center;gap:8px">
      <button class="btn sm" onclick="printDaybook()" style="padding:6px 16px;font-weight:700">Print</button>
      <button class="btn ok sm" onclick="daybookPDF()" style="padding:6px 16px;font-weight:700;background:#2563eb;color:#fff">PDF</button>
      <button class="btn g sm" onclick="daybookCSV()" style="padding:6px 16px;font-weight:700">Excel</button>
      <button class="btn sm" onclick="dbSubmitted=false;scrDaybook()" style="padding:6px 14px;font-weight:700;border:1px solid var(--border);margin-left:8px">
        🔍 Change Filter / New Search
      </button>
    </div>
    <div style="font-size:12.5px;font-weight:700;color:var(--text-muted)">
      <span>Period: <b style="color:var(--text)">${dmy(dbFrom)}</b> to <b style="color:var(--text)">${dmy(dbTo)}</b></span>
      <span style="margin:0 6px">•</span>
      <span style="color:#FF9707">${filterNames[dbFilterType] || 'Filtered'}</span>
    </div>
  </div>

  <!-- Quick Category Tabs -->
  <div style="display:flex;gap:6px;margin-bottom:12px;flex-wrap:wrap">
    <button class="cat ${dbFilterType==='all'?'active':''}" onclick="dbFilterType='all';renderDaybookReportScreen()" style="${dbFilterType==='all'?'background:var(--primary);color:#fff;font-weight:700':''}">📑 General Day Book</button>
    <button class="cat ${dbFilterType==='cancelled_sales'?'active':''}" onclick="dbFilterType='cancelled_sales';renderDaybookReportScreen()" style="${dbFilterType==='cancelled_sales'?'background:#ef4444;color:#fff;font-weight:700':''}">🚫 Cancelled Bills (${cancelledCount})</button>
    <button class="cat ${dbFilterType==='all_sales'?'active':''}" onclick="dbFilterType='all_sales';renderDaybookReportScreen()" style="${dbFilterType==='all_sales'?'background:var(--primary);color:#fff;font-weight:700':''}">🧾 All Bills (Active + Cancelled)</button>
    <button class="cat ${dbFilterType==='sales_expense'?'active':''}" onclick="dbFilterType='sales_expense';renderDaybookReportScreen()" style="${dbFilterType==='sales_expense'?'background:var(--primary);color:#fff;font-weight:700':''}">⚖️ Sales & Expenses</button>
    <button class="cat ${dbFilterType==='expense'?'active':''}" onclick="dbFilterType='expense';renderDaybookReportScreen()" style="${dbFilterType==='expense'?'background:#dc2626;color:#fff;font-weight:700':''}">💸 Expenses</button>
    <button class="cat ${dbFilterType==='cash'?'active':''}" onclick="dbFilterType='cash';renderDaybookReportScreen()" style="${dbFilterType==='cash'?'background:var(--primary);color:#fff;font-weight:700':''}">💵 Cash Drawer</button>
  </div>

  <div class="card" style="padding:0;overflow:auto;border-radius:10px;border:1px solid var(--border);box-shadow:0 4px 16px rgba(0,0,0,0.03)">
    <table style="width:100%;border-collapse:collapse;font-size:12.5px">
      <thead>
        <tr style="background:var(--surface);border-bottom:1px solid var(--border)">
          <th style="padding:10px 14px;text-align:left;font-size:11px;font-weight:800;color:var(--text-muted);letter-spacing:0.05em">DATE</th>
          <th style="padding:10px 12px;text-align:left;font-size:11px;font-weight:800;color:var(--text-muted);letter-spacing:0.05em">TIME</th>
          <th style="padding:10px 14px;text-align:left;font-size:11px;font-weight:800;color:var(--text-muted);letter-spacing:0.05em">VOUCHER TYPE</th>
          <th style="padding:10px 14px;text-align:left;font-size:11px;font-weight:800;color:var(--text-muted);letter-spacing:0.05em">PARTICULARS</th>
          <th style="padding:10px 12px;text-align:left;font-size:11px;font-weight:800;color:var(--text-muted);letter-spacing:0.05em">MODE</th>
          <th style="padding:10px 14px;text-align:right;font-size:11px;font-weight:800;color:var(--text-muted);letter-spacing:0.05em">INWARD (₹)</th>
          <th style="padding:10px 14px;text-align:right;font-size:11px;font-weight:800;color:var(--text-muted);letter-spacing:0.05em">OUTWARD (₹)</th>
        </tr>
      </thead>
      <tbody>
        ${filtered.length ? filtered.map(r => `
          <tr style="border-bottom:1px solid var(--border);${r.x ? 'background:rgba(239,68,68,0.03);opacity:0.85' : ''}">
            <td style="padding:10px 14px;white-space:nowrap;font-weight:600">${dmy(r.date)}</td>
            <td style="padding:10px 12px;white-space:nowrap;color:var(--text-muted)">${esc(r.time || '—')}</td>
            <td style="padding:10px 14px;white-space:nowrap">
              <span class="badge" style="font-size:11px;font-weight:700;${r.x ? 'background:#fee2e2;color:#dc2626;border:1px solid #fca5a5' : ''}">${esc(r.type)}</span>
            </td>
            <td style="padding:10px 14px;color:var(--text)">
              ${r.x ? `<span style="color:#dc2626;font-weight:700">${esc(r.part)}</span>` : esc(r.part)}
            </td>
            <td style="padding:10px 12px;white-space:nowrap;color:var(--text-muted);font-weight:600">${esc(r.mode || '—')}</td>
            <td style="padding:10px 14px;text-align:right;font-weight:700;${r.in > 0 ? 'color:#16a34a' : 'color:var(--text-muted)'}">
              ${r.in > 0 ? money(r.in) : '—'}
            </td>
            <td style="padding:10px 14px;text-align:right;font-weight:700;${r.out > 0 ? 'color:#dc2626' : 'color:var(--text-muted)'}">
              ${r.out > 0 ? money(r.out) : '—'}
            </td>
          </tr>
        `).join('') : `
          <tr>
            <td colspan="7" style="text-align:center;padding:36px;color:var(--text-muted);font-size:13px">
              No entries found for <b>${esc(filterNames[dbFilterType] || dbFilterType)}</b> in the range ${dmy(dbFrom)} to ${dmy(dbTo)}.
            </td>
          </tr>
        `}
      </tbody>
      <tfoot>
        <tr style="background:var(--surface);font-weight:800;border-top:2px solid var(--border)">
          <td colspan="5" style="padding:12px 14px">
            Total Movements (${filtered.length} entries${cancelledCount ? ` • ${cancelledCount} cancelled` : ''})
          </td>
          <td style="padding:12px 14px;text-align:right;color:#16a34a">${money(totalInward)}</td>
          <td style="padding:12px 14px;text-align:right;color:#dc2626">${money(totalOutward)}</td>
        </tr>
      </tfoot>
    </table>
  </div>
  `;
}
'''

# Replace function scrDaybook() block
daybook_start_idx = c.find('function scrDaybook(){')
if daybook_start_idx != -1:
    # Find end of scrDaybook
    daybook_end_idx = c.find('function daybookCSV(){', daybook_start_idx)
    if daybook_end_idx != -1:
        c = c[:daybook_start_idx] + daybook_js + '\n\n' + c[daybook_end_idx:]
        print("Replaced scrDaybook with modern filter-first Day Book & Cancelled Bills report")
    else:
        print("ERROR: could not locate end of scrDaybook")
else:
    print("ERROR: could not locate function scrDaybook(){")

# Save updated hotel_erp.html
html_path.write_text(c, encoding="utf-8")
print(f"Done! New file length: {len(c)}")

