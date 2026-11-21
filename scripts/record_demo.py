"""Records a demo video of the chat widget using the installed Google Chrome.

Run:  uv run --with playwright python scripts/record_demo.py
Output: ~/Documents/SideHustle/fiverr-gig-chatbot/demo-video.webm
"""
import shutil
import time
from pathlib import Path

from playwright.sync_api import sync_playwright

OUT = Path.home() / "Documents/SideHustle/fiverr-gig-chatbot"
QUESTIONS = [
    "Hi! Are you open on Saturday?",
    "How much is a cleaning? Do you take Delta Dental?",
    "How much does a crown cost?",
    "Great, I'd like to book a cleaning. I'm Priya, 555-0177, Saturday morning please.",
]


def type_slowly(page, selector, text):
    for ch in text:
        page.type(selector, ch, delay=35)


with sync_playwright() as p:
    browser = p.chromium.launch(channel="chrome", headless=True)
    ctx = browser.new_context(viewport={"width": 1280, "height": 720},
                              record_video_dir=str(OUT / "_rec"), record_video_size={"width": 1280, "height": 720})
    page = ctx.new_page()
    page.goto("http://localhost:8000/")
    page.wait_for_selector(".as-btn")
    time.sleep(2)
    page.click(".as-btn")
    time.sleep(1.5)
    for q in QUESTIONS:
        before = page.locator(".as-bot").count()
        type_slowly(page, ".as-in input", q)
        time.sleep(0.4)
        page.keyboard.press("Enter")
        # wait until the "…" placeholder is replaced by the real reply
        page.wait_for_function(
            "n => { const b=[...document.querySelectorAll('.as-bot')]; return b.length>n && b[b.length-1].textContent!=='…'; }",
            arg=before, timeout=120000)
        time.sleep(3.5)  # let viewers read the answer
    time.sleep(2)
    video_path = page.video.path()
    ctx.close()
    browser.close()

final = OUT / "demo-video.webm"
shutil.move(video_path, final)
shutil.rmtree(OUT / "_rec", ignore_errors=True)
print(final)
