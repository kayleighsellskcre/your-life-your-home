"""Bundle the site stylesheets into one file, in the exact cascade order base.html used.

Run after editing any source stylesheet:  python scripts/build_css.py
Output: static/css/ylh.bundle.css  (the only CSS file base.html links to)
"""
import re
from pathlib import Path

CSS = Path(__file__).resolve().parent.parent / "static" / "css"
ORDER = [
    "design-system.css",
    "variable-bridge.css",
    "responsive-grid.css",
    "styles.css",
    "platform-enhancements.css",
    "compact-dainty.css",
    "form-enhancements.css",
    "ylh-luxury.css",
    "sage-revival.css",   # overrides ylh-luxury
    "brass-accent.css",   # loads last = highest priority
]

parts = []
for name in ORDER:
    text = (CSS / name).read_text(encoding="utf-8")
    text = re.sub(r"/\*.*?\*/", "", text, flags=re.S)       # drop comments
    text = re.sub(r"\n\s*\n+", "\n", text).strip()          # drop blank lines
    parts.append(f"/* {name} */\n{text}")

out = CSS / "ylh.bundle.css"
out.write_text("\n".join(parts) + "\n", encoding="utf-8")
print(f"Wrote {out.name}: {out.stat().st_size // 1024} KB from {len(ORDER)} files")
