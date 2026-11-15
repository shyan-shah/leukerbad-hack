#!/usr/bin/env python3
"""Vita backend, for testing: runs on this laptop and stores patients' progress in a SQLite file.

Start it with:   python3 server.py            (or double-click start.command)
First time, tell it where the app is hosted:   python3 server.py --site https://your-site.netlify.app

It also opens a free Cloudflare tunnel (when cloudflared is installed), so a phone anywhere can reach it
over https. The page at http://localhost:8787 shows the phone link and a QR code to open the app with.

Only the Python standard library is used. The robot can send measurements to POST /api/robot/measurement later.
"""
import hashlib, json, os, re, secrets, sqlite3, subprocess, sys, threading, time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import urlparse, parse_qs, quote

HERE = os.path.dirname(os.path.abspath(__file__))
DB = os.path.join(HERE, 'vita.db')
CONF = os.path.join(HERE, 'config.json')
PORT = int(os.environ.get('VITA_PORT', '8787'))

# ---------- settings kept between runs: the app's address and the key the app must send ----------
conf = {}
if os.path.exists(CONF):
    try: conf = json.load(open(CONF))
    except Exception: conf = {}
if '--site' in sys.argv:
    conf['site'] = sys.argv[sys.argv.index('--site') + 1].rstrip('/')
conf.setdefault('key', secrets.token_urlsafe(12))
json.dump(conf, open(CONF, 'w'), indent=2)
TUNNEL = {'url': None}

# ---------- database ----------
def db():
    c = sqlite3.connect(DB, timeout=10); c.row_factory = sqlite3.Row; return c

with db() as c:
    c.executescript("""
    CREATE TABLE IF NOT EXISTS stations (id INTEGER PRIMARY KEY, name TEXT, location TEXT);
    CREATE TABLE IF NOT EXISTS sessions (id INTEGER PRIMARY KEY AUTOINCREMENT, patient TEXT, station INTEGER, started REAL);
    CREATE TABLE IF NOT EXISTS results (id INTEGER PRIMARY KEY AUTOINCREMENT, patient TEXT, plan TEXT, exercise TEXT, reps INTEGER,
        value REAL, unit TEXT, station INTEGER, source TEXT, at REAL);
    CREATE TABLE IF NOT EXISTS progress (patient TEXT, plan TEXT, data TEXT, updated REAL, PRIMARY KEY (patient, plan));
    CREATE TABLE IF NOT EXISTS settings (patient TEXT PRIMARY KEY, data TEXT, updated REAL);
    CREATE TABLE IF NOT EXISTS users (id INTEGER PRIMARY KEY AUTOINCREMENT, name TEXT, email TEXT UNIQUE, pw TEXT, salt TEXT, plan TEXT, created REAL);
    CREATE TABLE IF NOT EXISTS tokens (token TEXT PRIMARY KEY, user INTEGER, created REAL);
    """)
    if not c.execute('SELECT COUNT(*) FROM stations').fetchone()[0]:
        c.executemany('INSERT INTO stations VALUES (?,?,?)', [(1, 'Vita station 1', 'Gym'), (2, 'Vita station 2', 'Gym'), (3, 'Vita station 3', 'Care home')])

# ---------- accounts: passwords are stored only as a salted PBKDF2 hash; a log-in gives the phone a random token ----------
def pw_hash(pw, salt): return hashlib.pbkdf2_hmac('sha256', pw.encode(), bytes.fromhex(salt), 200_000).hex()
def public(u): return {'id': u['id'], 'name': u['name'], 'email': u['email'], 'plan': u['plan'], 'created': u['created']}
def new_token(c, uid):
    t = secrets.token_urlsafe(24); c.execute('INSERT INTO tokens VALUES (?,?,?)', (t, uid, time.time())); return t
EMAIL = re.compile(r'^[^@\s]+@[^@\s]+\.[^@\s]+$')

APP = os.path.join(HERE, 'app')   # a copy of the app, served at /app/ through the tunnel (no Netlify password needed)
TYPES = {'.html': 'text/html', '.js': 'text/javascript', '.css': 'text/css', '.png': 'image/png', '.svg': 'image/svg+xml', '.json': 'application/json'}

