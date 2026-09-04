#!/usr/bin/env python3
"""Generate the front door's two pictures: docs/assets/door.svg (the banner)
and docs/assets/tenseconds.svg (a real verdict, drawn).

The banner is mathematics -- a grid pulled toward a gravity well, an
event-horizon ring, one slow hotspot -- and carries no numbers, so it never
goes stale. The terminal shot is the actual output of the released CLI on a
deliberately broken package, colour added; regenerate both on release.

    python3 tools/gen_door.py
"""
import math, pathlib

OUT = pathlib.Path(__file__).resolve().parent.parent / "docs" / "assets"
MONO = "ui-monospace,SFMono-Regular,Menlo,Consolas,monospace"
SANS = ("-apple-system,'Segoe UI',Roboto,'Helvetica Neue',Arial,"
        "'Apple SD Gothic Neo','Malgun Gothic',sans-serif")

# ── the banner ──────────────────────────────────────────────────────────────
CX, CY, W, H = 470.0, 100.0, 940, 408
A, S, EXT = 0.55, 165.0, 182

def _warp(x, y):
    dx, dy = x - CX, y - CY
    r = math.hypot(dx, dy)
    g = 1.0 - A * math.exp(-(r / S) ** 2)
    return CX + dx * g, CY + dy * g

def _grid():
    parts = []
    for xi in range(-EXT, W + EXT + 1, 26):
        pts = [_warp(xi, yy) for yy in range(-EXT, H + 1, 10)]
        parts.append('M' + 'L'.join(f'{px:.1f},{py:.1f}' for px, py in pts))
    for yi in range(-EXT, H + 1, 26):
        pts = [_warp(xx, yi) for xx in range(-EXT, W + EXT + 1, 10)]
        parts.append('M' + 'L'.join(f'{px:.1f},{py:.1f}' for px, py in pts))
    return " ".join(parts)

def _smear():
    segs, N, SPAN, RR = [], 48, 94.0, 57
    C = 2 * math.pi * RR
    seg = C * (SPAN / 360.0) / N
    for i in range(N):
        t = (i + 0.5) / N
        op = 0.55 * (1 - abs(t - 0.5) * 2)
        off = -C * (SPAN / 360.0) * i / N
        segs.append(f'<circle cx="470" cy="100" r="{RR}" fill="none" stroke="#ffeede" '
                    f'stroke-opacity="{op:.3f}" stroke-width="18" '
                    f'stroke-dasharray="{seg:.2f} {C-seg:.2f}" stroke-dashoffset="{off:.2f}"/>')
    return "".join(segs)

banner = f'''<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 940 408" role="img" aria-label="iirds — validate, lint, pack and serve iiRDS packages, offline">
<defs>
<radialGradient id="halo" cx="50%" cy="50%" r="50%"><stop offset="0%" stop-color="#2f5d8a" stop-opacity=".30"/><stop offset="100%" stop-color="#2f5d8a" stop-opacity="0"/></radialGradient>
<filter id="soft"><feGaussianBlur stdDeviation="2.2"/></filter>
<filter id="softer"><feGaussianBlur stdDeviation="5"/></filter>
<filter id="smear" x="-40%" y="-40%" width="180%" height="180%"><feGaussianBlur stdDeviation="3"/></filter>
</defs>
<rect width="940" height="408" fill="#0b0f14"/>
<path d="{_grid()}" fill="none" stroke="rgba(198,212,224,0.075)" stroke-width="1"/>
<circle cx="470" cy="100" r="230" fill="url(#halo)"/>
<circle cx="470" cy="100" r="58" fill="none" stroke="#8fb8dd" stroke-opacity=".28" stroke-width="7" filter="url(#softer)"/>
<circle cx="470" cy="100" r="51" fill="#03050a"/>
<circle cx="470" cy="100" r="57" fill="none" stroke="#ffeede" stroke-opacity=".45" stroke-width="2" filter="url(#soft)"/>
<g filter="url(#smear)">{_smear()}
<animateTransform attributeName="transform" type="rotate" from="0 470 100" to="360 470 100" dur="16s" repeatCount="indefinite"/></g>
<text x="470" y="206" font-family="{MONO}" font-size="12.5" letter-spacing="3.4" fill="#93a1ad" text-anchor="middle">STANDARDS, JUDGED OFFLINE</text>
<text x="470" y="262" font-family="{MONO}" font-size="52" font-weight="700" fill="#e8edf2" text-anchor="middle">iirds<tspan fill="#8fb8dd">.</tspan></text>
<text x="470" y="298" font-family="{SANS}" font-size="15.5" fill="#c6d2dc" text-anchor="middle">Validate, lint, pack and serve iiRDS packages — offline, deterministic, and every finding tells you how to fix it.</text>
<text x="470" y="330" font-family="{MONO}" font-size="15" font-weight="700" fill="#e8edf2" text-anchor="middle">AI proposes. <tspan fill="#8fb8dd">Rules judge.</tspan> People decide.</text>
<rect x="308" y="352" width="26" height="15" rx="3" fill="#7da7cf"/><text x="321" y="363" font-family="{MONO}" font-size="9.5" font-weight="700" fill="#10151a" text-anchor="middle">DE</text>
<text x="342" y="363.5" font-family="{SANS}" font-size="12" fill="#93a1ad">Prüft iiRDS-Pakete offline</text>
<rect x="516" y="352" width="26" height="15" rx="3" fill="#ddab74"/><text x="529" y="363" font-family="{MONO}" font-size="9.5" font-weight="700" fill="#10151a" text-anchor="middle">KO</text>
<text x="550" y="363.5" font-family="{SANS}" font-size="12" fill="#93a1ad">iiRDS 패키지 오프라인 검증</text>
</svg>'''
(OUT / "door.svg").write_text(banner, encoding="utf-8")

