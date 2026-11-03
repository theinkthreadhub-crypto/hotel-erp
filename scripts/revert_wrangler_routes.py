from pathlib import Path

p = Path(r"c:\Users\jjcka\OneDrive\Desktop\School\snaoke eor\hotel-erp\cloud\wrangler.toml")
text = p.read_text(encoding="utf-8")

bad_route = '''routes = [
  { pattern = "hotel.setupro.in/*", zone_name = "setupro.in" }
]'''

text = text.replace(bad_route, '# routes = [ { pattern = "hotel.setupro.in/*", zone_name = "setupro.in" } ]')
p.write_text(text, encoding="utf-8")
print("Commented out routes in wrangler.toml")
