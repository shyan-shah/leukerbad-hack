#!/usr/bin/env python3
"""Renders film.html frame by frame (30 fps) into an MP4. Needs the local server on :8801, Playwright and ffmpeg."""
import subprocess, sys, time
from playwright.sync_api import sync_playwright
out = sys.argv[1]; FPS = 30
ff = subprocess.Popen(['ffmpeg', '-loglevel', 'error', '-y', '-f', 'image2pipe', '-framerate', str(FPS), '-c:v', 'mjpeg', '-i', '-', '-c:v', 'libx264', '-preset', 'slow', '-crf', '16', '-pix_fmt', 'yuv420p', '-movflags', '+faststart', out], stdin=subprocess.PIPE)
with sync_playwright() as p:
    b = p.chromium.launch(channel='chrome', headless=True, args=['--use-gl=angle', '--enable-unsafe-swiftshader'])
    pg = b.new_page(viewport={'width': 1920, 'height': 1080})
    pg.goto('http://localhost:8801/film.html?rec&hold'); pg.wait_for_function('window.filmReady===true', timeout=60000)
    n = int(pg.evaluate('film.DUR') * FPS); t0 = time.time()
    for i in range(n):
        if i: pg.evaluate('film.advance(1/30)')
        ff.stdin.write(pg.screenshot(type='jpeg', quality=96))
        if i % 150 == 0: print(i, n, round(time.time() - t0), flush=True)
    b.close()
ff.stdin.close(); ff.wait(); print('done', out, flush=True)
