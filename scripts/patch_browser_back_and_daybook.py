import re

with open('hotel_erp.html', 'r', encoding='utf-8') as f:
    content = f.read()

# 1. Update goBackOrDashboard and popstate handler
old_history_block = '''let _screenHistory = [];

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
});'''

new_history_block = '''let _screenHistory = [];

function backToDaybookFilter(){
  dbSubmitted = false;
  if(window.history && window.history.state && window.history.state.sub === 'report'){
    window.history.back();
  } else {
    scrDaybook();
  }
}

function goBackOrDashboard(){
  // 1. If inside Day Book Report, go back to Day Book Filter screen
  if(cur === 'daybook' && typeof dbSubmitted !== 'undefined' && dbSubmitted){
    backToDaybookFilter();
    return;
  }
  
  // 2. Use browser history if available
  if(window.history && window.history.length > 1 && window.location.hash && window.location.hash !== '#gateway'){
    window.history.back();
    return;
  }

  // 3. Fallback to in-memory screen history
  if(_screenHistory.length > 0){
    const prev = _screenHistory.pop();
    if(prev && prev !== cur){
      go(prev, true, true);
      return;
    }
  }

  // 4. Fallback to Gateway Dashboard
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

// HTML5 Popstate Handler: Makes Chrome's browser back button navigate screens instead of exiting website
window.addEventListener('popstate', (e) => {
  const state = e.state;
  if(typeof activeUser === 'undefined' || !activeUser) return;

  if(!state || !state.screen || state.screen === 'gateway'){
    if(cur === 'daybook' && typeof dbSubmitted !== 'undefined' && dbSubmitted){
      dbSubmitted = false;
      scrDaybook();
      return;
    }
    if(cur !== 'gateway'){
      go('gateway', true, true);
    }
    return;
  }

  if(state.screen === 'daybook'){
    if(state.sub === 'report'){
      dbSubmitted = true;
      go('daybook', true, true);
    } else {
      dbSubmitted = false;
      go('daybook', true, true);
    }
  } else {
    go(state.screen, true, true);
  }
});'''

assert old_history_block in content, "old_history_block not found"
content = content.replace(old_history_block, new_history_block, 1)

# 2. Update go(s, approved, isBack) to pushState to browser history
old_go_push = '''  if(!isBack && cur && cur !== s){
    if(_screenHistory.length >= 30) _screenHistory.shift();
    if(!_screenHistory.length || _screenHistory[_screenHistory.length - 1] !== cur){
      _screenHistory.push(cur);
    }
  }'''

new_go_push = '''  if(!isBack && cur && cur !== s){
    if(_screenHistory.length >= 30) _screenHistory.shift();
    if(!_screenHistory.length || _screenHistory[_screenHistory.length - 1] !== cur){
      _screenHistory.push(cur);
    }
    if(window.history && window.history.pushState){
      const targetHash = '#' + s;
      if(window.location.hash !== targetHash){
        window.history.pushState({ screen: s, sub: null }, '', targetHash);
      }
    }
  }'''

assert old_go_push in content, "old_go_push not found"
content = content.replace(old_go_push, new_go_push, 1)

