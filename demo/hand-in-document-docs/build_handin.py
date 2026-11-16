# Builds demo/hand-in-document-docs/hand-in-document.html from the README (and the 16 Nov LOG entry for Row/Strength).
import os
# PDF: Chrome --headless=new --no-pdf-header-footer --virtual-time-budget=8000 --print-to-pdf=hand-in-document.pdf file://.../hand-in-document.html
OUT = os.path.expanduser('~/leukerbad-hack/demo/hand-in-document-docs/hand-in-document.html')

def table(head, rows, cls=''):
    h = ''.join(f'<th>{c}</th>' for c in head)
    b = ''.join('<tr>' + ''.join(f'<td>{c}</td>' for c in r) + '</tr>' for r in rows)
    return f'<table class="{cls}"><thead><tr>{h}</tr></thead><tbody>{b}</tbody></table>'

def page(n, eyebrow, title, body, cls=''):
    return f'''<section class="pg {cls}"><header><p class="eb">{eyebrow}</p><h2>{title}</h2></header><div class="body">{body}</div>
<footer><span>Vita · Leukerbad Robot Carnival 2026 · Track 4</span><span>{n}</span></footer></section>'''

# ---------- chart: target vs measured force (Push, real arm) ----------
def force_chart():
    data = [('1 Light', 10, 10.9, 1.7, '4 of 4'), ('2 Medium', 15, 19.1, 1.7, '10 of 10'),
            ('3 Firm', 20, 25.0, 2.3, '10 of 10'), ('4 Strong', 28, 31.2, 3.4, '10 of 10')]
    W, L, R, T, rowh = 620, 92, 40, 34, 58
    H = T + rowh * len(data) + 34
    x = lambda v: L + v / 40 * (W - L - R)
    g = []
    for v in range(0, 41, 10):
        g.append(f'<line x1="{x(v)}" x2="{x(v)}" y1="{T-8}" y2="{H-30}" stroke="#E3EAEB"/>'
                 f'<text x="{x(v)}" y="{H-12}" class="ax" text-anchor="middle">{v} N</text>')
    for i, (lab, tgt, m, sd, reps) in enumerate(data):
        y = T + rowh * i + rowh / 2
        g.append(f'<text x="0" y="{y+5}" class="lb">{lab}</text>')
        g.append(f'<line x1="{x(m-sd)}" x2="{x(m+sd)}" y1="{y}" y2="{y}" stroke="#1F7F95" stroke-width="2" stroke-linecap="round" opacity=".55"/>')
        g.append(f'<line x1="{x(tgt)}" x2="{x(tgt)}" y1="{y-12}" y2="{y+12}" stroke="#7D8A8D" stroke-width="3" stroke-linecap="round"/>')
        g.append(f'<circle cx="{x(m)}" cy="{y}" r="7" fill="#1F7F95" stroke="#fff" stroke-width="2"/>')
        g.append(f'<text x="{x(m+sd)+10}" y="{y+5}" class="vl">{m:.1f} N</text>')
    leg = (f'<g transform="translate({L} 8)"><line x1="0" x2="0" y1="-6" y2="8" stroke="#7D8A8D" stroke-width="3" stroke-linecap="round"/>'
           f'<text x="10" y="6" class="ax">Target</text><circle cx="86" cy="1" r="6" fill="#1F7F95"/><line x1="100" x2="124" y1="1" y2="1" stroke="#1F7F95" stroke-width="2" opacity=".55"/>'
           f'<text x="132" y="6" class="ax">Measured mean ± 1 sd, pushing out</text></g>')
    return f'<svg class="chart" viewBox="0 0 {W} {H}" role="img" aria-label="Target versus measured force for Push at four levels">{leg}{"".join(g)}</svg>'