def phone_link():
    if not TUNNEL['url']: return None
    if not conf.get('site') and os.path.isdir(APP): return f"{TUNNEL['url']}/app/?api={quote(TUNNEL['url'], safe='')}&key={quote(conf['key'], safe='')}"
    if not conf.get('site'): return None
    return f"{conf['site']}/?api={quote(TUNNEL['url'], safe='')}&key={quote(conf['key'], safe='')}"

# ---------- the API ----------
class H(BaseHTTPRequestHandler):
    server_version = 'vita-backend'

    def log_message(self, fmt, *a):
        sys.stderr.write('  %s %s\n' % (time.strftime('%H:%M:%S'), fmt % a))

    def send(self, code, body, ctype='application/json'):
        data = body if isinstance(body, bytes) else (json.dumps(body) if ctype == 'application/json' else body).encode()
        self.send_response(code)
        self.send_header('Content-Type', ctype + '; charset=utf-8')
        self.send_header('Access-Control-Allow-Origin', '*')
        self.send_header('Access-Control-Allow-Headers', 'Content-Type, X-Vita-Key, Authorization')
        self.send_header('Access-Control-Allow-Methods', 'GET, POST, PUT, OPTIONS')
        self.send_header('Cache-Control', 'no-store')
        self.send_header('Content-Length', str(len(data)))
        self.end_headers(); self.wfile.write(data)

    def do_OPTIONS(self): self.send(204, b'', 'text/plain')

    def body(self):
        n = int(self.headers.get('Content-Length') or 0)
        try: return json.loads(self.rfile.read(n) or b'{}')
        except Exception: return {}

    def local(self):      # the request comes from this laptop, not through the tunnel
        return self.client_address[0] in ('127.0.0.1', '::1') and not self.headers.get('Cf-Connecting-Ip')

    def user(self, c):   # the logged-in account, from 'Authorization: Bearer <token>'
        a = self.headers.get('Authorization', '')
        if not a.startswith('Bearer '): return None
        return c.execute('SELECT users.* FROM tokens JOIN users ON users.id = tokens.user WHERE tokens.token=?', (a[7:],)).fetchone()

    def allowed(self):    # the API needs the key, except from this laptop itself
        return self.local() or secrets.compare_digest(self.headers.get('X-Vita-Key', ''), conf['key'])

    def route(self, method):
        u = urlparse(self.path); q = {k: v[0] for k, v in parse_qs(u.query).items()}; p = u.path.rstrip('/') or '/'
        if p == '/' and method == 'GET': return self.send(200, status_page(), 'text/html')
        if p == '/qrcode.js': return self.send(200, open(os.path.join(HERE, 'qrcode.js'), 'rb').read(), 'text/javascript')
        if (p == '/app' or p.startswith('/app/')) and method == 'GET':
            if p == '/app' and not u.path.endswith('/'): self.send_response(301); self.send_header('Location', '/app/' + ('?' + u.query if u.query else '')); self.end_headers(); return
            rel = p[5:] or 'index.html'; f = os.path.realpath(os.path.join(APP, rel))
            if not f.startswith(os.path.realpath(APP) + os.sep) or not os.path.isfile(f): return self.send(404, {'error': 'not found'})
            return self.send(200, open(f, 'rb').read(), TYPES.get(os.path.splitext(f)[1], 'application/octet-stream'))
        if p == '/api/health': return self.send(200, {'ok': True, 'name': 'vita-backend', 'time': time.time()})
        if not p.startswith('/api/'): return self.send(404, {'error': 'not found'})
        if not self.allowed(): return self.send(401, {'error': 'wrong or missing key'})
        with db() as c:
            me = self.user(c)
            # ---- accounts ----
            if p == '/api/auth/signup' and method == 'POST':
                b = self.body(); name = str(b.get('name') or '').strip()[:60]; email = str(b.get('email') or '').strip().lower()[:120]; pw = str(b.get('password') or '')
                if not name: return self.send(400, {'error': 'Please fill in your name.'})
                if not EMAIL.match(email): return self.send(400, {'error': 'That email address does not look right.'})
                if len(pw) < 8: return self.send(400, {'error': 'Choose a password of at least 8 characters.'})
                if c.execute('SELECT 1 FROM users WHERE email=?', (email,)).fetchone(): return self.send(409, {'error': 'There is already an account with this email. Log in instead.'})
                salt = secrets.token_hex(16)
                uid = c.execute('INSERT INTO users (name, email, pw, salt, plan, created) VALUES (?,?,?,?,?,?)', (name, email, pw_hash(pw, salt), salt, None, time.time())).lastrowid
                u = c.execute('SELECT * FROM users WHERE id=?', (uid,)).fetchone()
                return self.send(200, {'token': new_token(c, uid), 'user': public(u)})
            if p == '/api/auth/login' and method == 'POST':
                b = self.body(); email = str(b.get('email') or '').strip().lower(); pw = str(b.get('password') or '')
                u = c.execute('SELECT * FROM users WHERE email=?', (email,)).fetchone()
                if not u or not secrets.compare_digest(pw_hash(pw, u['salt']), u['pw']): time.sleep(0.5); return self.send(401, {'error': 'Wrong email or password.'})
                return self.send(200, {'token': new_token(c, u['id']), 'user': public(u)})
            if p == '/api/auth/logout' and method == 'POST':
                a = self.headers.get('Authorization', ''); c.execute('DELETE FROM tokens WHERE token=?', (a[7:],)); return self.send(200, {'ok': True})
            if p == '/api/me':
                if not me: return self.send(401, {'error': 'not logged in', 'auth': True})
                if method == 'PUT':
                    b = self.body()
                    if 'plan' in b: c.execute('UPDATE users SET plan=? WHERE id=?', (str(b['plan'])[:40], me['id']))
                    if b.get('name'): c.execute('UPDATE users SET name=? WHERE id=?', (str(b['name']).strip()[:60], me['id']))
                    me = c.execute('SELECT * FROM users WHERE id=?', (me['id'],)).fetchone()
                st = c.execute('SELECT data FROM settings WHERE patient=?', (f"user:{me['id']}",)).fetchone()
                return self.send(200, {'user': public(me), 'settings': json.loads(st['data']) if st else None})
            # everything a patient saves belongs to the logged-in account when there is one
            who = f"user:{me['id']}" if me else None
            if who and method in ('POST', 'PUT'):
                _b = self.body(); _b['patient'] = who; self.body = lambda: _b
            if who: q['patient'] = who
            if p == '/api/stations' and method == 'GET':
                return self.send(200, [dict(r) for r in c.execute('SELECT * FROM stations')])
            m = re.fullmatch(r'/api/stations/(\d+)', p)
            if m and method == 'GET':
                r = c.execute('SELECT * FROM stations WHERE id=?', (int(m.group(1)),)).fetchone()
                return self.send(200, dict(r)) if r else self.send(404, {'error': 'no such station'})
            if p == '/api/scan' and method == 'POST':
                b = self.body(); st = c.execute('SELECT * FROM stations WHERE id=?', (int(b.get('station') or 0),)).fetchone()
                if not st: return self.send(404, {'error': 'no such station'})
                cur = c.execute('INSERT INTO sessions (patient, station, started) VALUES (?,?,?)', (b.get('patient'), st['id'], time.time()))
                return self.send(200, {'session': cur.lastrowid, 'station': dict(st)})
            if p == '/api/progress' and method == 'GET':
                r = c.execute('SELECT data, updated FROM progress WHERE patient=? AND plan=?', (q.get('patient'), q.get('plan'))).fetchone()
                return self.send(200, {'hist': json.loads(r['data']) if r else None, 'updated': r['updated'] if r else None})
            if p == '/api/progress' and method == 'PUT':
                b = self.body()
                c.execute('INSERT OR REPLACE INTO progress VALUES (?,?,?,?)', (b.get('patient'), b.get('plan'), json.dumps(b.get('hist')), time.time()))
                return self.send(200, {'ok': True})
            if p == '/api/results' and method == 'POST':
                b = self.body()
                c.execute('INSERT INTO results (patient, plan, exercise, reps, value, unit, station, source, at) VALUES (?,?,?,?,?,?,?,?,?)',
                          (b.get('patient'), b.get('plan'), b.get('exercise'), b.get('reps'), b.get('value'), b.get('unit'), b.get('station'), 'app', time.time()))
                return self.send(200, {'ok': True})
            if p == '/api/results' and method == 'GET':
                return self.send(200, [dict(r) for r in c.execute('SELECT * FROM results ORDER BY id DESC LIMIT 100')])
            if p == '/api/robot/measurement' and method == 'POST':
                # for later: the robot reports a finished exercise; it lands in the patient's progress like the app's own results
                b = self.body(); pat, plan = b.get('patient'), b.get('plan')
                c.execute('INSERT INTO results (patient, plan, exercise, reps, value, unit, station, source, at) VALUES (?,?,?,?,?,?,?,?,?)',
                          (pat, plan, b.get('exercise'), b.get('reps'), b.get('value'), b.get('unit'), b.get('station'), 'robot', time.time()))
                r = c.execute('SELECT data FROM progress WHERE patient=? AND plan=?', (pat, plan)).fetchone()
                if r and b.get('value') is not None:
                    h = json.loads(r['data']); h['pts'].append(b['value']); h['ex'] = h.get('ex', 0) + 1
                    h['reps'][b.get('exercise')] = h['reps'].get(b.get('exercise'), 0) + int(b.get('reps') or 0)
                    c.execute('UPDATE progress SET data=?, updated=? WHERE patient=? AND plan=?', (json.dumps(h), time.time(), pat, plan))
                return self.send(200, {'ok': True})
            if p == '/api/settings' and method == 'GET':
                r = c.execute('SELECT data FROM settings WHERE patient=?', (q.get('patient'),)).fetchone()
                return self.send(200, {'settings': json.loads(r['data']) if r else None})
            if p == '/api/settings' and method == 'PUT':
                b = self.body(); c.execute('INSERT OR REPLACE INTO settings VALUES (?,?,?)', (b.get('patient'), json.dumps(b.get('settings')), time.time()))
                return self.send(200, {'ok': True})
        return self.send(404, {'error': 'not found'})

    def do_GET(self): self.route('GET')
    def do_POST(self): self.route('POST')
    def do_PUT(self): self.route('PUT')

