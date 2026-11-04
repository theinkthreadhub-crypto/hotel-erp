with open('sw.js', 'r', encoding='utf-8') as f:
    text = f.read()

text = text.replace("const CACHE_NAME = 'setu-pos-v96';", "const CACHE_NAME = 'setu-pos-v97';")
with open('sw.js', 'w', encoding='utf-8') as f:
    f.write(text)

with open('tests/test_horeca_one_ui.py', 'r', encoding='utf-8') as f:
    ttext = f.read()

ttext = ttext.replace("'setu-pos-v96'", "'setu-pos-v97'")
with open('tests/test_horeca_one_ui.py', 'w', encoding='utf-8') as f:
    f.write(ttext)

print('Bumped cache to setu-pos-v97 in sw.js and test_horeca_one_ui.py')