# ---------- architecture diagram ----------
def arch():
    def box(x, y, w, h, title, lines, kind=''):
        t = ''.join(f'<tspan x="{x+16}" dy="18">{l}</tspan>' for l in lines)
        return (f'<g class="bx {kind}"><rect x="{x}" y="{y}" width="{w}" height="{h}" rx="12"/>'
                f'<text x="{x+16}" y="{y+28}" class="bt">{title}</text><text x="{x+16}" y="{y+34}" class="bl">{t}</text></g>')
    arr = lambda x1, y1, x2, y2, lab='': (f'<line x1="{x1}" y1="{y1}" x2="{x2}" y2="{y2}" class="ar" marker-end="url(#ah)"/>'
                                          + (f'<text x="{(x1+x2)/2}" y="{min(y1,y2)-8}" class="al" text-anchor="middle">{lab}</text>' if lab else ''))
    s = ['<defs><marker id="ah" viewBox="0 0 10 10" refX="9" refY="5" markerWidth="7" markerHeight="7" orient="auto"><path d="M0 0L10 5L0 10z" fill="#0A4552"/></marker></defs>']
    s.append('<rect x="200" y="6" width="702" height="350" rx="18" class="zone"/><text x="220" y="32" class="zl">STATION LAPTOP · one process, works offline</text>')
    s.append(box(0, 70, 170, 96, 'Patient phone', ['Vita app', 'NFC tap to start'], 'ph'))
    s.append(box(226, 52, 210, 130, 'server/', ['FastAPI', 'REST + WebSocket 30 Hz', 'SQLite, exports,', 'session note']))
    s.append(box(466, 52, 200, 130, 'software/', ['Engines: Push (Band),', 'Row, Strength', '100 Hz control loop']))
    s.append(box(696, 52, 190, 130, 'robot/arm.py', ['The ONLY code that', 'touches the robot:', 'clamps, trips, watchdog'], 'safe'))
    s.append(box(226, 222, 210, 116, 'server/screens', ['Patient big screen', 'Physio dashboard', 'Operator console']))
    s.append(box(940, 52, 190, 130, 'Flexiv Rizon 4', ['7 torque-sensing joints', '1 kHz Cartesian', 'impedance'], 'rb'))
    s.append(arr(170, 118, 222, 118)); s.append('<text x="85" y="190" class="al" text-anchor="middle">HTTP + live feed</text>')
    s.append(arr(331, 222, 331, 186))
    s.append(arr(436, 117, 462, 117))
    s.append(arr(666, 117, 692, 117))
    s.append(arr(886, 117, 936, 117))
    s.append('<text x="1035" y="208" class="al" text-anchor="middle">Flexiv RDK 1.7</text><text x="1035" y="224" class="al" text-anchor="middle">over Ethernet</text>')
    return f'<svg class="arch" viewBox="0 0 1136 360">{"".join(s)}</svg>'

# ---------- elastic band diagram ----------
def band():
    return '''<svg class="band" viewBox="0 0 520 210" aria-hidden="true">
<line x1="40" y1="110" x2="480" y2="110" stroke="#C9D5D7" stroke-width="2" stroke-dasharray="5 6"/>
<rect x="40" y="86" width="440" height="48" rx="24" fill="none" stroke="#58C4D4" stroke-width="1.5" opacity=".6"/>
<text x="260" y="76" text-anchor="middle" class="dl">soft walls keep the hand on a straight 30 cm line</text>
<line x1="40" y1="150" x2="40" y2="166" stroke="#7D8A8D"/><line x1="480" y1="150" x2="480" y2="166" stroke="#7D8A8D"/>
<line x1="40" y1="158" x2="480" y2="158" stroke="#7D8A8D"/><text x="260" y="182" text-anchor="middle" class="dl">30 cm push · rep counted out past 20 cm, back within 5 cm</text>
<circle cx="150" cy="110" r="8" fill="#0A4552"/><text x="150" y="146" text-anchor="middle" class="dl">anchor</text>
<path d="M158 110 l12 -12 l14 24 l14 -24 l14 24 l14 -24 l14 24 l14 -24 l12 12" fill="none" stroke="#1F7F95" stroke-width="3" stroke-linejoin="round"/>
<circle cx="300" cy="110" r="15" fill="#F1C36A"/><text x="300" y="115" text-anchor="middle" class="hd">hand</text>
<path d="M326 110h70" stroke="#0A4552" stroke-width="3" marker-end="url(#bh)"/>
<defs><marker id="bh" viewBox="0 0 10 10" refX="8" refY="5" markerWidth="6" markerHeight="6" orient="auto"><path d="M0 0L10 5L0 10z" fill="#0A4552"/></marker></defs>
<text x="404" y="104" class="dl">push</text>
<text x="225" y="40" text-anchor="middle" class="dl b">anchor moves with the hand, a fixed distance behind it</text>
</svg>'''

