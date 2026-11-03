from pathlib import Path
import re

p = Path("hotel-erp/hotel_erp.html")
c = p.read_text(encoding="utf-8")

# 1. Update line 1830 sidebar section header
c = re.sub(
    r'html\[data-theme\^="horeca_"\] #side \.side-section-header\{[^}]+\}',
    '''html[data-theme^="horeca_"] #side .side-section-header{
  margin:12px 4px 4px;padding:7px 9px;
  font-size:10px;font-weight:800;letter-spacing:.095em;
  text-transform:uppercase;color:#e2e8f0!important;border-radius:8px;
}''',
    c,
    count=1
)

# 2. Update line 1835 nav item text
c = re.sub(
    r'html\[data-theme\^="horeca_"\] #side \.nav-item\{[^}]+\}',
    '''html[data-theme^="horeca_"] #side .nav-item{
  color:#f8fafc!important;
  background:transparent!important;border-radius:10px!important;
  min-height:38px;padding:9px 10px!important;margin:1px 0;
  font-weight:600!important;line-height:1.3;gap:10px;
  border:1px solid transparent!important;
  transition:background .16s,color .16s,border-color .16s;
}''',
    c,
    count=1
)

# 3. Update line 1843 nav icon
c = re.sub(
    r'html\[data-theme\^="horeca_"\] #side \.nav-item \.nav-icon\{[^}]+\}',
    '''html[data-theme^="horeca_"] #side .nav-item .nav-icon{
  flex:0 0 18px;width:18px;display:flex;align-items:center;justify-content:center;
  color:#cbd5e1!important;
}''',
    c,
    count=1
)

# 4. Also check line 2617 section header
c = re.sub(
    r'html\[data-theme\^="horeca_"\] #side \.side-section-header\{\s*margin:13px 6px 6px!important;padding:7px 5px!important;\s*font-size:11px!important;color:[^;]+!important;font-weight:800!important;\s*letter-spacing:\.09em!important;text-transform:uppercase!important\s*\}',
    '''html[data-theme^="horeca_"] #side .side-section-header{
  margin:13px 6px 6px!important;padding:7px 5px!important;
  font-size:11px!important;color:#e2e8f0!important;font-weight:800!important;
  letter-spacing:.09em!important;text-transform:uppercase!important
}''',
    c
)

p.write_text(c, encoding="utf-8")
print("Enhanced high contrast in sidebar rules successfully!")

