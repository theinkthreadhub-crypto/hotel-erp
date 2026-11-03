from pathlib import Path

p = Path(r"c:\Users\jjcka\OneDrive\Desktop\School\snaoke eor\hotel-erp\cloud\wrangler.toml")
text = p.read_text(encoding="utf-8")

old_routes = '''routes = [
  { pattern = "hotel.setupro.in", custom_domain = true }
]'''

new_routes = '''workers_dev = true
routes = [
  { pattern = "hotel.setupro.in/*", zone_name = "setupro.in" }
]'''

text = text.replace(old_routes, new_routes)
p.write_text(text, encoding="utf-8")
print("Updated to zone_name = setupro.in and workers_dev = true")