yes = '<span class="ok">✓</span>'
pages = []

# 1 cover
pages.append('''<section class="pg cover">
<img src="vita-logo.png" class="logo" alt="vita">
<h1>A standard robot arm,<br>turned into a rehab station.</h1>
<p class="sub">Software that turns an off-the-shelf, force-sensing robot arm (a Flexiv Rizon 4) into a station for arm rehabilitation. The arm acts as an elastic band whose strength the patient picks on their phone. It counts every repetition and measures how far and how hard the patient pushes. A physiotherapist sees every repetition remotely.</p>
<div class="meta">
<div><span>Event</span>Leukerbad Robot Carnival hackathon<br>14 to 16 November 2026</div>
<div><span>Track</span>4 · Elderly Care and Rehabilitation</div>
<div><span>Team</span>Shyan Shah, Shiv, Kian,<br>Mat (Matvey), Gio van Belle</div>
<div><span>Links</span>vitarehab.org<br>app.vitarehab.org <em>(hosted demo, simulated)</em></div>
</div>
<p class="pill">Research prototype, team-tested only. Not a medical device.</p>
</section>''')

# 2 overview + what runs today
stats = '''<div class="stats"><div><b>48 h</b><span>to build</span></div><div><b>5</b><span>people, each running several Claude Code agents</span></div>
<div><b>~900</b><span>automated tests (~10,000 lines)</span></div><div><b>150+</b><span>commits on one main branch</span></div></div>'''
runs = table(['', 'On the real arm', 'In simulation'], [
    ['<b>Push</b> at 4 resistance levels (Light, Medium, Firm, Strong)', f'{yes} 10/10 reps counted at each level, smooth return', yes],
    ['<b>Row</b> (pull towards you) at 4 levels', f'{yes} Real-arm checks passed 16 Nov: empty handle at levels 1 and 4, by hand at level 2 (2 of 2 reps)', f'{yes} 57 dedicated tests + soak'],
    ['<b>Strength test</b> (3 timed pushes against a held arm)', f'{yes} Real-arm checks passed 16 Nov: untouched and by hand, no trip, no fault', yes],
    ['Tap-to-start with an NFC tag on the station', yes, yes],
    ['Live rep counter, force bar and 3D twin on the phone', yes, yes],
    ['Physio dashboard, session note, exports', yes, yes]], 'runs')
pages.append(page(2, 'Overview', 'What runs today', stats + runs))

# 3 architecture
pages.append(page(3, 'Architecture', 'One laptop, one server, one safety layer', arch() + '''<div class="three">
<div><h3>One process on the station laptop</h3><p>The phone, the big screen and the physio dashboard all talk to the same local server. Nothing needs the internet, so a venue Wi-Fi failure cannot stop a session.</p></div>
<div><h3>The robot does the fast loop</h3><p>The Rizon runs its own 1 kHz Cartesian impedance controller. Our 100 Hz loop only decides where the spring is anchored and how stiff it is. Python never closes a force loop.</p></div>
<div><h3>One interface, real or simulated</h3><p><code>robot/arm.py</code> (real) and <code>software/sim_arm.py</code> (simulated, with friction, sensor offset, drift, noise and stiffness latency) expose the same methods, so everything was built and tested before the arm was connected.</p></div></div>'''))

