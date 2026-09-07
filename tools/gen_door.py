#!/usr/bin/env python3
"""Generate the front door's two pictures: docs/assets/door.svg (the banner)
and docs/assets/tenseconds.svg (a real verdict, drawn).

The banner is mathematics -- a grid pulled toward a gravity well, an
event-horizon ring, one slow hotspot -- and carries no numbers, so it never
goes stale. The terminal shot is the actual output of the released CLI on a
deliberately broken package, colour added; regenerate both on release.

    python3 tools/gen_door.py
"""
import math
import pathlib
import re

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
<text x="470" y="292" font-family="{SANS}" font-size="15.5" fill="#c6d2dc" text-anchor="middle">Validate, lint, pack and serve iiRDS packages —</text>
<text x="470" y="313" font-family="{SANS}" font-size="15.5" fill="#c6d2dc" text-anchor="middle">offline, deterministic, and every finding tells you how to fix it.</text>
<text x="470" y="345" font-family="{MONO}" font-size="15" font-weight="700" fill="#e8edf2" text-anchor="middle">AI proposes. <tspan fill="#8fb8dd">Rules judge.</tspan> People decide.</text>
<text x="470" y="376" text-anchor="middle" font-family="{SANS}" font-size="12" fill="#93a1ad"><tspan font-family="{MONO}" font-size="10.5" font-weight="700" fill="#7da7cf">DE&#160;&#160;</tspan>Prüft iiRDS-Pakete offline<tspan font-family="{MONO}" font-size="10.5" font-weight="700" fill="#ddab74">&#160;&#160;&#160;&#160;&#160;KO&#160;&#160;</tspan>iiRDS 패키지 오프라인 검증</text>
</svg>'''

# ── the real verdict, drawn ──────────────────────────────────────────────────
#
# The text is the checker's own, captured from `report.render_text` on the
# package below. It used to be transcribed by hand into a table of coloured
# runs, and it drifted: the transcript said "175 rules checked, 24 not
# applicable" for five releases while the committed picture said what a run
# said, because two tests hold the picture to a real run and nothing at all
# held this file. The gate and the rule that a generated file has one author
# were pulling in opposite directions, and the gate won every time -- by
# putting the edit in the output.
#
# So the only sentences written here are the two commands, which are the
# invocation rather than the output. Everything below them is read.

#: The package the picture is of. It lives here because the picture is of it;
#: `tests/test_readme_front.py` imports it rather than keeping a second copy.
TERMSHOT_PACKAGE = {
    "mimetype": b"application/zip",
    "META-INF/metadata.rdf": (
        '<?xml version="1.0"?><rdf:RDF '
        'xmlns:rdf="http://www.w3.org/1999/02/22-rdf-syntax-ns#" '
        'xmlns:iirds="http://iirds.tekom.de/iirds#">'
        '<iirds:Topic rdf:about="urn:x:t1">'
        "<iirds:title>A topic</iirds:title></iirds:Topic></rdf:RDF>"),
    "content/topic1.xhtml": "<html/>",
}

#: Characters that fit across the picture at this font size. A run of the
#: checker prints two lines longer than this; they are cut at a word and
#: marked, and the caption says so, because a picture that quietly shortens
#: what it calls real output is telling a small lie about the tool.
COLUMNS = 118


def _verdict_lines():
    """What `iirds check` prints for TERMSHOT_PACKAGE, as plain text."""
    import io
    import sys
    import tempfile
    import zipfile

    sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent / "src"))
    from iirds_validate import report as report_module
    from iirds_validate import runner

    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as archive:
        info = zipfile.ZipInfo("mimetype")
        info.compress_type = zipfile.ZIP_STORED
        archive.writestr(info, TERMSHOT_PACKAGE["mimetype"])
        for name, body in TERMSHOT_PACKAGE.items():
            if name != "mimetype":
                archive.writestr(name, body)
    directory = pathlib.Path(tempfile.mkdtemp())
    package = directory / "broken.iirds"
    package.write_bytes(buf.getvalue())

    printed = io.StringIO()          # not a tty, so the renderer paints nothing
    report_module.render_text(runner.check(package), printed)
    out = []
    for line in printed.getvalue().splitlines():
        if len(line) > COLUMNS:
            cut = line.rfind(" ", 0, COLUMNS - 2)
            line = line[:cut] + " \u2026"
        out.append(line)
    return out


L = []
def ln(y, dy, runs):
    """Append one rendered line at baseline y; return the next baseline."""
    parts = "".join(f'<tspan x="{x}" fill="{c}"{w}>{t}</tspan>'
                    for x, c, t, w in runs)
    L.append(f'<text y="{y}" font-family="{MONO}" font-size="12.5" xml:space="preserve">{parts}</text>')
    return y + dy
B = " font-weight=\"700\""
G, D, E, A_, F, T, N = "#8fd0a8", "#7d8a99", "#e0604d", "#e8c268", "#5cb87f", "#d8dfe5", "#93a1ad"
ADVANCE = 7.0            # one monospace column at 12.5px, measured on the shipped picture
LEFT = 28


def _escape(text):
    return text.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


def _runs(line):
    """One printed line as coloured runs, painted by the shape the renderer
    gives it rather than by a table kept in step with it."""
    indent = len(line) - len(line.lstrip())
    x = LEFT + indent * ADVANCE
    body = line.strip()
    if not body:
        return []
    if body.startswith("\u2192 "):
        return [(x, F, _escape(body), "")]
    if body.startswith("note:"):
        return [(x, N, _escape(body), "")]
    error = re.match(r"^(ERROR|WARN|INFO)\s+(\S+)\s+(.*)$", body)
    if error:
        level, rule_id, message = error.groups()
        pad = len(error.group(0)) - len(level) - len(rule_id) - len(message)
        return [(x, E, level, B),
                (x + (len(level) + 1) * ADVANCE, A_, rule_id, B),
                (x + (len(level) + len(rule_id) + pad) * ADVANCE, T, _escape(message), "")]
    if body.startswith("FAIL") or body.startswith("PASS"):
        verdict, _, rest = body.partition(" ")
        return [(x, E if verdict == "FAIL" else F, verdict, B),
                (x + 8 * ADVANCE, T, _escape(rest.strip()), "")]
    if re.match(r"^\d+ rules checked", body):
        return [(x, N, _escape(body), "")]
    if indent >= 20:
        return [(x, D, _escape(body), "")]
    name, _, state = body.partition("   ")
    if state.strip():
        return [(x, T, _escape(name) + "   ", B),
                (x + (len(name) + 3) * ADVANCE, A_, _escape(state.strip()), "")]
    return [(x, T, _escape(body), "")]


def _draw():
    global L
    L = []
    y = 40
    # The two commands are the invocation, not the output: they are typed.
    y = ln(y, 21, [(LEFT, G, "$ ", B), (LEFT + 18, T, "pip install iirds", "")])
    y = ln(y, 30, [(LEFT, G, "$ ", B), (LEFT + 18, T, "iirds check broken.iirds", "")])
    for line in _verdict_lines():
        runs = _runs(line)
        if not runs:
            y += 10
            continue
        y = ln(y, 19, runs)
    height = y + 18
    return f'''<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 940 {height}" role="img" aria-label="Real output of iirds check on a broken package: two errors, each with evidence and a fix">
