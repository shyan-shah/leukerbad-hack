# Builds the app: puts the 3D module (deck scene code + app motions) into vita-app.html, then writes the local test copy and the Desktop export.
import os, re, base64
os.chdir(os.path.expanduser('~/vitalis-website'))
SP = '/private/tmp/claude-501/-Users-matveyshelkovnikov/88632073-ba78-4019-bd73-918a46fc8c5e/scratchpad'
sci = open('assets/science.js').read().split('\n')
part = '\n'.join(sci[27:126])                     # science.js lines 28-126: materials, room, chair, Anna, robot
logo = 'data:image/png;base64,' + base64.b64encode(open(SP + '/logo-small.png', 'rb').read()).decode()
old = "logoImg.src = new URL('./vita-logo.png', import.meta.url).href;"
assert part.count(old) == 1; part = part.replace(old, "logoImg.src = LOGO;")
mod = open('app-src/vita3d.head.js').read() + f"const LOGO = '{logo}';\n" + part + '\n' + open('app-src/vita3d.tail.js').read()
IM = '<script type="importmap">{"imports":{"three":"./vendor/three.module.min.js","three/addons/environments/RoomEnvironment.js":"./vendor/RoomEnvironment.js","three/addons/geometries/RoundedBoxGeometry.js":"./vendor/RoundedBoxGeometry.js"}}</script>'
block = '<!--3D-->\n' + IM + '\n<script type="module">\n' + mod + '\n</script>\n<!--/3D-->'
s = open('vita-app.html').read()
if '<!--3D-->' in s: s = re.sub(r'<!--3D-->.*?<!--/3D-->', lambda m: block, s, flags=re.S)
else: s = s.replace('\n<script>\n', '\n' + block + '\n<script>\n', 1)
open('vita-app.html', 'w').write(s)
open('vita-app.local.html', 'w').write('<!doctype html><html style="height:100%"><head><meta charset=utf8><meta name=viewport content="width=device-width,initial-scale=1"><style>body{margin:0}[hidden]{display:none!important}</style></head><body>' + s + '</body></html>')
# the Desktop copy works by double-click: the three.js files go inside it as data URLs
du = lambda f: 'data:text/javascript;base64,' + base64.b64encode(open(f, 'rb').read()).decode()
im2 = IM.replace('./vendor/three.module.min.js', du('vendor/three.module.min.js')).replace('./vendor/RoomEnvironment.js', du('vendor/RoomEnvironment.js')).replace('./vendor/RoundedBoxGeometry.js', du('vendor/RoundedBoxGeometry.js'))
s2 = s.replace(IM, im2).replace('<script src="./vendor/jsQR.js"></script>', '<script>' + open('vendor/jsQR.js').read() + '</script>')
open(os.path.expanduser('~/Desktop/vita-pitch-deck/vita-app.html'), 'w').write('<!doctype html><html lang="en" style="height:100%"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1,viewport-fit=cover"><style>:root{color-scheme:light}body{margin:0}img{max-width:100%}[hidden]{display:none!important}</style></head><body>' + s2 + '</body></html>')
# the Netlify folder: drag it onto app.netlify.com/drop
import shutil
N = os.path.expanduser('~/Desktop/vita-app-netlify'); os.makedirs(N + '/vendor', exist_ok=True)
for f in ['three.module.min.js', 'RoomEnvironment.js', 'RoundedBoxGeometry.js', 'jsQR.js', 'qrcode.js']: shutil.copy('vendor/' + f, N + '/vendor/' + f)
open(N + '/index.html', 'w').write('<!doctype html><html lang="en" style="height:100%"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1,viewport-fit=cover"><meta name="theme-color" content="#0f3d34"><style>:root{color-scheme:light}body{margin:0}img{max-width:100%}[hidden]{display:none!important}</style></head><body>' + s + '</body></html>')
shutil.copy('app-src/stations.html', N + '/stations.html')
open(N + '/_headers', 'w').write('/*\n  Permissions-Policy: camera=(self)\n  Cache-Control: no-cache\n')
B = os.path.expanduser('~/vita-backend/app'); shutil.rmtree(B, ignore_errors=True); shutil.copytree(N, B, ignore=shutil.ignore_patterns('_headers'))
print('built', len(s), len(s2), 'netlify ->', N)