# 4 elastic band
pages.append(page(4, 'How it works', 'The “elastic band”', '<div class="split"><div>' + band() + '''<p class="cap">The patient holds the end of the arm and pushes along a straight 30 cm line.</p></div>
<ol class="steps">
<li><b>The arm behaves as a spring.</b> Stiff across the line (soft walls keep the hand on track) and, along the line, a stiffness chosen so the patient feels the level’s force.</li>
<li><b>The anchor sits a fixed distance behind the hand,</b> so the resistance stays near constant through the push instead of growing with distance.</li>
<li><b>Stiffness is set once per set</b> (ramped over 0.5 s on a level change). Only the anchor moves. This is what made it smooth on the real arm.</li>
<li><b>Reps are counted from position alone,</b> with hysteresis: out past 20 cm, counted when back within 5 cm. No guessing whether a hand is present.</li>
<li><b>At the end of a set,</b> a “hands off” countdown, then one continuous move back to the start at 5 cm/s.</li></ol></div>'''))

# 5 measured push
mtab = table(['Level', 'Target', 'Reps counted', 'Mean force out', 'Spread (sd)'], [
    ['1 Light', '10 N', '4 of 4', '10.9 N', '1.7 N'], ['2 Medium', '15 N', '10 of 10', '19.1 N', '1.7 N'],
    ['3 Firm', '20 N', '10 of 10', '25.0 N', '2.3 N'], ['4 Strong', '28 N', '10 of 10', '31.2 N', '3.4 N']], 'num')
pages.append(page(5, 'Measured on the real arm · Push, 15 November', 'Every rep counted, at every level', f'''<div class="split w">
<div>{force_chart()}{mtab}</div>
<div class="facts">
<div><b>0.045–0.050 m/s</b><span>return to start, <strong>zero stops</strong> in five runs</span></div>
<div><b>0.3 mm</b><span>straight-line tracking along the 30 cm line; back to start within 0.09 mm</span></div>
<div><b>0.04 N</b><span>empty-handle reading after zeroing</span></div>
<div><b>50–54 N for 8 s</b><span>staged test of a raised force profile; reached 62 N twice, no arm fault, highest joint load 46% of its limit</span></div>
<p class="note">Readings above target grow with hand speed (the arm’s own damping, about 50 to 143 N per m/s by level), which is why the demo uses slow, steady pushes.</p>
</div></div>'''))

# 6 row + strength
rtab = table(['Row, empty handle', 'Level 1', 'Level 4'], [
    ['Move out, 28.0 cm', '6.9 s, 0.044–0.050 m/s, no stops', '6.9 s, 0.045–0.050 m/s, no stops'],
    ['Return, 28.0 cm', '6.9 s, 0.045–0.049 m/s, no stops', '6.9 s, 0.045–0.050 m/s, no stops'],
    ['Band on 10 s, nobody near', 'mean 0.26 N, 0.5 mm, 0 reps', 'mean 0.30 N, 0.6 mm, 0 reps']])
pages.append(page(6, 'Measured on the real arm · Row and Strength, 16 November', 'Row and the strength test pass their real-arm checks', f'''<div class="split">
<div>{rtab}<p class="cap">No phantom reps with nobody touching the handle, and smooth moves at both levels.</p></div>
<div class="facts">
<div><b>2 of 2</b><span>Row reps counted by hand at level 2. Pulling force mean 18.7 N (sd 4.8), top speed 0.13 m/s, no trip. Levels 1, 3 and 4 not yet done by hand.</span></div>
<div><b>1.61 N</b><span>Strength test peak, untouched, over three tries; handle moved 0.4 mm, no trip</span></div>
<div><b>30.0 N</b><span>Strength test peak by hand; above about 27 N it eases off by design (600 N/m × 4.5 cm). Every release under 0.15 m/s, no trip, no fault.</span></div>
</div></div>'''))

# 7 safety
saf = table(['Layer', 'Value'], [
    ['Spring pull bound', 'Stiffness clamp 600 N/m × anchor clamp 5 cm = <b>30 N</b> maximum commanded pull'],
    ['Commanded speed', '0.15 m/s, acceleration 0.5 m/s², passed on every command'],
    ['Trips to a soft hold', 'Hand speed over 0.40 m/s, force over 40 N, hand 2 cm outside the workspace box'],
    ['Workspace box', '±35 cm along the line, ±10 cm across and up, around the start pose'],
    ['Watchdog', 'No command for 0.2 s holds the arm'],
    ['Robot contact limit', '30 N (SetMaxContactWrench)'],
    ['Moves the arm makes by itself', 'Only after a 3 s “hands off” countdown, never while the handle reads over 6 N, aborted on a 10 N change'],
    ['Human', 'A named e-stop holder for every session; <code>robot/RUNBOOK.md</code>, <code>robot/SAFETY.md</code>']], 'saf')