# ── the real verdict, drawn (captured from the released CLI on a broken zip) ─
L = []
def ln(y, runs):
    parts = "".join(f'<tspan x="{x}" fill="{c}"{w}>{t}</tspan>'
                    for x, c, t, w in runs)
    L.append(f'<text y="{y}" font-family="{MONO}" font-size="12.5" xml:space="preserve">{parts}</text>')
B = " font-weight=\"700\""
G, D, E, A_, F, T, N = "#8fd0a8", "#7d8a99", "#e0604d", "#e8c268", "#5cb87f", "#d8dfe5", "#93a1ad"
y = 40
ln(y, [(28, G, "$ ", B), (46, T, "pip install iirds", "")]); y += 21
ln(y, [(28, G, "$ ", B), (46, T, "iirds check broken.iirds", "")]); y += 30
ln(y, [(28, T, "broken.iirds   ", B), (140, A_, "iiRDS not declared", "")]); y += 20
ln(y, [(40, N, "note: no iirds:iiRDSVersion in the package; validated against 1.3.", "")]); y += 17
ln(y, [(40, N, "note: metadata read from META-INF/metadata.rdf", "")]); y += 27
ln(y, [(40, E, "ERROR ", B), (90, A_, "C5", B), (140, T, "mimetype must contain exactly 'application/iirds+zip' with no line ending", "")]); y += 19
ln(y, [(168, D, "mimetype", "")]); y += 17
ln(y, [(168, D, "b'application/zip'", "")]); y += 19
ln(y, [(154, F, "→ Make the file contain exactly application/iirds+zip, ASCII, with no", "")]); y += 17
ln(y, [(154, F, "→ trailing newline and no byte order mark. Editors add both silently, so", "")]); y += 17
ln(y, [(154, F, "→ write it with a tool that does not.", "")]); y += 24
ln(y, [(40, E, "ERROR ", B), (90, A_, "M3", B), (140, T, "metadata declares no iirds:Package for this container", "")]); y += 19
ln(y, [(154, F, "→ Provide exactly one iirds:Package instance describing this container. It", "")]); y += 17
ln(y, [(154, F, "→ is the root a consumer starts from, so zero leaves the package", "")]); y += 17
ln(y, [(154, F, "→ unidentified and two leave it ambiguous.", "")]); y += 27
ln(y, [(28, E, "FAIL", B), (90, T, "2 error(s), 0 warning(s), 0 informational", "")]); y += 19
ln(y, [(28, N, "164 rules checked, 21 not applicable to this version/variant", "")]); y += 14
TH = y + 18
shot = f'''<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 940 {TH}" role="img" aria-label="Real output of iirds check on a broken package: two errors, each with evidence and a fix">
<rect x="1" y="1" width="938" height="{TH-2}" rx="10" fill="#12161a" stroke="#252b30" stroke-width="1.5"/>
<circle cx="24" cy="19" r="5" fill="#e0604d"/><circle cx="42" cy="19" r="5" fill="#e8c268"/><circle cx="60" cy="19" r="5" fill="#5cb87f"/>
<text x="80" y="23" font-family="{MONO}" font-size="11" fill="#7d8a99">iirds check — real output, colour added</text>
{"".join(L)}
</svg>'''
(OUT / "tenseconds.svg").write_text(shot, encoding="utf-8")
print("door.svg", len(banner)//1024, "KB · tenseconds.svg", len(shot)//1024, "KB")
