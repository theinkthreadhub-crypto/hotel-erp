# Writes the build's version into hotel_erp.html before the EXE is packed (used by build-exe.yml).
import sys

version = sys.argv[1]
path = 'hotel_erp.html'
text = open(path, encoding='utf-8').read()
mark = "const APP_VERSION = 'dev';"
if mark not in text:
    sys.exit('APP_VERSION line not found in hotel_erp.html')
open(path, 'w', encoding='utf-8', newline='').write(text.replace(mark, f"const APP_VERSION = '{version}';"))
print('Setu version', version)
