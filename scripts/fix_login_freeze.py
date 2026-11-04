from pathlib import Path
import re

p = Path("hotel-erp/hotel_erp.html")
c = p.read_text(encoding="utf-8")

# 1. Fix updateUserUI
old_update_user = '''function updateUserUI(){
  if(activeUser){
    $('#top_user_name').textContent = activeUser.name;
    $('#top_user_role').textContent = activeUser.role === 'admin' ? 'Manager' : 'Cashier';
  }
}'''

new_update_user = '''function updateUserUI(){
  if(!activeUser) return;
  const nameEl = $('#top_user_name') || $('#uname');
  if(nameEl) nameEl.textContent = activeUser.name;
  const roleEl = $('#top_user_role') || $('#urole');
  if(roleEl) roleEl.textContent = (activeUser.role === 'admin' || activeUser.access === 'admin') ? 'Manager' : (activeUser.role || 'Staff');
}'''

if old_update_user in c:
    c = c.replace(old_update_user, new_update_user, 1)
    print("Patched updateUserUI (exact match)")
else:
    old_crlf = old_update_user.replace("\n", "\r\n")
    if old_crlf in c:
        c = c.replace(old_crlf, new_update_user, 1)
        print("Patched updateUserUI (CRLF match)")
    else:
        print("Warning: could not match old_update_user directly, using regex...")
        c = re.sub(
            r'function updateUserUI\(\)\{\s*if\(activeUser\)\{\s*\$\(\'#top_user_name\'\)\.textContent[^}]+\}\s*\}',
            new_update_user,
            c
        )

# 2. Make finishLogin bulletproof
old_finish_login = '''function finishLogin(){
  sessionStorage.setItem(AUTH_KEY, JSON.stringify(activeUser));
  localStorage.setItem(AUTH_KEY, JSON.stringify(activeUser));
  audit('Login', `${activeUser.name} (${activeUser.access || activeUser.role})`);
  save();
  updateUserUI();
  $('#login-screen').style.display = 'none';
  toast('Welcome, ' + activeUser.name + '!');

  if(checkExpiryLock()){
    return;
  }
  go(activeUser.access === 'captain' ? 'captain' : 'gateway');
}'''

new_finish_login = '''function finishLogin(){
  try {
    sessionStorage.setItem(AUTH_KEY, JSON.stringify(activeUser));
    localStorage.setItem(AUTH_KEY, JSON.stringify(activeUser));
  } catch(e){}

  try {
    audit('Login', `${activeUser.name} (${activeUser.access || activeUser.role})`);
  } catch(e){}

  try {
    save();
  } catch(e){}

  try {
    updateUserUI();
  } catch(e){}

  try {
    const loginScreen = $('#login-screen');
    if(loginScreen) loginScreen.style.display = 'none';
  } catch(e){}

  toast('Welcome, ' + (activeUser ? activeUser.name : 'User') + '!');

  try {
    if(checkExpiryLock()){
      return;
    }
  } catch(e){}

  try {
    go(activeUser && activeUser.access === 'captain' ? 'captain' : 'gateway');
  } catch(e){
    console.error('Error opening gateway:', e);
  }
}'''

if old_finish_login in c:
    c = c.replace(old_finish_login, new_finish_login, 1)
    print("Patched finishLogin (exact match)")
else:
    old_crlf2 = old_finish_login.replace("\n", "\r\n")
    if old_crlf2 in c:
        c = c.replace(old_crlf2, new_finish_login, 1)
        print("Patched finishLogin (CRLF match)")
    else:
        print("Warning: could not match old_finish_login directly, using regex...")
        c = re.sub(
            r'function finishLogin\(\)\{.*?\n\}',
            new_finish_login,
            c,
            flags=re.DOTALL
        )

p.write_text(c, encoding="utf-8")
print(f"Patched successfully! New length: {len(c)}")

