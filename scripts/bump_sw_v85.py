from pathlib import Path

sw_path = Path("hotel-erp/sw.js")
sw_c = sw_path.read_text(encoding="utf-8")
sw_c = sw_c.replace("setu-pos-v84", "setu-pos-v85")
sw_path.write_text(sw_c, encoding="utf-8")

test_path = Path("hotel-erp/tests/test_horeca_one_ui.py")
test_c = test_path.read_text(encoding="utf-8")
test_c = test_c.replace('or "setu-pos-v84" in sw', 'or "setu-pos-v84" in sw or "setu-pos-v85" in sw')
test_path.write_text(test_c, encoding="utf-8")

print("Bumped sw.js to setu-pos-v85")