pages.append(page(7, 'Safety by construction', 'All limits live below everything else', '<p class="lead">Every limit sits in <code>robot/arm.py</code>, the only code that touches the robot, so no caller can override them.</p>' + saf))

# 8 lessons
les = table(['Problem on the real robot', 'Cause', 'Fix'], [
    ['Laptop could ping the arm but not control it', 'Remote Mode not enabled; RDK version must match robot software (v3.9.3 ↔ flexivrdk 1.7.0)', 'Elements Studio run in WSL, Remote Mode set to Ethernet, pinned RDK'],
    ['16 to 26 N reading with nothing touching', 'Constant joint-torque offset (shoulder, about 6 Nm) after joint moves; this Rizon 4 has no wrist sensor', 'Zero with <code>ZeroFTSensor</code> at the start pose before every set: <b>15.5 N → under 0.5 N</b>'],
    ['“10 N” level pulled 25 N', 'The robot applies stiffness along the <b>tool</b> axes, not the base axes; the 500 N/m wall landed on the push direction', 'Stiffness mapped onto the correct tool axis with an 11° correction; measured 200 N/m as commanded'],
    ['Return to start stopped and started', 'A soft spring dragged against about 4.5 N of friction (stick-slip)', 'Anchor walks back at a steady 5 cm/s; measured <b>zero stops</b>'],
    ['Freedrive hit a singularity', 'Arm stretched almost straight', 'Start pose chosen by joint-space moves, every joint at least 29° from its limit'],
    ['Rep counting missed real reps, counted phantom ones', 'Rep start depended on detecting a hand from a noisy force signal', 'Reps counted from position only']], 'les')
pages.append(page(8, 'What the real arm taught us', 'Six problems, six fixes', les))

# 9 sim first + run it
pages.append(page(9, 'Engineering', 'Built simulation-first', '''<div class="split">
<div class="facts">
<div><b>Real quirks, simulated</b><span><code>software/sim_arm.py</code> reproduces what we found on the robot: Coulomb friction, an empty-handle reading that varies with pose, sensor drift and noise, stiffness latency.</span></div>
<div><b>~900 tests</b><span>About 10,000 lines across <code>robot/</code>, <code>software/</code> and <code>server/</code>, including soak tests that run dozens of full sessions through the real HTTP API on the simulated arm with random patients.</span></div>
<div><b>Step-by-step bring-up</b><span>Scripts in <code>server/hw/</code> brought the real arm up one step at a time: read-only probe, joint moves with automatic stops, zeroing, drift check along the line, path trace, empty-handle engine runs.</span></div>
</div>
<div><h3>Run it without a robot</h3>
<pre>python -m venv .venv &amp;&amp; .venv/bin/pip install \\
  -r server/requirements.txt -r software/requirements.txt
.venv/bin/python -m server.run --mock</pre>
<p>Then open <code>http://127.0.0.1:8000</code>:</p>
<ul class="urls"><li><code>/app/</code> patient app</li><li><code>/screens/patient.html</code> big screen</li><li><code>/screens/physio.html</code> physio dashboard</li><li><code>/screens/operator.html</code> operator console</li></ul>
<p>Everything in mock mode is labelled SIMULATED.</p>
<h3>On the station laptop wired to the arm</h3>
<pre>python -m server.run --robot --lan</pre>
<p>Push only by default; <code>--with-row-strength</code> adds Row and the strength test. Cold-start steps are in <code>robot/RUNBOOK.md</code>.</p>
</div></div>'''))