def esc(s): return str(s).replace('&', '&amp;').replace('<', '&lt;').replace('>', '&gt;').replace('"', '&quot;')

def status_page():
    with db() as c:
        rows = c.execute('SELECT * FROM results ORDER BY id DESC LIMIT 15').fetchall()
        n_ses = c.execute('SELECT COUNT(*) FROM sessions').fetchone()[0]
        users = c.execute('SELECT * FROM users ORDER BY id').fetchall()
    names = {f"user:{u['id']}": u['name'] for u in users}
    link = phone_link()
    res = ''.join(f"<tr><td>{time.strftime('%H:%M', time.localtime(r['at']))}</td><td>{esc(names.get(r['patient'], r['patient']))}</td><td>{esc(r['exercise'])}</td><td>{r['reps']}</td><td>{'' if r['value'] is None else esc(r['value'])} {esc(r['unit'] or '')}</td><td>{esc(r['source'])}</td></tr>" for r in rows) or '<tr><td colspan="6">Nothing yet. Finish an exercise in the app.</td></tr>'
    if link:
        how = f'<p>Scan this with your phone camera. It opens the app connected to this laptop:</p><div id="qr"></div><p class="mono">{esc(link)}</p><p>Station codes to scan from the app: <a href="{esc(conf.get('site') or TUNNEL['url'] + '/app')}/stations.html" target="_blank">open the station codes</a></p>'
    elif not conf.get('site'):
        how = '<p><b>Tell me where the app is hosted.</b> Stop this server (Ctrl+C) and start it again with<br><span class="mono">python3 server.py --site https://YOUR-SITE.netlify.app</span></p>'
    else:
        how = '<p>Waiting for the tunnel… reload in a few seconds. (Is cloudflared installed? <span class="mono">brew install cloudflared</span>)</p>'
    return f"""<!doctype html><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>Vita backend</title>
<meta http-equiv="refresh" content="{'20' if link else '4'}">
<style>body{{font:16px/1.5 system-ui,sans-serif;max-width:760px;margin:40px auto;padding:0 20px;color:#17241F;background:#F6F8F3}}h1{{color:#064D3B}}
.card{{background:#fff;border-radius:16px;padding:18px 22px;box-shadow:0 0 0 1px #DFE7E1;margin:16px 0}}.mono{{font-family:ui-monospace,monospace;font-size:13px;word-break:break-all;color:#5E6D66}}
table{{width:100%;border-collapse:collapse;font-size:14px}}td,th{{text-align:left;padding:6px 8px;border-top:1px solid #DFE7E1}}#qr img{{width:220px;image-rendering:pixelated}}.ok{{color:#12845C;font-weight:600}}</style>
<h1>Vita backend is running</h1>
<div class="card"><p class="ok">● Running on this laptop, port {PORT}</p>
<p>Public address: <span class="mono">{esc(TUNNEL['url'] or 'starting…')}</span><br>App: <span class="mono">{esc(conf.get('site') or 'not set')}</span><br>Key: <span class="mono">{esc(conf['key'])}</span></p></div>
<div class="card">{how}</div>
<div class="card"><b>Accounts</b> ({len(users)})<table><tr><th>Name</th><th>Email</th><th>Plan</th><th>Since</th></tr>{''.join(f"<tr><td>{esc(u['name'])}</td><td>{esc(u['email'])}</td><td>{esc(u['plan'] or 'not chosen yet')}</td><td>{time.strftime('%d %b %H:%M', time.localtime(u['created']))}</td></tr>" for u in users) or '<tr><td colspan="4">No accounts yet. Create one in the app.</td></tr>'}</table></div>
<div class="card"><b>Latest results</b> ({n_ses} scans so far)<table><tr><th>Time</th><th>Patient</th><th>Exercise</th><th>Reps</th><th>Value</th><th>From</th></tr>{res}</table></div>
<p class="mono">Database: {esc(DB)}</p>
<script src="/qrcode.js"></script><script>{'var q=qrcode(0,"M");q.addData(' + json.dumps(link) + ');q.make();document.getElementById("qr").innerHTML=q.createImgTag(6,8);' if link else ''}</script>"""

