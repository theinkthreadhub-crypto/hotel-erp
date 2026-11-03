from pathlib import Path

p = Path(r"c:\Users\jjcka\OneDrive\Desktop\School\snaoke eor\hotel-erp\cloud\wrangler.toml")
text = p.read_text(encoding="utf-8")

# Remove routes from [vars]
text = text.replace('''routes = [
  { pattern = "hotel.setupro.in", custom_domain = true }
]''', '')

# Place routes at top
route_block = '''name = "setu-cloud"
main = "src/worker.js"
compatibility_date = "2025-09-01"
keep_vars = true

routes = [
  { pattern = "hotel.setupro.in", custom_domain = true }
]
'''

text = text.replace('''name = "setu-cloud"
main = "src/worker.js"
compatibility_date = "2025-09-01"
# Like Library ERP: settings added in the Cloudflare dashboard survive a deploy from GitHub
keep_vars = true''', route_block)

p.write_text(text, encoding="utf-8")
print("Placed routes at root level in wrangler.toml")

