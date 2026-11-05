with open('tests/sqlite_phase2_test.py', 'r', encoding='utf-8') as f:
    text = f.read()

text = text.replace("json.load(open(out))", "json.load(open(out, encoding='utf-8'))")
with open('tests/sqlite_phase2_test.py', 'w', encoding='utf-8') as f:
    f.write(text)
print('Fixed encoding in sqlite_phase2_test.py')
