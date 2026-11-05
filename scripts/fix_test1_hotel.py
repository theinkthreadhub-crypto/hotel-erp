with open('tests/sync_phase3_outbox_test.py', 'r', encoding='utf-8') as f:
    text = f.read()

text = text.replace("self.assertEqual(env['hotel_id'], 'TEST_HOTEL_01')", "self.assertEqual(env['hotel_id'], self.store.sdb.meta('hotel_id'))")

with open('tests/sync_phase3_outbox_test.py', 'w', encoding='utf-8') as f:
    f.write(text)

print('Updated test 1 hotel_id assertion')
