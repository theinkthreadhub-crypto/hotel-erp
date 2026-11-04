import sys
sys.stdout.reconfigure(encoding='utf-8')

with open('hotel_erp.html', 'r', encoding='utf-8') as f:
    text = f.read()

pos_menu = text.find('const MENU = [')
pos_alias = text.find('const MENU_ALIAS =', pos_menu)
pos_screens = text.find('const SCREENS = {', pos_alias)
pos_ho_help = text.find('const HO_HELP = {')

print("MENU to ALIAS:")
print(text[pos_alias-200:pos_alias+200])

print("\nSCREENS start:")
print(text[pos_screens:pos_screens+300])

print("\nHO_HELP start:")
print(text[pos_ho_help:pos_ho_help+300])
