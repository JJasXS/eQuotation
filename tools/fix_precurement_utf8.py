from pathlib import Path

p = Path(__file__).resolve().parents[1] / "templates" / "precurement" / "precurement.html"
text = p.read_bytes().decode("utf-8-sig")
text = text.replace("\u2014", "-").replace("\ufffd", "-")
p.write_text(text, encoding="utf-8", newline="\r\n")
assert p.read_bytes()[:3] != b"\xef\xbb\xbf"
p.read_text(encoding="utf-8")
print("normalized", p.stat().st_size, "bytes")
