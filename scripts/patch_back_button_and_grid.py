import re

with open('hotel_erp.html', 'r', encoding='utf-8') as f:
    content = f.read()

# 1. Update theme variables in html[data-theme="horeca_light"]
theme_target = '''html[data-theme="horeca_light"] {
  --primary: #f97316;
  --primary-dark: #ea580c;
  --primary-light: #ffedd5;
  --accent: #f97316;
  --bg: #f8fafc;
  --panel: #ffffff;
  --surface: #f1f5f9;
  --border: #e2e8f0;
  --border-focus: #fb923c;
  --text: #0f172a;
  --text-muted: #64748b;'''

theme_replacement = '''html[data-theme="horeca_light"] {
  --primary: #f97316;
  --primary-dark: #ea580c;
  --primary-light: #ffedd5;
  --accent: #f97316;
  --bg: #f8fafc;
  --panel: #ffffff;
  --surface: #f1f5f9;
  --border: #64748b;
  --border-focus: #fb923c;
  --text: #08080E;
  --text-muted: #1e293b;'''

assert theme_target in content, "Theme light target not found"
content = content.replace(theme_target, theme_replacement, 1)

# 2. Add comprehensive High-Contrast Table Grid Lines, Dark Button Borders & Top Back Button CSS
css_target = '''/* Day Book & Ledger Report Table Styling */
body[data-horeca-screen="daybook"] #main table,
#main table {
  border-collapse: collapse !important;
}

body[data-horeca-screen="daybook"] #main table thead tr th {
  background: #f1f5f9 !important;
  color: #0f172a !important;
  font-weight: 800 !important;
  font-size: 11.5px !important;
  border-bottom: 2px solid #cbd5e1 !important;
}

body[data-horeca-screen="daybook"] #main table tbody tr td {
  color: #0f172a !important;
  border-bottom: 1px solid #e2e8f0 !important;
}'''

