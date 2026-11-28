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
# Windows file details (Properties -> Details, Task Manager): company and product name in the program itself
parts = (version.split('.') + ['0', '0', '0', '0'])[:4]
nums = ', '.join(str(int(x)) if x.isdigit() else '0' for x in parts)
open('installer/version_info.txt', 'w', encoding='utf-8').write(f'''VSVersionInfo(
  ffi=FixedFileInfo(filevers=({nums}), prodvers=({nums}), mask=0x3f, flags=0x0, OS=0x40004, fileType=0x1, subtype=0x0, date=(0, 0)),
  kids=[
    StringFileInfo([StringTable('040904B0', [
      StringStruct('CompanyName', 'Aghanya Devanya Enterprises'),
      StringStruct('FileDescription', 'HoReCa One - Restaurant and Hotel POS'),
      StringStruct('FileVersion', '{version}'),
      StringStruct('InternalName', 'Aghanya-Devanya-Hotel-ERP'),
      StringStruct('LegalCopyright', 'Copyright (C) Aghanya Devanya Enterprises'),
      StringStruct('OriginalFilename', 'Aghanya-Devanya-Hotel-ERP.exe'),
      StringStruct('ProductName', 'HoReCa One'),
      StringStruct('ProductVersion', '{version}')])]),
    VarFileInfo([VarStruct('Translation', [1033, 1200])])
  ]
)
''')
print('Setu version', version)
