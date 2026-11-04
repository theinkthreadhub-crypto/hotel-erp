from pathlib import Path

sw_path = Path("sw.js")
sw_c = sw_path.read_text(encoding="utf-8")
sw_c = sw_c.replace("setu-pos-v89", "setu-pos-v90")
sw_path.write_text(sw_c, encoding="utf-8")

test_path = Path("tests/test_horeca_one_ui.py")
test_c = test_path.read_text(encoding="utf-8")
test_c = test_c.replace('or "setu-pos-v89" in sw', 'or "setu-pos-v89" in sw or "setu-pos-v90" in sw')
test_path.write_text(test_c, encoding="utf-8")

# In hotel_erp.html also bump register sw query string if any
html_path = Path("hotel_erp.html")
html_c = html_path.read_text(encoding="utf-8")
html_c = html_c.replace("sw.js?v=89", "sw.js?v=90")
html_path.write_text(html_c, encoding="utf-8")

print("Bumped sw.js to setu-pos-v90")