# ---------- the tunnel: a public https address for this laptop ----------
def tunnel():
    exe = next((p for p in ('/opt/homebrew/bin/cloudflared', '/usr/local/bin/cloudflared') if os.path.exists(p)), None)
    if not exe: print('  (cloudflared not found: the phone can only reach this laptop on the same Wi-Fi)'); return
    proc = subprocess.Popen([exe, 'tunnel', '--no-autoupdate', '--url', f'http://localhost:{PORT}'], stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True)
    for line in proc.stdout:
        m = re.search(r'https://[a-z0-9-]+\.trycloudflare\.com', line)
        if m and not TUNNEL['url']:
            TUNNEL['url'] = m.group(0)
            print('\n  Public address:', TUNNEL['url'])
            link = phone_link()
            print('  Open on your phone:', link or '(start with --site https://YOUR-SITE.netlify.app to get the phone link)')
            print(f'  Or scan the QR code at http://localhost:{PORT}\n')

if __name__ == '__main__':
    print(f'\n  Vita backend on http://localhost:{PORT}  (Ctrl+C stops it)')
    print('  Database:', DB)
    if '--no-tunnel' not in sys.argv: threading.Thread(target=tunnel, daemon=True).start()
    try: ThreadingHTTPServer(('0.0.0.0', PORT), H).serve_forever()
    except KeyboardInterrupt: print('\n  Stopped.')
