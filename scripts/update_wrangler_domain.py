from pathlib import Path

p = Path(r"c:\Users\jjcka\OneDrive\Desktop\School\snaoke eor\hotel-erp\cloud\wrangler.toml")
text = p.read_text(encoding="utf-8")

old_text = '# routes = [ { pattern = "app.setupro.in", custom_domain = true }, { pattern = "*.setupro.in/*", zone_name = "setupro.in" } ]'
new_text = '''routes = [
  { pattern = "hotel.setupro.in", custom_domain = true }
]'''

text = text.replace('BASE_DOMAIN = ""', 'BASE_DOMAIN = "setupro.in"')
text = text.replace('APP_HOST = ""', 'APP_HOST = "hotel.setupro.in"')
text = text.replace(old_text, new_text)

p.write_text(text, encoding="utf-8")
print("wrangler.toml updated successfully!")

