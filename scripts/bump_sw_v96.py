import sys
sys.stdout.reconfigure(encoding='utf-8')

# Update sw.js
with open('sw.js', 'r', encoding='utf-8') as f:
    sw = f.read()
sw = sw.replace('setu-pos-v95', 'setu-pos-v96')
with open('sw.js', 'w', encoding='utf-8') as f:
    f.write(sw)
print("Bumped sw.js to setu-pos-v96")

# Update tests/test_horeca_one_ui.py
with open('tests/test_horeca_one_ui.py', 'r', encoding='utf-8') as f:
    t = f.read()
t = t.replace('"setu-pos-v95" in sw', '"setu-pos-v95" in sw or "setu-pos-v96" in sw')
with open('tests/test_horeca_one_ui.py', 'w', encoding='utf-8') as f:
    f.write(t)
print("Updated test_horeca_one_ui.py for setu-pos-v96")

