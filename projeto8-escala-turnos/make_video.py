"""
Records the product demo video of the shift scheduler (needs: pip install playwright imageio-ffmpeg, then
`playwright install chromium`).   python make_video.py [output.mp4]

It starts the real Streamlit app, drives it like a user, and encodes ~1.5 minutes of 1080p video.
"""
import subprocess
import sys
import time
import urllib.request
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent / "tools" / "video"))
from videokit import Recorder  # noqa: E402

PORT = 8611
URL = f"http://localhost:{PORT}"
OUT = sys.argv[1] if len(sys.argv) > 1 else str(HERE / "video" / "shift-scheduler-demo.mp4")


def start_server():
    proc = subprocess.Popen(
        [sys.executable, "-m", "streamlit", "run", "app.py", "--server.port", str(PORT), "--server.headless", "true",
         "--browser.gatherUsageStats", "false", "--theme.base", "dark", "--theme.primaryColor", "#4da3ff"],
        cwd=HERE, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
    )
    for _ in range(60):
        try:
            urllib.request.urlopen(URL, timeout=1)
            return proc
        except Exception:
            time.sleep(0.5)
    proc.kill()
    raise SystemExit("Streamlit did not start")


def build(r):
    r.click(r.page.get_by_role("button", name="Build schedule"), pause=0.3)
    r.wait(2.2)  # solver + rerender


def main():
    server = start_server()
    try:
        with Recorder(OUT) as r:
            p = r.page
            p.goto(URL)  # loads behind the title card, so the viewer never sees a loading screen
            r.card_show("Weekly Shift Scheduler", "A fair rota in seconds - or a clear reason why it can't be done",
                        tag="Python · OR-Tools · Streamlit")
            r.wait(0.8)
            r.mark_start()
            p.get_by_text("Optimal").wait_for(timeout=30000)
            r.wait(3.5)
            r.card_hide()
            r.shot(str(HERE / "imagens" / "escala-video.jpg"))
            r.wait(1.5)
            r.caption("8 people. 7 days. 38 shifts to cover.",
                      "Everyone's limits and preferences go in; a finished schedule comes out.", hold=4)
            r.caption("Hard rules are never broken",
                      "exact headcount · availability · one shift a day · no evening-then-morning · weekly max", hold=5)
            r.caption_off()

            # the grid
            grid = p.get_by_text("Schedule", exact=True).first
            grid.scroll_into_view_if_needed()
            r.move_to(800, 380)
            r.caption("Then it balances the work fairly",
                      "Minimizes missed day-off requests, then evens out who works the most.", hold=4.5)
            r.caption_off()
            p.mouse.wheel(0, 700)
            r.wait(1.0)
            r.caption("Shifts per person at a glance", hold=3.5)
            r.caption_off()
            p.mouse.wheel(0, -2000)
            r.wait(0.8)

            # an impossible request
            r.card("What if you ask for the impossible?", tag="Stress test", hold=2.8)
            wk_morning = p.get_by_label("Weekday Morning")
            r.type_into(wk_morning, "6", enter=True)
            r.caption("Weekday mornings now need 6 people", "The team can't cover that.", hold=2.5)
            build(r)
            p.get_by_text("No valid schedule").wait_for(timeout=15000)
            r.caption("It doesn't crash or guess - it tells you why",
                      "58 shifts needed, but this team can only work 39 in total.", hold=6)
            r.caption_off()

            # back to reality, then a real-life change
            r.type_into(wk_morning, "2", enter=True)
            r.card("Real life: a team member's plans change", tag="Update the plan", hold=2.8)
            p.get_by_text("Ana", exact=True).first.scroll_into_view_if_needed()
            r.click(p.get_by_text("Ana", exact=True).first)
            cannot = p.get_by_role("combobox", name="Cannot work").first
            r.click(cannot)
            for label in ("Mon Morning", "Tue Morning"):
                p.keyboard.type(label, delay=60)
                p.keyboard.press("Enter")
                r.wait(0.5)
            p.keyboard.press("Escape")
            r.caption("Ana can't work Monday or Tuesday morning", hold=2.5)
            r.caption_off(0.2)
            build(r)
            r.wait(0.6)
            p.mouse.wheel(0, 0)
            r.caption("New schedule in under a second",
                      "Ana is off those mornings; the solver re-balanced everyone else automatically.", hold=5)
            r.caption_off()

            # export
            dl = p.get_by_role("button", name="Download schedule (CSV)")
            r.click(dl, pause=1.2)
            r.caption("One click exports it to CSV", hold=3)
            r.caption_off()

            r.card("Built to be trusted", tag="13 automated tests",
                   bullets=["Every rule verified against the solver's real output",
                            "Impossible requests produce an explanation, not an error",
                            "Rules, team and coverage are easy to change for your business"],
                   hold=6)
    finally:
        server.kill()
    print("saved", OUT)


if __name__ == "__main__":
    main()