css_replacement = '''/* ==========================================================================
   GLOBAL HIGH-CONTRAST ERP GRID TABLES, DARK BORDERS & READABILITY
   ========================================================================== */

/* Universal High Contrast Table Grid with Column Separators & Row Borders */
table,
.card table,
.ent-table-card table,
.table-wrap table,
#main table {
  width: 100% !important;
  border-collapse: collapse !important;
  border: 1.5px solid #475569 !important;
  background: #ffffff !important;
  color: #08080E !important;
}

table thead tr th,
.card table thead tr th,
.ent-table-card th,
.table-wrap th,
#main table thead tr th,
body[data-horeca-screen="daybook"] #main table thead tr th {
  background: #f1f5f9 !important;
  color: #08080E !important;
  font-weight: 800 !important;
  font-size: 11.5px !important;
  letter-spacing: 0.04em !important;
  padding: 10px 14px !important;
  border: 1px solid #64748b !important; /* Visible column lines in header */
  border-bottom: 2px solid #334155 !important;
  text-transform: uppercase !important;
}

table tbody tr td,
.card table tbody tr td,
.ent-table-card td,
.table-wrap td,
#main table tbody tr td,
body[data-horeca-screen="daybook"] #main table tbody tr td {
  color: #08080E !important;
  font-weight: 600 !important;
  font-size: 12.5px !important;
  padding: 9px 12px !important;
  border: 1px solid #cbd5e1 !important; /* Visible column and row lines in all data cells */
}

table tbody tr:nth-child(even),
#main table tbody tr:nth-child(even) {
  background: #f8fafc !important;
}

table tbody tr:hover,
#main table tbody tr:hover {
  background: #f1f5f9 !important;
}

table tfoot tr td,
.card table tfoot tr td,
.ent-table-card tfoot td,
#main table tfoot tr td {
  background: #f1f5f9 !important;
  color: #08080E !important;
  font-weight: 800 !important;
  border: 1px solid #64748b !important;
  border-top: 2px solid #334155 !important;
}

/* Universal Dark Borders on All Buttons Across Application */
.btn,
button:not(#side button):not(#sidebtn):not(.horeca-nav-item):not(.sub-item) {
  border: 1.5px solid #334155 !important;
  color: #08080E !important;
  font-weight: 750 !important;
}

.btn:hover,
button:not(#side button):not(#sidebtn):not(.horeca-nav-item):not(.sub-item):hover {
  border-color: #08080E !important;
}

.btn.ok, .btn-primary, .btn-login-gradient {
  background: linear-gradient(135deg, #FF9707 0%, #ea580c 100%) !important;
  border: 1.5px solid #c2410c !important;
  color: #ffffff !important;
  font-weight: 800 !important;
}

.btn.g {
  background: #ffffff !important;
  border: 1.5px solid #334155 !important;
  color: #08080E !important;
  font-weight: 750 !important;
}

.cat {
  border: 1.5px solid #475569 !important;
  color: #08080E !important;
  font-weight: 750 !important;
  background: #ffffff !important;
  border-radius: 8px !important;
  padding: 7px 14px !important;
}

.cat.active, .cat[style*="background:var(--primary)"] {
  border: 1.5px solid #c2410c !important;
  color: #ffffff !important;
  background: var(--primary) !important;
}

/* Universal Dark High Contrast Text */
#main,
#main p,
#main div,
#main label,
#main b,
#main strong,
.card,
.card b,
.card span {
  color: #08080E;
}

#main .text-muted,
#main [style*="color:var(--text-muted)"],
#main [style*="color: var(--text-muted)"],
.muted {
  color: #1e293b !important;
  font-weight: 600;
}

/* Dedicated Top Navigation Back Button */
.top-back-btn {
  display: inline-flex !important;
  align-items: center !important;
  gap: 6px !important;
  padding: 5px 14px !important;
  margin: 0 10px !important;
  font-size: 13px !important;
  font-weight: 800 !important;
  color: #08080E !important;
  background: #ffffff !important;
  border: 1.5px solid #1e293b !important;
  border-radius: 8px !important;
  cursor: pointer !important;
  box-shadow: 0 1px 3px rgba(0,0,0,0.08) !important;
  transition: all 0.15s ease !important;
  flex-shrink: 0 !important;
}

.top-back-btn:hover {
  background: #f1f5f9 !important;
  border-color: #08080E !important;
  transform: translateX(-1px) !important;
}

/* Clear Dark Outlines on Cards & Panels */
.card,
.ent-card,
.m-hero,
.m-kpi,
.panel {
  border: 1.5px solid #94a3b8 !important;
}'''

assert css_target in content, "CSS target not found"
content = content.replace(css_target, css_replacement, 1)

# 3. Add top navigation Back button before #scrname
top_target = '''      <div style="display:flex;align-items:center;gap:6px;font-size:10px;font-weight:700;color:var(--text-muted)">
        <span id="hsub">Hotel • Restaurant • Café</span>
      </div>
    </div>
  </div>

  <span class="scr" id="scrname"><span class="dot"></span>Gateway</span>'''

top_replacement = '''      <div style="display:flex;align-items:center;gap:6px;font-size:10px;font-weight:700;color:var(--text-muted)">
        <span id="hsub">Hotel • Restaurant • Café</span>
      </div>
    </div>
  </div>

  <button id="top-back-btn" class="top-back-btn" onclick="goBackOrDashboard()" title="Go Back to Previous Screen / Dashboard (Backspace / Alt+Left)">
    <span style="font-size:15px;font-weight:900">←</span> Back
  </button>
  <span class="scr" id="scrname"><span class="dot"></span>Gateway</span>'''

assert top_target in content, "Top header target not found"
content = content.replace(top_target, top_replacement, 1)

