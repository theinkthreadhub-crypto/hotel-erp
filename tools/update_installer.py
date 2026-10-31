import os

path = r'c:\Users\jjcka\OneDrive\Desktop\School\snaoke eor\hotel-erp\Install-Aghanya-Devanya-ERP-Setup.bat'
with open(path, 'r', encoding='utf-8') as f:
    text = f.read()

target = 'copy /Y "%SCRIPT_DIR%favicon.ico" "%INSTALL_DIR%\\" >nul\n'
if '\r\n' in text:
    target = 'copy /Y "%SCRIPT_DIR%favicon.ico" "%INSTALL_DIR%\\" >nul\r\n'

addition = (
    'if exist "%SCRIPT_DIR%food" xcopy /E /I /Y "%SCRIPT_DIR%food" "%INSTALL_DIR%\\food" >nul\n'
    'if exist "%SCRIPT_DIR%Foodpiolet_Real_Food_Images" xcopy /E /I /Y "%SCRIPT_DIR%Foodpiolet_Real_Food_Images" "%INSTALL_DIR%\\Foodpiolet_Real_Food_Images" >nul\n'
)
if '\r\n' in text:
    addition = addition.replace('\n', '\r\n')

if target in text:
    text = text.replace(target, target + addition)
    with open(path, 'w', encoding='utf-8') as f:
        f.write(text)
    print("Updated successfully!")
else:
    print("Target not found in text")

