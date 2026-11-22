"""Figures for the defense deck, drawn from the running service (no mock-ups):
  xray_*.png   — a real PDF page with the service's own X-ray boxes (GET /api/page/.../xray);
  shot_*.png   — headless-Chrome screenshots of the site.
    python docs/make_deck_assets.py OUT_DIR [BASE_URL]"""
import io
import json
import subprocess
import sys
import urllib.request

from PIL import Image, ImageDraw

OUT = sys.argv[1]
BASE = sys.argv[2] if len(sys.argv) > 2 else "http://127.0.0.1:8077"
COL = {"verified": (31, 143, 106), "needs_review": (224, 161, 27), "flagged": (192, 57, 43), "not_applicable": (138, 150, 168)}
MISS = (107, 91, 214)
CHROME = "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome"


def get(path):
    with urllib.request.urlopen(BASE + path, timeout=120) as r:
        return r.read()


def xray(domain, split, pid, page, name, crop=None, dpi=200, hide_ints=True):
    img = Image.open(io.BytesIO(get(f"/api/page/{domain}/{split}/{pid}/{page}.png?dpi={dpi}"))).convert("RGB")
    xr = json.loads(get(f"/api/page/{domain}/{split}/{pid}/{page}/xray"))
    k = img.width / xr["width"]
    over = Image.new("RGBA", img.size, (0, 0, 0, 0))
    d = ImageDraw.Draw(over)

    def box(b, color, dashed=False, fill=40):
        x0, y0, x1, y1 = [v * k for v in b]
        x0, y0, x1, y1 = x0 - 3, y0 - 3, x1 + 3, y1 + 3
        d.rectangle([x0, y0, x1, y1], fill=color + (fill,))
        if not dashed:
            d.rectangle([x0, y0, x1, y1], outline=color + (255,), width=4)
        else:
            step = 10
            for xx in range(int(x0), int(x1), step * 2):
                d.line([xx, y0, min(xx + step, x1), y0], fill=color + (255,), width=3)
                d.line([xx, y1, min(xx + step, x1), y1], fill=color + (255,), width=3)
            for yy in range(int(y0), int(y1), step * 2):
                d.line([x0, yy, x0, min(yy + step, y1)], fill=color + (255,), width=3)
                d.line([x1, yy, x1, min(yy + step, y1)], fill=color + (255,), width=3)
    cands = [c for c in xr["candidates"] if not hide_ints or any(ch in c["text"].strip("()[],;:*") for ch in ".,%")]
    for c in cands:
        box(c["box"], MISS, dashed=True, fill=18)
    for r in xr["records"]:
        if r.get("box"):
            box(r["box"], COL.get(r["status"], COL["not_applicable"]))
    img = Image.alpha_composite(img.convert("RGBA"), over).convert("RGB")
    if crop:
        W, H = img.size
        img = img.crop((int(crop[0] * W), int(crop[1] * H), int(crop[2] * W), int(crop[3] * H)))
    img.save(f"{OUT}/{name}.png")
    st = {s: sum(1 for r in xr["records"] if r["status"] == s and r.get("box")) for s in COL}
    print(name, xr["stats"], st, "candidates shown", len(cands))
    return xr["stats"]


def shot(path, name, w=1440, h=900):
    subprocess.run([CHROME, "--headless=new", "--disable-gpu", "--hide-scrollbars", f"--window-size={w},{h}", "--force-device-scale-factor=2",
                    "--virtual-time-budget=9000", f"--user-data-dir={OUT}/chrome_prof", f"--screenshot={OUT}/{name}.png", BASE + path],
                   capture_output=True, timeout=120)
    print(name, path)


if __name__ == "__main__":
    import os
    os.makedirs(OUT, exist_ok=True)
    jobs = json.loads(sys.argv[3]) if len(sys.argv) > 3 else {}
    for j in jobs.get("xray", []):
        xray(*j["args"], name=j["name"], crop=j.get("crop"))
    for j in jobs.get("shots", []):
        shot(j["path"], j["name"], j.get("w", 1440), j.get("h", 900))
