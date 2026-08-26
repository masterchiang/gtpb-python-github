"""Fix Python syntax errors in i18n.py caused by inner ASCII double-quotes
in German / French / Spanish / Portuguese / Russian strings.

Strategy: for each line that starts with a `    "key":` pattern, escape any
ASCII `"` that appears inside the value (between the key's closing quote and
the line's last quote) by replacing it with `\"`.
"""
import io
import re

with io.open("gtpb/i18n.py", "r", encoding="utf-8") as f:
    text = f.read()

lines = text.split("\n")
fixed = 0
out = []
for i, line in enumerate(lines, 1):
    # Match a dict-entry line: leading whitespace, "key": "value",
    m = re.match(r'^(\s+)"([^"]+)":\s"(.*)"(,?)$', line)
    if not m:
        out.append(line)
        continue
    indent, key, value, comma = m.group(1), m.group(2), m.group(3), m.group(4)
    # If value contains any unescaped `"` (more than just escaped pairs at boundaries),
    # we need to escape inner ones. Heuristic: count unescaped `"` after backslash-stripping.
    # In our source strings, inner `"` always needs escaping.
    if '"' in value:
        # Escape any unescaped "
        # First, temporarily mark already-escaped sequences
        new_value = ""
        i = 0
        while i < len(value):
            ch = value[i]
            if ch == '\\' and i + 1 < len(value) and value[i+1] in ('"', '\\', 'n', 't', 'r'):
                new_value += value[i:i+2]
                i += 2
            elif ch == '"':
                new_value += '\\"'
                i += 1
            else:
                new_value += ch
                i += 1
        new_line = f'{indent}"{key}": "{new_value}"{comma}'
        out.append(new_line)
        fixed += 1
        print(f"Line {i}: {line[:100]!r} -> {new_line[:100]!r}")
    else:
        out.append(line)

with io.open("gtpb/i18n.py", "w", encoding="utf-8") as f:
    f.write("\n".join(out))

print(f"\nFixed {fixed} lines")

# Try to import the module now
import sys
sys.path.insert(0, ".")
if "gtpb.i18n" in sys.modules:
    del sys.modules["gtpb.i18n"]
try:
    import gtpb.i18n as i18n
    print("OK: import succeeded")
    print("Languages:", list(i18n.TRANSLATIONS.keys()))
    for code in i18n.TRANSLATIONS:
        d = i18n.TRANSLATIONS[code]
        print(f"  {code}: {len(d)} keys, btn_start={d.get('btn_start')!r}")
except SyntaxError as e:
    print(f"STILL BROKEN: {e}")
    # Show the broken lines
    with io.open("gtpb/i18n.py", "r", encoding="utf-8") as f:
        for j, l in enumerate(f.read().split("\n"), 1):
            if j == e.lineno:
                print(f"  {j}: {l!r}")