# 3. Update top-back-btn text in go() so it says clean "← Back" everywhere instead of "← Back to Dashboard"
old_top_btn = '''  const bBtn = $('#top-back-btn');
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

new_top_btn = '''  const bBtn = $('#top-back-btn');
  if(bBtn){
    bBtn.innerHTML = '<span style="font-size:15px;font-weight:900">←</span> Back';
    if(s === 'gateway'){
      bBtn.title = _screenHistory.length ? 'Back to previous screen' : 'Gateway Dashboard';
      bBtn.style.display = _screenHistory.length ? 'inline-flex' : 'none';
    } else {
      bBtn.title = 'Back (Alt + Left)';
      bBtn.style.display = 'inline-flex';
    }
  }'''

assert old_top_btn in content, "old_top_btn not found"
content = content.replace(old_top_btn, new_top_btn, 1)

# 4. Update submitDaybookFilter() to push history state for #daybook-report
old_submit_filter = '''function submitDaybookFilter(){
  dbFrom = $('#db_form_start').value || today();
  dbTo = $('#db_form_end').value || dbFrom;
  dbFilterType = $('#db_form_type').value || 'all';
  dbUser = $('#db_form_user').value || 'all';
  dbOrder = $('#db_form_order').value || 'date_asc';
  dbSubmitted = true;
  scrDaybook();
}'''

new_submit_filter = '''function submitDaybookFilter(){
  dbFrom = $('#db_form_start').value || today();
  dbTo = $('#db_form_end').value || dbFrom;
  dbFilterType = $('#db_form_type').value || 'all';
  dbUser = $('#db_form_user').value || 'all';
  dbOrder = $('#db_form_order').value || 'date_asc';
  dbSubmitted = true;
  if(window.history && window.history.pushState){
    window.history.pushState({ screen: 'daybook', sub: 'report' }, '', '#daybook-report');
  }
  scrDaybook();
}'''

assert old_submit_filter in content, "old_submit_filter not found"
content = content.replace(old_submit_filter, new_submit_filter, 1)

# 5. Replace "Back to Dashboard" in Daybook and Guide screens
# Daybook filter header:
content = content.replace(
    '''<button class="btn sm" onclick="goBackOrDashboard()" style="padding:6px 14px;font-weight:800;border:1.5px solid #1e293b;background:#f8fafc;color:#08080E">← Back to Dashboard</button>
          <div>
            <h2 style="margin:0 0 4px;font-size:20px;font-weight:800;color:#08080E">Day Book & Ledger Filter</h2>''',
    '''<button class="btn sm" onclick="goBackOrDashboard()" style="padding:6px 14px;font-weight:800;border:1.5px solid #1e293b;background:#f8fafc;color:#08080E">← Back</button>
          <div>
            <h2 style="margin:0 0 4px;font-size:20px;font-weight:800;color:#08080E">Day Book & Ledger Filter</h2>'''
)

# Daybook filter footer:
content = content.replace(
    '''<button type="button" class="btn" onclick="goBackOrDashboard()" style="padding:10px 18px;font-size:13px;font-weight:800;border:1.5px solid #334155;color:#08080E;background:#f8fafc">← Back to Dashboard</button>''',
    '''<button type="button" class="btn" onclick="goBackOrDashboard()" style="padding:10px 18px;font-size:13px;font-weight:800;border:1.5px solid #334155;color:#08080E;background:#f8fafc">← Back</button>'''
)

# Daybook report action bar:
content = content.replace(
    '''    <div style="display:flex;align-items:center;gap:8px;flex-wrap:wrap">
      <button class="btn sm" onclick="goBackOrDashboard()" style="padding:6px 14px;font-weight:800;border:1.5px solid #1e293b;background:#f8fafc;color:#08080E">← Back to Dashboard</button>
      <button class="btn sm" onclick="dbSubmitted=false;scrDaybook()" style="padding:6px 14px;font-weight:800;border:1.5px solid #1e293b;background:#f8fafc;color:#08080E">''',
    '''    <div style="display:flex;align-items:center;gap:8px;flex-wrap:wrap">
      <button class="btn sm" onclick="backToDaybookFilter()" style="padding:6px 14px;font-weight:800;border:1.5px solid #1e293b;background:#f8fafc;color:#08080E">← Back to Filter</button>
      <button class="btn sm" onclick="backToDaybookFilter()" style="padding:6px 14px;font-weight:800;border:1.5px solid #1e293b;background:#f8fafc;color:#08080E">'''
)

# Guide screens:
content = content.replace(
    '''<button class='btn sm' onclick='goBackOrDashboard()' style='padding:6px 14px;font-weight:800;border:1.5px solid #1e293b;background:#f8fafc;color:#08080E'>← Back to Dashboard</button>''',
    '''<button class='btn sm' onclick='goBackOrDashboard()' style='padding:6px 14px;font-weight:800;border:1.5px solid #1e293b;background:#f8fafc;color:#08080E'>← Back</button>'''
)

# 6. Initialize baseline state on bootstrap so Chrome knows root
init_target = 'if(activeUser) go(\'gateway\');'
init_replacement = '''if(activeUser){
    if(window.history && window.history.replaceState && !window.history.state){
      window.history.replaceState({ screen: 'gateway', sub: null }, '', '#gateway');
    }
    go('gateway');
  }'''
assert init_target in content, "init_target not found"
content = content.replace(init_target, init_replacement, 1)

with open('hotel_erp.html', 'w', encoding='utf-8') as f:
    f.write(content)

print("Browser back and Daybook filter navigation successfully patched!")