# 10 repo + how we worked
repo = table(['Folder', 'What', 'Owner'], [
    ['<code>robot/</code>', '<code>arm.py</code> safety layer over the Flexiv RDK, config, run book, safety checks, tuning', 'Kian'],
    ['<code>software/</code>', 'Engines (Push, Row, Strength; the earlier adaptive engine), simulated arm and patient, metrics, rep detection', 'Shiv, Shyan'],
    ['<code>server/</code>', 'API, live feed, storage, exports, session note, screens, real-arm bring-up scripts (<code>server/hw/</code>)', 'Shyan'],
    ['<code>demo/</code>', 'Patient app, website, pitch deck', 'Mat, Gio'],
    ['<code>context/</code>', 'Shared plan, decisions and log the five people and their AI agents worked from', 'Everyone']])
pages.append(page(10, 'Team and process', 'How we worked', repo + '''<div class="three four">
<div><h3>Many agents, one branch</h3><p>Five people, each driving several Claude Code sessions at once on one <code>main</code> branch. 150+ commits in 48 hours.</p></div>
<div><h3>Shared context</h3><p>Every agent read the same <code>context/</code> files first: the master plan, a decisions log (time, who, what and why for every scope or architecture decision) and a running log of what each person had done, what was next and what was blocking others.</p></div>
<div><h3>Folder ownership</h3><p>Each folder has one owner, which kept parallel agents from editing the same files.</p></div>
<div><h3>Outreach to therapists</h3><p>Mat and Gio reached out to physiotherapists in the Netherlands and to therapists in Zurich to test the idea with the people who would use it. Mat talked with therapists to check that the exercises are done accurately and how supervision should work. The three Swiss physio centres we called all see more patients coming in, and said measured training would give them a better overview of each patient’s progress.</p></div></div>'''))

# 11 limits
pages.append(f'''<section class="pg cover end"><img src="vita-logo.png" class="logo sm" alt="vita">
<p class="eb">Status and honest limits</p>
<ul class="lim">
<li><b>Research prototype.</b> Tested by the team on a bare flange and a printed handle; not used with patients. A product like this is a medical device and needs certification first.</li>
<li><b>Simulated history.</b> The physio dashboard’s history is simulated and labelled so; today’s sessions are real.</li>
<li><b>Strength cap.</b> Strength readings are capped at about 30 N by the safety limits on this arm.</li>
<li><b>Row and the strength test.</b> Implemented and tested in simulation; real-arm checks passed on 16 November (empty handle and by hand). Row by hand was done at level 2 only.</li>
</ul>
<div class="meta"><div><span>Website</span>vitarehab.org</div><div><span>Patient app (simulated)</span>app.vitarehab.org</div><div><span>Code</span>github.com/shyan-shah/leukerbad-hack</div><div><span>Team</span>Shyan Shah, Shiv, Kian, Mat (Matvey), Gio van Belle</div></div>
</section>''')

