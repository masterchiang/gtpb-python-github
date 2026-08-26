"""Find lines in i18n.py that have nested unescaped ASCII quotes (Python syntax errors)."""
import io

with io.open("gtpb/i18n.py", "r", encoding="utf-8") as f:
    text = f.read()

lines = text.split("\n")
problem_count = 0
for i, line in enumerate(lines, 1):
    # Count ASCII double-quote chars. A valid "key": "value" line has exactly 2.
    qc = line.count('"')
    if qc > 2 and line.lstrip().startswith('"'):
        problem_count += 1
        # Print first 200 chars
        snippet = line[:200].encode("ascii", "replace").decode("ascii")
        print(f"Line {i} (q={qc}): {snippet}")

print(f"\nTotal problematic lines: {problem_count}")