<rect x="1" y="1" width="938" height="{height-2}" rx="10" fill="#12161a" stroke="#252b30" stroke-width="1.5"/>
<circle cx="24" cy="19" r="5" fill="#e0604d"/><circle cx="42" cy="19" r="5" fill="#e8c268"/><circle cx="60" cy="19" r="5" fill="#5cb87f"/>
<text x="80" y="23" font-family="{MONO}" font-size="11" fill="#7d8a99">iirds check — the checker\u2019s own output, coloured; two long lines cut at a word</text>
{"".join(L)}
</svg>'''


shot = _draw()

#: What this file is the author of. `--check` regenerates into memory and
#: compares, which is the gate the front page's two pictures did not have: the
#: tests hold the *picture* to a real run, and holding the picture is what put
#: every edit into the output and left the generator behind. Byte-compared,
#: like every other generated artefact here.
WRITES = {"door.svg": banner, "tenseconds.svg": shot}


def main() -> int:
    import argparse

    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--check", action="store_true",
                    help="regenerate into memory and compare, writing nothing")
    args = ap.parse_args()

    if args.check:
        stale = []
        for name, body in sorted(WRITES.items()):
            path = OUT / name
            if not path.exists():
                stale.append("%s is missing" % name)
            elif path.read_text(encoding="utf-8") != body:
                stale.append("%s is not what this generator writes" % name)
        if stale:
            import sys
            for line in stale:
                print("  " + line, file=sys.stderr)
            print("\nrun: python3 tools/gen_door.py", file=sys.stderr)
            return 1
        print("docs/assets: %d picture(s) match their generator" % len(WRITES))
        return 0

    for name, body in sorted(WRITES.items()):
        (OUT / name).write_text(body, encoding="utf-8")
    print("door.svg %d KB · tenseconds.svg %d KB" % (len(banner) // 1024, len(shot) // 1024))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
