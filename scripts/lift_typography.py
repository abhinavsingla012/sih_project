"""One-off: lift the type ramp and swap font stacks in App.css / government-theme.css (design_guidelines.json remap table)."""
import re, json, pathlib
root = pathlib.Path('/app/frontend/src')
remap = {int(k): v for k, v in json.load(open('/app/design_guidelines.json'))['px_remap_table'].items()}
FONT_IMPORT = "@import url('https://fonts.googleapis.com/css2?family=Plus+Jakarta+Sans:wght@400;500;600;700;800&family=Noto+Sans+Devanagari:wght@400;500;600;700&family=JetBrains+Mono:wght@400;500;600&display=swap');"
VARS = "--font-body:'Plus Jakarta Sans','Noto Sans Devanagari',sans-serif;--font-heading:'Plus Jakarta Sans','Noto Sans Devanagari',sans-serif;--font-mono:'JetBrains Mono','Courier New',monospace;--font-devanagari:'Noto Sans Devanagari','Plus Jakarta Sans',sans-serif;"

def size(m):
    n = int(m.group(2)); return f"font-size:{m.group(1)}{remap.get(n, n)}px"

def remap_sizes(css):
    return re.sub(r"font-size:(\s?)(\d+)px", size, css)

app = (root / 'App.css').read_text()
lines = app.split('\n')
assert lines[0].startswith('@import'); lines[0] = FONT_IMPORT
app = '\n'.join(lines)
app = app.replace(':root{', ':root{' + VARS, 1)
app = app.replace("font-family:'DM Sans',sans-serif", 'font-family:var(--font-body)')
app = app.replace("font-family:'Manrope',sans-serif", 'font-family:var(--font-heading)').replace('font-family:Manrope,sans-serif', 'font-family:var(--font-heading)')
app = app.replace("font-family:'IBM Plex Mono',monospace", 'font-family:var(--font-mono)')
app = app.replace('font-size:14px}button,input,select,textarea{font:inherit}', 'font-size:16px;line-height:1.5}button,input,select,textarea{font:inherit}', 1)
app = remap_sizes(app)
(root / 'App.css').write_text(app)

theme = (root / 'government-theme.css').read_text()
theme = theme.replace("font-family: Arial, 'Nirmala UI', sans-serif", 'font-family: var(--font-body)')
theme = remap_sizes(theme)
(root / 'government-theme.css').write_text(theme)
from collections import Counter
print('App.css sizes:', sorted(Counter(re.findall(r'font-size:\s?(\d+)px', app)).items(), key=lambda x: int(x[0])))
print('theme sizes:', sorted(Counter(re.findall(r'font-size:\s?(\d+)px', theme)).items(), key=lambda x: int(x[0])))
