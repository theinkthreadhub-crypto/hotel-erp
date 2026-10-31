# Writes the build's version into hotel_erp.html and app_main.py before the EXE is packed (used by build-exe.yml).
import sys

version = sys.argv[1]
path = 'hotel_erp.html'
text = open(path, encoding='utf-8').read()
mark = "const APP_VERSION = 'dev';"
if mark not in text:
    sys.exit('APP_VERSION line not found in hotel_erp.html')
open(path, 'w', encoding='utf-8', newline='').write(text.replace(mark, f"const APP_VERSION = '{version}';"))
# The EXE's own version, for the updater (compares it with the newest one on Hotel Setu Cloud)
py = open('app_main.py', encoding='utf-8').read()
pmark = "APP_VERSION = 'dev'"
if pmark not in py:
    sys.exit('APP_VERSION line not found in app_main.py')
open('app_main.py', 'w', encoding='utf-8', newline='').write(py.replace(pmark, f"APP_VERSION = '{version}'", 1))
print('Setu version', version)