# 4. Update go() function and add navigation history stack
go_target = '''// Current staff member's ticked screens (looked up fresh so Staff edits apply at once)
const userPerms = () => { const st = activeUser && activeUser.staffId && (D.staff || []).find(x => x.id === activeUser.staffId); return (st && st.perms) || []; };

function go(s, approved){'''

go_replacement = '''// Current staff member's ticked screens (looked up fresh so Staff edits apply at once)
const userPerms = () => { const st = activeUser && activeUser.staffId && (D.staff || []).find(x => x.id === activeUser.staffId); return (st && st.perms) || []; };

let _screenHistory = [];

function goBackOrDashboard(){
  if(_screenHistory.length > 0){
    const prev = _screenHistory.pop();
    if(prev && prev !== cur){
      go(prev, true, true);
      return;
    }
  }
  if(cur !== 'gateway'){
    go('gateway', true, true);
  } else {
    toast('You are on the main Gateway Dashboard.');
  }
}

// Global keyboard shortcut: Alt+Left or Escape (outside modals) to go back
window.addEventListener('keydown', (e) => {
  if((e.altKey && e.key === 'ArrowLeft') || (e.key === 'Escape' && cur !== 'gateway' && !document.querySelector('.modal-backdrop, .modal, #login-screen:not([style*="display: none"])'))){
    goBackOrDashboard();
  }
});

function go(s, approved, isBack){
  if(!isBack && cur && cur !== s){
    if(_screenHistory.length >= 30) _screenHistory.shift();
    if(!_screenHistory.length || _screenHistory[_screenHistory.length - 1] !== cur){
      _screenHistory.push(cur);
    }
  }'''

assert go_target in content, "go() target not found"
content = content.replace(go_target, go_replacement, 1)

# Also update the top-back-btn inside go(s)
go_end_target = '''  $('#scrname').innerHTML = `<span class="dot"></span>${m ? m[1] : 'Gateway of Restaurant'}`;
  $('#hname').textContent = D.settings.name;'''

go_end_replacement = '''  $('#scrname').innerHTML = `<span class="dot"></span>${m ? m[1] : 'Gateway of Restaurant'}`;
  $('#hname').textContent = D.settings.name;
  const bBtn = $('#top-back-btn');
  if(bBtn){
    if(s === 'gateway'){
      bBtn.innerHTML = '<span style="font-size:15px;font-weight:900">←</span> Back';
      bBtn.title = _screenHistory.length ? 'Back to previous screen' : 'Gateway Dashboard';
      bBtn.style.display = _screenHistory.length ? 'inline-flex' : 'none';
    } else {
      bBtn.innerHTML = '<span style="font-size:15px;font-weight:900">←</span> Back to Dashboard';
      bBtn.title = 'Back to Gateway Dashboard (Alt + Left)';
      bBtn.style.display = 'inline-flex';
    }
  }'''

assert go_end_target in content, "go() end target not found"
content = content.replace(go_end_target, go_end_replacement, 1)

# 5. Add Back to Dashboard button in scrDaybook() filter form
daybook_filter_target = '''      <div style="border-bottom:1px solid var(--border);padding-bottom:16px;margin-bottom:24px;display:flex;align-items:center;justify-content:space-between">
        <div>
          <h2 style="margin:0 0 4px;font-size:20px;font-weight:800;color:var(--text)">Day Book & Ledger Filter</h2>
          <p style="margin:0;font-size:12px;color:var(--text-muted)">Select dates, voucher type and parameters to generate the day book ledger</p>
        </div>
        <button class="btn sm" onclick="dbSubmitted=true;scrDaybook()" style="font-weight:700">Quick View Today &rarr;</button>
      </div>'''

