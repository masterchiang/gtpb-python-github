import io, sys
sys.path.insert(0, ".")
text = io.open("gtpb/i18n.py", "r", encoding="utf-8").read()
try:
    import gtpb.i18n as i18n
    print("OK")
    print("Languages:", list(i18n.TRANSLATIONS.keys()))
    for code in i18n.TRANSLATIONS:
        d = i18n.TRANSLATIONS[code]
        print(f"  {code}: {len(d)} keys, btn_start={d.get('btn_start')!r}")
except SyntaxError as e:
    print("SyntaxError at line", e.lineno, ":", e.msg)
    lines = text.split("\n")
    print("Line content:")
    print(repr(lines[e.lineno - 1]))
    print()
    print("Context:")
    for j in range(max(0, e.lineno - 3), min(len(lines), e.lineno + 2)):
        print(f"  {j+1}: {lines[j]!r}")
