"""
Small toolkit for recording polished product demos with Playwright.

What it adds on top of a plain browser recording:
  - a visible cursor with a click ripple (Playwright's own recording hides the mouse)
  - lower-third captions and full-screen title cards that fade in and out
  - smooth mouse movement, then H.264 encoding with ffmpeg (bundled via imageio-ffmpeg)

Usage:
    with Recorder("out/demo.mp4") as r:
        r.card("Title", "subtitle")
        r.page.goto("http://localhost:8501")
        r.caption("What the viewer should notice")
        r.click(r.page.get_by_role("button", name="Build schedule"))
"""
from __future__ import annotations

import shutil
import time
import subprocess
import tempfile
from pathlib import Path

import imageio_ffmpeg
from playwright.sync_api import sync_playwright

W, H = 1280, 720          # recorded at 720p, upscaled to 1080p when encoding (keeps app text large)

OVERLAY_JS = r"""
(() => {
  if (window.__kit) return;
  window.__kit = true;
  const css = `
    #__cursor{position:fixed;z-index:2147483646;width:26px;height:26px;pointer-events:none;
      left:-50px;top:-50px;transition:none;filter:drop-shadow(0 2px 4px rgba(0,0,0,.45))}
    .__ripple{position:fixed;z-index:2147483645;width:14px;height:14px;margin:-7px 0 0 -7px;border-radius:50%;
      border:3px solid #4da3ff;pointer-events:none;animation:__rip .55s ease-out forwards}
    @keyframes __rip{to{transform:scale(4.2);opacity:0}}
    #__cap{zoom:.667;position:fixed;z-index:2147483644;left:50%;bottom:54px;transform:translate(-50%,14px);
      max-width:1280px;padding:16px 30px;border-radius:14px;background:rgba(10,14,22,.88);
      color:#fff;font:600 30px/1.3 'Segoe UI',system-ui,sans-serif;text-align:center;
      border:1px solid rgba(255,255,255,.12);box-shadow:0 10px 40px rgba(0,0,0,.45);
      opacity:0;transition:opacity .45s ease,transform .45s ease;pointer-events:none}
    #__cap.on{opacity:1;transform:translate(-50%,0)}
    #__cap small{display:block;margin-top:6px;font-weight:400;font-size:21px;color:#a9b8d0}
    #__card{zoom:.667;position:fixed;z-index:2147483647;inset:0;display:flex;flex-direction:column;align-items:center;
      justify-content:center;text-align:center;color:#fff;
      background:radial-gradient(1200px 700px at 50% 35%,#16315c 0%,#0a1020 70%);
      font-family:'Segoe UI',system-ui,sans-serif;opacity:0;transition:opacity .6s ease;pointer-events:none}
    #__card.on{opacity:1}
    #__card h1{margin:0 0 18px;font-size:76px;font-weight:700;letter-spacing:-1px;line-height:1.1;max-width:1500px}
    #__card p{margin:0;font-size:34px;color:#b9c8e2;max-width:1300px;line-height:1.4}
    #__card .tag{margin-bottom:28px;padding:8px 20px;border-radius:99px;font-size:22px;letter-spacing:3px;
      text-transform:uppercase;color:#7fc0ff;border:1px solid rgba(127,192,255,.4)}
    #__card ul{list-style:none;margin:30px 0 0;padding:0;font-size:32px;color:#dbe6f7;text-align:left}
    #__card li{margin:12px 0}
    #__card li:before{content:"\\2713";color:#4ade80;font-weight:700;margin-right:16px}
  `;
  const st = document.createElement('style'); st.textContent = css;
  const mount = () => {
    document.head.appendChild(st);
    const c = document.createElement('div'); c.id='__cursor';
    c.innerHTML = '<svg viewBox="0 0 24 24" width="26" height="26"><path d="M3 2l7.5 19 2.7-7.6L21 10.7z" fill="#fff" stroke="#111" stroke-width="1.6" stroke-linejoin="round"/></svg>';
    const cap = document.createElement('div'); cap.id='__cap';
    const card = document.createElement('div'); card.id='__card';
    document.body.append(c, cap, card);
    window.addEventListener('mousemove', e => { c.style.left = e.clientX + 'px'; c.style.top = e.clientY + 'px'; }, true);
    window.addEventListener('mousedown', e => {
      const r = document.createElement('div'); r.className='__ripple';
      r.style.left = e.clientX+'px'; r.style.top = e.clientY+'px'; document.body.appendChild(r);
      setTimeout(()=>r.remove(), 700);
    }, true);
  };
  if (document.body) mount(); else document.addEventListener('DOMContentLoaded', mount);
  window.__cap = (html) => { const e=document.getElementById('__cap'); if(!e) return;
    if(!html){e.classList.remove('on');return;} e.innerHTML=html; e.classList.add('on'); };
  window.__card = (html) => { const e=document.getElementById('__card'); if(!e) return;
    if(!html){e.classList.remove('on');return;} e.innerHTML=html; e.classList.add('on'); };
})();
"""