daybook_filter_replacement = '''      <div style="border-bottom:1.5px solid #64748b;padding-bottom:16px;margin-bottom:24px;display:flex;align-items:center;justify-content:space-between;flex-wrap:wrap;gap:10px">
        <div style="display:flex;align-items:center;gap:12px">
          <button class="btn sm" onclick="goBackOrDashboard()" style="padding:6px 14px;font-weight:800;border:1.5px solid #1e293b;background:#f8fafc;color:#08080E">← Back to Dashboard</button>
          <div>
            <h2 style="margin:0 0 4px;font-size:20px;font-weight:800;color:#08080E">Day Book & Ledger Filter</h2>
            <p style="margin:0;font-size:12px;color:#1e293b;font-weight:600">Select dates, voucher type and parameters to generate the day book ledger</p>
          </div>
        </div>
        <button class="btn sm" onclick="dbSubmitted=true;scrDaybook()" style="font-weight:800;border:1.5px solid #334155">Quick View Today &rarr;</button>
      </div>'''

assert daybook_filter_target in content, "daybook filter header target not found"
content = content.replace(daybook_filter_target, daybook_filter_replacement, 1)

# 6. Add Back button in scrDaybook() form buttons
daybook_btn_target = '''          <div style="display:flex;gap:10px">
            <button type="submit" class="btn ok" style="padding:10px 28px;font-size:14px;font-weight:800;border-radius:8px;background:#1e293b;color:#fff">Submit</button>
            <button type="button" class="btn" onclick="dbFrom=dbTo=today();dbFilterType='all';dbSubmitted=true;scrDaybook()" style="padding:10px 18px;font-size:13px;font-weight:700">Today's Quick Book</button>
          </div>'''

daybook_btn_replacement = '''          <div style="display:flex;gap:10px;align-items:center;flex-wrap:wrap">
            <button type="submit" class="btn ok" style="padding:10px 28px;font-size:14px;font-weight:800;border-radius:8px;background:#1e293b;color:#fff;border:1.5px solid #08080E">Submit</button>
            <button type="button" class="btn" onclick="dbFrom=dbTo=today();dbFilterType='all';dbSubmitted=true;scrDaybook()" style="padding:10px 18px;font-size:13px;font-weight:800;border:1.5px solid #334155;color:#08080E;background:#fff">Today's Quick Book</button>
            <button type="button" class="btn" onclick="goBackOrDashboard()" style="padding:10px 18px;font-size:13px;font-weight:800;border:1.5px solid #334155;color:#08080E;background:#f8fafc">← Back to Dashboard</button>
          </div>'''

assert daybook_btn_target in content, "daybook btn target not found"
content = content.replace(daybook_btn_target, daybook_btn_replacement, 1)

# 7. Add Back to Dashboard button in renderDaybookReportScreen()
report_header_target = '''  <div style="margin-bottom:14px;display:flex;align-items:center;justify-content:space-between;flex-wrap:wrap;gap:10px">
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
  </div>'''

report_header_replacement = '''  <div style="margin-bottom:14px;display:flex;align-items:center;justify-content:space-between;flex-wrap:wrap;gap:10px">
    <div style="display:flex;align-items:center;gap:8px;flex-wrap:wrap">
      <button class="btn sm" onclick="goBackOrDashboard()" style="padding:6px 14px;font-weight:800;border:1.5px solid #1e293b;background:#f8fafc;color:#08080E">← Back to Dashboard</button>
      <button class="btn sm" onclick="dbSubmitted=false;scrDaybook()" style="padding:6px 14px;font-weight:800;border:1.5px solid #1e293b;background:#f8fafc;color:#08080E">🔍 Change Filter / New Search</button>
      <button class="btn sm" onclick="printDaybook()" style="padding:6px 16px;font-weight:800;border:1.5px solid #334155;color:#08080E;background:#fff">Print</button>
      <button class="btn ok sm" onclick="daybookPDF()" style="padding:6px 16px;font-weight:800;background:#2563eb;color:#fff;border:1.5px solid #1d4ed8">PDF</button>
      <button class="btn g sm" onclick="daybookCSV()" style="padding:6px 16px;font-weight:800;border:1.5px solid #334155;color:#08080E;background:#fff">Excel</button>
    </div>
    <div style="font-size:13px;font-weight:800;color:#08080E">
      <span>Period: <b style="color:#08080E">${dmy(dbFrom)}</b> to <b style="color:#08080E">${dmy(dbTo)}</b></span>
      <span style="margin:0 6px">•</span>
      <span style="color:#ea580c;font-weight:800">${filterNames[dbFilterType] || 'Filtered'}</span>
    </div>
  </div>'''