CSS = '''
@import url('https://fonts.googleapis.com/css2?family=Outfit:wght@500;600;700&family=Instrument+Sans:wght@400;500;600&display=swap');
@page { size: 1280px 720px; margin: 0; }
* { box-sizing: border-box; margin: 0; padding: 0; }
body { font-family: 'Instrument Sans', system-ui, sans-serif; color: #1E282A; background: #888; -webkit-print-color-adjust: exact; print-color-adjust: exact; }
.pg { width: 1280px; height: 720px; background: #F8FCFC; position: relative; overflow: hidden; padding: 48px 72px 56px; page-break-after: always; break-after: page; display: flex; flex-direction: column; margin: 0 auto 20px; }
@media print { body { background: none; } .pg { margin: 0; } }
.pg:last-child { page-break-after: auto; break-after: auto; }
header { margin-bottom: 22px; } .eb { font: 600 13px 'Instrument Sans'; letter-spacing: .12em; text-transform: uppercase; color: #2F9DB6; margin-bottom: 6px; }
h2 { font: 700 38px/1.1 Outfit, sans-serif; color: #0A4552; letter-spacing: -.01em; }
h3 { font: 600 17px Outfit, sans-serif; color: #0A4552; margin-bottom: 6px; }
.body { flex: 1; min-height: 0; display: flex; flex-direction: column; justify-content: center; padding-bottom: 30px; }
footer { position: absolute; left: 72px; right: 72px; bottom: 22px; display: flex; justify-content: space-between; font-size: 11.5px; color: #8A9699; border-top: 1px solid #E3EAEB; padding-top: 10px; }
code { font: 500 .88em ui-monospace, Menlo, monospace; background: #E8F1F2; padding: 1px 5px; border-radius: 4px; color: #0A4552; }
table { width: 100%; border-collapse: collapse; font-size: 14px; line-height: 1.4; }
th { text-align: left; font: 600 11.5px 'Instrument Sans'; letter-spacing: .08em; text-transform: uppercase; color: #556164; padding: 8px 12px; border-bottom: 2px solid #0A4552; }
td { padding: 9px 12px; border-bottom: 1px solid #E3EAEB; vertical-align: top; }
tbody tr:nth-child(even) td { background: #F0F6F7; }
.ok { display: inline-grid; place-items: center; width: 18px; height: 18px; border-radius: 50%; background: #1F7F95; color: #fff; font-size: 11px; margin-right: 6px; vertical-align: -3px; }
.runs td:first-child { width: 38%; } .runs td:last-child { width: 18%; }
.stats { display: grid; grid-template-columns: repeat(4, 1fr); gap: 14px; margin-bottom: 20px; }
.stats div { background: #0A4552; color: #CFE0E3; border-radius: 12px; padding: 14px 18px; } .stats b { display: block; font: 700 30px/1 Outfit; color: #fff; margin-bottom: 6px; } .stats span { font-size: 13px; line-height: 1.35; display: block; }
.stats div:first-child b { color: #58E6F2; } .stats div:nth-child(3) b { color: #F1C36A; }
.arch { width: 100%; height: auto; margin: -6px 0 18px; }
.arch .zone { fill: #EEF5F6; stroke: #C9D9DC; stroke-dasharray: 6 6; } .arch .zl { font: 600 11px 'Instrument Sans'; letter-spacing: .1em; fill: #556164; }
.arch .bx rect { fill: #fff; stroke: #B8CCD0; stroke-width: 1.5; } .arch .bx.safe rect { stroke: #F1C36A; stroke-width: 2.5; fill: #FFFAEF; } .arch .bx.rb rect, .arch .bx.ph rect { fill: #0A4552; stroke: none; }
.arch .bt { font: 600 17px Outfit; fill: #0A4552; } .arch .bl { font: 13px 'Instrument Sans'; fill: #556164; }
.arch .rb .bt, .arch .ph .bt { fill: #fff; } .arch .rb .bl, .arch .ph .bl { fill: #BFD6DA; }
.arch .ar { stroke: #0A4552; stroke-width: 2; } .arch .al { font: 500 11.5px 'Instrument Sans'; fill: #556164; }
.three.four { grid-template-columns: repeat(4, 1fr); gap: 24px; } .three.four p { font-size: 13.5px; }
.three { display: grid; grid-template-columns: repeat(3, 1fr); gap: 28px; margin-top: 18px; } .three p { font-size: 14px; line-height: 1.5; color: #3B4749; }
.split { display: grid; grid-template-columns: 1fr 1fr; gap: 48px; align-items: center; } .split.w { grid-template-columns: 1.15fr 1fr; }
.band { width: 100%; height: auto; transform: scale(1.12); transform-origin: left center; margin: 20px 0; } .band .dl { font: 12.5px 'Instrument Sans'; fill: #556164; } .band .dl.b { font-weight: 600; fill: #0A4552; } .band .hd { font: 600 10px 'Instrument Sans'; fill: #0A4552; }
.cap { font-size: 13.5px; color: #556164; margin-top: 10px; line-height: 1.45; }
.steps { list-style: none; counter-reset: s; } .steps li { counter-increment: s; position: relative; padding: 0 0 13px 46px; font-size: 14.5px; line-height: 1.45; color: #3B4749; }
.steps li::before { content: counter(s); position: absolute; left: 0; top: -2px; width: 32px; height: 32px; border-radius: 50%; background: #0A4552; color: #F1C36A; font: 700 16px/32px Outfit; text-align: center; }
.steps b { color: #0A4552; }
.chart { width: 100%; height: auto; margin-bottom: 8px; } .chart .ax { font: 11.5px 'Instrument Sans'; fill: #556164; } .chart .lb { font: 600 13px 'Instrument Sans'; fill: #1E282A; } .chart .vl { font: 600 12.5px 'Instrument Sans'; fill: #1E282A; }
.num td:not(:first-child), .num th:not(:first-child) { text-align: right; } .num td { padding: 6px 12px; font-size: 13.5px; }
.facts { display: flex; flex-direction: column; gap: 12px; } .facts > div { border-left: 4px solid #58C4D4; background: #EEF5F6; border-radius: 0 10px 10px 0; padding: 11px 16px; }
.facts b { display: block; font: 700 22px/1.15 Outfit; color: #0A4552; margin-bottom: 3px; } .facts span { font-size: 13.5px; line-height: 1.45; color: #3B4749; }
.note { font-size: 12.5px; color: #556164; line-height: 1.45; }
.lead { font-size: 16px; color: #3B4749; margin-bottom: 16px; }
.saf td:first-child { width: 26%; font-weight: 600; color: #0A4552; } .saf td { padding: 10px 12px; font-size: 14.5px; }
.les td { font-size: 13px; padding: 9px 10px; } .les td:first-child { width: 24%; font-weight: 600; color: #0A4552; } .les td:nth-child(2) { width: 38%; color: #556164; }
pre { background: #0A4552; color: #DCEFF2; font: 12.5px/1.6 ui-monospace, Menlo, monospace; padding: 12px 16px; border-radius: 10px; margin: 6px 0 10px; white-space: pre-wrap; }
.split p { font-size: 13.5px; line-height: 1.45; color: #3B4749; margin-bottom: 6px; } .split h3 + pre { margin-top: 4px; } .split h3:not(:first-child) { margin-top: 14px; }
.urls { list-style: none; display: grid; grid-template-columns: 1fr 1fr; gap: 4px 12px; font-size: 13px; color: #3B4749; margin-bottom: 8px; }
.cover { background: #0A4552; color: #CFE0E3; padding: 64px 80px; justify-content: center; }
.cover .logo { width: 230px; margin: 0 0 30px -36px; } .cover .logo.sm { width: 170px; margin: 0 0 20px -27px; }
.cover h1 { font: 700 52px/1.08 Outfit; color: #fff; letter-spacing: -.015em; margin-bottom: 20px; }
.cover .sub { font-size: 17px; line-height: 1.55; max-width: 820px; margin-bottom: 34px; }
.cover .meta { display: grid; grid-template-columns: repeat(4, 1fr); gap: 24px; border-top: 1px solid rgba(239,242,243,.2); padding-top: 18px; font-size: 14px; line-height: 1.5; color: #EFF2F3; }
.cover .meta span { display: block; font: 600 11px 'Instrument Sans'; letter-spacing: .12em; text-transform: uppercase; color: #58E6F2; margin-bottom: 4px; } .cover .meta em { color: #A9CDD3; font-style: normal; font-size: 12.5px; }
.cover .pill { position: absolute; top: 56px; right: 80px; background: rgba(241,195,106,.15); color: #F1C36A; border: 1px solid rgba(241,195,106,.5); border-radius: 99px; padding: 7px 16px; font: 600 12.5px 'Instrument Sans'; }
.end .eb { color: #58E6F2; } .lim { list-style: none; margin: 8px 0 34px; display: grid; grid-template-columns: 1fr 1fr; gap: 14px 40px; }
.lim li { font-size: 15px; line-height: 1.5; padding-left: 16px; border-left: 3px solid #F1C36A; } .lim b { color: #fff; display: block; font: 600 17px Outfit; margin-bottom: 2px; }
'''
html = f'<!doctype html><html lang="en"><head><meta charset="utf-8"><title>Vita: hackathon hand-in</title><style>{CSS}</style></head><body>{"".join(pages)}</body></html>'
open(OUT, 'w').write(html)
print('wrote', OUT)