class Recorder:
    def __init__(self, out_mp4: str, size=(W, H), slow_mo=0, caption_top=False):
        self.out = Path(out_mp4)
        self.size = size
        self.slow_mo = slow_mo
        self._tmp = Path(tempfile.mkdtemp(prefix="demo_rec_"))
        self._mx, self._my = size[0] // 2, size[1] // 2
        self._trim = 0.0
        self.caption_top = caption_top

    def __enter__(self):
        self._pw = sync_playwright().start()
        self.browser = self._pw.chromium.launch(args=["--force-device-scale-factor=1"])
        self.ctx = self.browser.new_context(
            viewport={"width": self.size[0], "height": self.size[1]},
            record_video_dir=str(self._tmp),
            record_video_size={"width": self.size[0], "height": self.size[1]},
            color_scheme="dark",
        )
        self.ctx.add_init_script(OVERLAY_JS)
        self._t0 = time.time()
        self.page = self.ctx.new_page()
        self.page.goto("about:blank")
        self.page.mouse.move(self._mx, self._my)
        return self

    # ---- narration helpers -------------------------------------------------
    def wait(self, seconds: float):
        self.page.wait_for_timeout(int(seconds * 1000))

    def ensure_overlay(self):
        self.page.evaluate(OVERLAY_JS)

    def caption(self, text: str, sub: str = "", hold: float = 3.0):
        html = text + (f"<small>{sub}</small>" if sub else "")
        self.ensure_overlay()
        if self.caption_top:  # keep the lower part of the screen free (e.g. for a response panel)
            self.page.evaluate("() => { const e = document.getElementById('__cap'); e.style.bottom = 'auto'; e.style.top = '8px'; }")
        self.page.evaluate("h => window.__cap(h)", html)
        self.wait(hold)

    def caption_off(self, pause: float = 0.5):
        self.page.evaluate("() => window.__cap('')")
        self.wait(pause)

    def card_show(self, title: str, subtitle: str = "", tag: str = "", bullets: list[str] | None = None):
        html = (f'<div class="tag">{tag}</div>' if tag else "") + f"<h1>{title}</h1>"
        if subtitle:
            html += f"<p>{subtitle}</p>"
        if bullets:
            html += "<ul>" + "".join(f"<li>{b}</li>" for b in bullets) + "</ul>"
        self.ensure_overlay()
        self.page.evaluate("h => window.__card(h)", html)

    def card_hide(self, pause: float = 0.8):
        self.page.evaluate("() => window.__card('')")
        self.wait(pause)

    def card(self, title: str, subtitle: str = "", tag: str = "", bullets: list[str] | None = None, hold: float = 3.5):
        self.card_show(title, subtitle, tag, bullets)
        self.wait(hold)
        self.card_hide()

    def shot(self, path: str):
        """Clean screenshot (no caption/card/cursor) for use as a thumbnail."""
        self.page.evaluate("() => { window.__cap(''); window.__card(''); const c = document.getElementById('__cursor'); if (c) c.style.display = 'none'; }")
        self.wait(0.7)
        Path(path).parent.mkdir(parents=True, exist_ok=True)
        self.page.screenshot(path=path, type="jpeg", quality=92)
        self.page.evaluate("() => { const c = document.getElementById('__cursor'); if (c) c.style.display = ''; }")

    def mark_start(self):
        """Everything recorded before this call (blank page, loading) is cut from the final video."""
        self._trim = max(time.time() - self._t0 - 0.2, 0.0)

    # ---- pointer -----------------------------------------------------------
    def move_to(self, x: float, y: float, steps: int = 28):
        # ease-in-out so the cursor glides instead of teleporting
        sx, sy = self._mx, self._my
        for i in range(1, steps + 1):
            t = i / steps
            e = t * t * (3 - 2 * t)
            self.page.mouse.move(sx + (x - sx) * e, sy + (y - sy) * e)
            self.page.wait_for_timeout(14)
        self._mx, self._my = x, y

    def _center(self, locator):
        locator.scroll_into_view_if_needed()
        box = locator.bounding_box()
        return box["x"] + box["width"] / 2, box["y"] + box["height"] / 2

    def click(self, locator, pause: float = 0.6):
        x, y = self._center(locator)
        self.move_to(x, y)
        self.wait(0.15)
        self.page.mouse.down()
        self.page.mouse.up()
        self.wait(pause)

    def type_into(self, locator, text: str, delay: int = 70, enter: bool = False):
        self.click(locator, pause=0.2)
        self.page.keyboard.press("Control+A")
        self.page.keyboard.type(text, delay=delay)
        if enter:
            self.page.keyboard.press("Enter")
        self.wait(0.5)

    # ---- finish ------------------------------------------------------------
    def __exit__(self, *exc):
        video = self.page.video
        self.ctx.close()
        raw = Path(video.path())  # only valid until Playwright is stopped
        self.browser.close()
        self._pw.stop()
        if exc[0] is None:
            self.out.parent.mkdir(parents=True, exist_ok=True)
            encode(raw, self.out, trim=self._trim)
        shutil.rmtree(self._tmp, ignore_errors=True)


def encode(src: Path, dst: Path, fade_s: float = 0.6, trim: float = 0.0):
    ffmpeg = imageio_ffmpeg.get_ffmpeg_exe()
    # probe duration so the fade-out lands at the end
    probe = subprocess.run([ffmpeg, "-i", str(src)], capture_output=True, text=True).stderr
    dur = 0.0
    for line in probe.splitlines():
        if "Duration:" in line:
            h, m, s = line.split("Duration:")[1].split(",")[0].strip().split(":")
            dur = int(h) * 3600 + int(m) * 60 + float(s) - trim
    vf = f"scale=1920:1080:flags=lanczos,fps=30,fade=t=in:st=0:d={fade_s},fade=t=out:st={max(dur - fade_s, 0):.2f}:d={fade_s},format=yuv420p"
    subprocess.run(
        [ffmpeg, "-y", "-ss", f"{trim:.2f}", "-i", str(src), "-vf", vf, "-c:v", "libx264", "-preset", "slow", "-crf", "18",
         "-movflags", "+faststart", "-an", str(dst)],
        check=True, capture_output=True,
    )