assert report_header_target in content, "report header target not found"
content = content.replace(report_header_target, report_header_replacement, 1)

# 8. Add Back buttons in scrHoGuide() and hoRenderLesson()
guide_target = r'''function scrHoGuide(){
 const a=HO_HELP[hoSelectedGuide];
 if(!a){
  main.innerHTML="<div class='title'>User Guide & Training <span class='r'>"+Object.keys(HO_HELP).length+" topics</span></div>"+
   "<div class='card'><h2>Learn HoReCa One</h2><p class='muted'>Searchable offline instructions for existing modules. Use test data when practicing.</p>"+
   "<input type='search' class='ho-guide-search' maxlength='100' placeholder='Search billing, KOT, printer, GST...' oninput='hoFilterGuide(this.value)' aria-label='Search guide'></div>"+
   "<div id='ho-guide-results' class='ho-learning-grid'>"+Object.keys(HO_HELP).map(hoCard).join("")+"</div>";
  return;
 }
 main.innerHTML="<div class='title'>User Guide / "+esc(a[0])+" <span class='r'><button class='btn g sm' onclick='hoSelectedGuide=\"\";go(\"guide\")'>All Topics</button></span></div>"+
  "<article class='ho-learning-article'><h2>"+esc(a[0])+"</h2><ol>"+a.slice(1).map(step=>"<li>"+esc(step)+"</li>").join("")+"</ol>"+
  "<div class='ho-learning-note'><b>Important:</b> "+esc(HO_HELP_WARN[hoSelectedGuide]||"Actions and availability depend on your role, enabled plan and configured integrations.")+"</div>"+
  "<div class='ho-learning-actions'><button class='btn' onclick='go(\""+hoSelectedGuide+"\")'>Open Module</button>"+
  "<button class='btn g' onclick='hoBeginLesson(\""+hoSelectedGuide+"\")'>Show Me How</button>"+
  "<button class='btn g' onclick='go(\"ai\")'>Ask Setu AI</button></div></article>";
}'''

