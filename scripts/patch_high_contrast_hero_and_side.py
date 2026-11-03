from pathlib import Path
import re

p = Path("hotel-erp/hotel_erp.html")
c = p.read_text(encoding="utf-8")

contrast_css = '''
/* ================= HIGH CONTRAST DASHBOARD HERO & SIDEBAR OVERRIDES ================= */
.m-hero,
#main .m-hero,
html[data-theme^="horeca_"] #main .m-hero {
  background: linear-gradient(135deg, #0b172c 0%, #172a45 60%, #1e3a5f 100%) !important;
  color: #ffffff !important;
  border-radius: 14px !important;
  border: 1px solid rgba(255, 255, 255, 0.12) !important;
  box-shadow: 0 4px 20px rgba(0, 0, 0, 0.15) !important;
}

.m-hero h2,
#main .m-hero h2,
html[data-theme^="horeca_"] #main .m-hero h2 {
  color: #ffffff !important;
  font-size: 22px !important;
  font-weight: 900 !important;
  margin: 0 0 6px !important;
  letter-spacing: -0.3px !important;
  text-shadow: 0 2px 4px rgba(0, 0, 0, 0.4) !important;
}

.m-hero p,
#main .m-hero p,
html[data-theme^="horeca_"] #main .m-hero p {
  color: #e2e8f0 !important;
  font-size: 13px !important;
  font-weight: 600 !important;
  margin: 0 !important;
  opacity: 1 !important;
  text-shadow: 0 1px 2px rgba(0, 0, 0, 0.3) !important;
}

/* Sidebar Section Headers: Ultra High Contrast */
#side .side-section-header,
#side .side-section-header span,
html[data-theme^="horeca_"] #side .side-section-header,
html[data-theme^="horeca_"] #side .side-section-header span {
  color: #f8fafc !important;
  font-size: 11px !important;
  font-weight: 850 !important;
  letter-spacing: 0.08em !important;
  text-transform: uppercase !important;
  text-shadow: 0 1px 2px rgba(0, 0, 0, 0.4) !important;
}

/* Sidebar Nav Items: Bright Crisp Text and Icons */
#side .nav-item,
html[data-theme^="horeca_"] #side .nav-item {
  color: #f1f5f9 !important;
}

#side .nav-item .nav-label,
html[data-theme^="horeca_"] #side .nav-item .nav-label {
  color: #f1f5f9 !important;
  font-weight: 600 !important;
}

#side .nav-item .nav-icon,
html[data-theme^="horeca_"] #side .nav-item .nav-icon {
  color: #cbd5e1 !important;
}

#side .nav-item:hover,
html[data-theme^="horeca_"] #side .nav-item:hover {
  background: rgba(255, 255, 255, 0.12) !important;
  color: #ffffff !important;
}

#side .nav-item:hover .nav-label {
  color: #ffffff !important;
}

#side .nav-item:hover .nav-icon {
  color: #FF9707 !important;
}

#side .nav-item.active,
html[data-theme^="horeca_"] #side .nav-item.active {
  background: linear-gradient(135deg, #FF9707 0%, #ea580c 100%) !important;
  color: #ffffff !important;
  border: 1px solid rgba(255, 151, 7, 0.4) !important;
  box-shadow: 0 4px 14px rgba(255, 151, 7, 0.35) !important;
}

#side .nav-item.active .nav-label,
#side .nav-item.active .nav-icon {
  color: #ffffff !important;
}

/* Day Book & Ledger Report Table Styling */
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
}
'''

# Inject right before </style>
if '</style>' in c:
    c = c.replace('</style>', contrast_css + '\n</style>', 1)
    print("Injected high-contrast styles for hero banner, sidebar headers, and Day Book table")

p.write_text(c, encoding="utf-8")
print(f"Patched successfully! Length: {len(c)}")
