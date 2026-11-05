with open('setu_sqlite.py', 'r', encoding='utf-8') as f:
    text = f.read()

text = text.replace("c.execute('INSERT INTO sync_outbox", "cur = c.execute('INSERT INTO sync_outbox")
text = text.replace("return c.lastrowid", "return cur.lastrowid")

with open('setu_sqlite.py', 'w', encoding='utf-8') as f:
    f.write(text)

print('Updated append_outbox in setu_sqlite.py')