guide_replacement = r'''function scrHoGuide(){
 const a=HO_HELP[hoSelectedGuide];
 if(!a){
  main.innerHTML="<div style='margin-bottom:12px;display:flex;align-items:center;justify-content:space-between;flex-wrap:wrap;gap:10px'>"+
    "<button class='btn sm' onclick='goBackOrDashboard()' style='padding:6px 14px;font-weight:800;border:1.5px solid #1e293b;background:#f8fafc;color:#08080E'>← Back to Dashboard</button>"+
    "<div class='title' style='margin:0'>User Guide & Training <span class='r'>"+Object.keys(HO_HELP).length+" topics</span></div>"+
    "</div>"+
    "<div class='card' style='border:1.5px solid #94a3b8'><h2>Learn HoReCa One</h2><p class='muted'>Searchable offline instructions for existing modules. Use test data when practicing.</p>"+
    "<input type='search' class='ho-guide-search' maxlength='100' placeholder='Search billing, KOT, printer, GST...' oninput='hoFilterGuide(this.value)' aria-label='Search guide'></div>"+
    "<div id='ho-guide-results' class='ho-learning-grid'>"+Object.keys(HO_HELP).map(hoCard).join("")+"</div>";
  return;
 }
 main.innerHTML="<div style='margin-bottom:12px;display:flex;align-items:center;justify-content:space-between;flex-wrap:wrap;gap:10px'>"+
   "<div style='display:flex;gap:8px'>"+
     "<button class='btn sm' onclick='goBackOrDashboard()' style='padding:6px 14px;font-weight:800;border:1.5px solid #1e293b;background:#f8fafc;color:#08080E'>← Back to Dashboard</button>"+
     "<button class='btn sm g' onclick='hoSelectedGuide=\"\";go(\"guide\")' style='padding:6px 14px;font-weight:800;border:1.5px solid #334155'>All Topics</button>"+
   "</div>"+
   "<div class='title' style='margin:0'>User Guide / "+esc(a[0])+"</div>"+
   "</div>"+
   "<article class='ho-learning-article' style='border:1.5px solid #94a3b8'><h2>"+esc(a[0])+"</h2><ol>"+a.slice(1).map(step=>"<li>"+esc(step)+"</li>").join("")+"</ol>"+
   "<div class='ho-learning-note'><b>Important:</b> "+esc(HO_HELP_WARN[hoSelectedGuide]||"Actions and availability depend on your role, enabled plan and configured integrations.")+"</div>"+
   "<div class='ho-learning-actions'><button class='btn' onclick='go(\""+hoSelectedGuide+"\")' style='border:1.5px solid #334155;font-weight:800'>Open Module</button>"+
   "<button class='btn g' onclick='hoBeginLesson(\""+hoSelectedGuide+"\")' style='border:1.5px solid #334155;font-weight:800'>Show Me How</button>"+
   "<button class='btn g' onclick='go(\"ai\")' style='border:1.5px solid #334155;font-weight:800'>Ask Setu AI</button></div></article>";
}'''

assert guide_target in content, "guide target not found"
content = content.replace(guide_target, guide_replacement, 1)

# 9. Update hoRenderLesson
lesson_start = 'function hoRenderLesson(){'
lesson_end = 'function hoGuideAnswer(q){'
assert lesson_start in content and lesson_end in content, "hoRenderLesson bounds not found"
p1 = content.find(lesson_start)
p2 = content.find(lesson_end)

new_lesson_func = '''function hoRenderLesson(){
 if(!hoLesson)return;
 const a=HO_HELP[hoLesson.id],i=hoLesson.step;
 let p=document.getElementById("ho-lesson-panel");
 if(!p){
   p=document.createElement("div");
   p.id="ho-lesson-panel";
   p.setAttribute("role","dialog");
   p.setAttribute("aria-label","Guided learning");
   document.body.appendChild(p);
 }
 p.innerHTML="<div class='muted' style='font-size:11px;font-weight:800;color:#08080E'>SAFE TRAINING • STEP "+(i+1)+" OF 3</div><h3 style='color:#08080E'>"+esc(a[0])+"</h3>"+
 "<div>"+esc(a[i+1])+"</div><div class='lesson-buttons' style='margin-top:12px;display:flex;gap:8px'>"+
 "<button onclick='hoEndLesson();goBackOrDashboard()' style='border:1.5px solid #334155;font-weight:800;padding:6px 12px;border-radius:6px;background:#f8fafc;color:#08080E'>← Back / Exit</button>"+
 "<button onclick='hoMoveLesson(-1)' "+(i===0?"disabled":"")+" style='border:1.5px solid #334155;font-weight:800;padding:6px 12px;border-radius:6px;background:#fff;color:#08080E'>Previous</button>"+
 "<button class='next' onclick='"+(i===2?"hoEndLesson();goBackOrDashboard()":"hoMoveLesson(1)")+"' style='border:1.5px solid #c2410c;font-weight:800;padding:6px 12px;border-radius:6px;background:var(--primary);color:#fff'>"+(i===2?"Finish & Back":"Next")+"</button></div>";
}
'''

content = content[:p1] + new_lesson_func + content[p2:]

with open('hotel_erp.html', 'w', encoding='utf-8') as f:
    f.write(content)

print("Successfully applied back button, dark text, dark button borders, and column grid lines!")
