# Splits the single-file app into a small Vite project (HTML, CSS, JS modules, three.js from npm) for Lovable or any host.
import os, shutil, json, re
os.chdir(os.path.expanduser('~/vitalis-website'))
SP = '/private/tmp/claude-501/-Users-matveyshelkovnikov/88632073-ba78-4019-bd73-918a46fc8c5e/scratchpad'
OUT = os.path.expanduser('~/Desktop/vita-app-lovable')
L = open('vita-app.html').read().split('\n')
find = lambda pred, start=0: next(i for i in range(start, len(L)) if pred(L[i]))
st0 = find(lambda l: l == '<style>'); st1 = find(lambda l: l == '</style>', st0)
mk0 = find(lambda l: l.startswith('<div class="phone3d"')); mk1 = find(lambda l: l == '<!--3D-->') 
js0 = find(lambda l: l == '<script>', mk1); js1 = find(lambda l: l == '</script>', js0)
fonts = next(l for l in L[:st0] if 'fonts.googleapis' in l)
css = '\n'.join(L[st0 + 1:st1])
markup = '\n'.join(L[mk0:mk1]).rstrip()
app = L[js0 + 1:js1]
d0 = next(i for i, l in enumerate(app) if l.startswith('// ---------- example data')); d1 = next(i for i, l in enumerate(app) if l.startswith('const fmt'))
data = app[d0:d1 + 1]; rest = app[:d0] + app[d1 + 1:]
data_js = '// Demo data. In the real app this comes from the backend: the exercise library, and the plan the specialist set for this patient.\n' + '\n'.join(data[1:]) + '\nexport { EX, PLANS, fmt };\n'
app_js = "// The patient app: screens, navigation, the exercise timer. Plain JavaScript, no framework.\nimport { EX, PLANS, fmt } from './data.js';\n" + '\n'.join(rest) + '\n'
# the 3D module: same code as in the published app, with three.js from npm and the logo as a normal file
part = '\n'.join(open('assets/science.js').read().split('\n')[27:126]).replace("logoImg.src = new URL('./vita-logo.png', import.meta.url).href;", "logoImg.src = LOGO;")
vita3d = open('app-src/vita3d.head.js').read() + "const LOGO = '/vita-logo.png';\n" + part + '\n' + open('app-src/vita3d.tail.js').read()
main_js = """import './style.css';
import './app.js';
// the 3D station loads on its own; if WebGL is missing the app keeps its simple drawn figures
import('./vita3d.js').catch((e) => console.warn('3D view not available:', e));
"""
base_css = """/* base */
html, body { margin: 0; height: 100%; }
body { font-family: system-ui, sans-serif; -webkit-font-smoothing: antialiased; }
img { max-width: 100%; }
[hidden] { display: none !important; }
:root { color-scheme: light; padding-top: env(safe-area-inset-top, 0px); padding-bottom: env(safe-area-inset-bottom, 0px); }
"""
index = f"""<!doctype html>
<html lang="en" style="height:100%">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1,viewport-fit=cover">
<meta name="theme-color" content="#F6F8F3">
<title>Vita</title>
<link rel="icon" href="/vita-logo.png">
{fonts}
</head>
<body>
{markup}
<script type="module" src="/src/main.js"></script>
</body>
</html>
"""
pkg = {"name": "vita-app", "private": True, "version": "0.1.0", "type": "module",
       "scripts": {"dev": "vite", "build": "vite build", "preview": "vite preview"},
       "dependencies": {"three": "0.160.0"}, "devDependencies": {"vite": "^5.4.0"}}
if os.path.exists(OUT): shutil.rmtree(OUT)
os.makedirs(OUT + '/src'); os.makedirs(OUT + '/public')
w = lambda p, t: open(os.path.join(OUT, p), 'w').write(t)
w('index.html', index); w('src/style.css', base_css + css.replace('\n  ', '\n') + '\n'); w('src/app.js', app_js); w('src/data.js', data_js); w('src/vita3d.js', vita3d); w('src/main.js', main_js)
w('package.json', json.dumps(pkg, indent=2) + '\n'); w('.gitignore', 'node_modules\ndist\n')
shutil.copy(SP + '/logo-small.png', OUT + '/public/vita-logo.png')
w('README.md', open('app-src/HANDOFF.md').read())
print('ok', OUT)
