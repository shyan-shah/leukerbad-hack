# Builds the pitch deck copies from science.src.html: local science.html, Desktop export folder and the single-file deck.
import os, base64, shutil
os.chdir(os.path.expanduser('~/vitalis-website'))
src = open('science.src.html').read()
SK = '<!doctype html><html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1,viewport-fit=cover"><style>body{margin:0}[hidden]{display:none!important}</style></head><body>'
open('science.html', 'w').write(SK + src + '</body></html>')
D = os.path.expanduser('~/Desktop/vita-pitch-deck')
open(D + '/index.html', 'w').write(SK + src + '</body></html>')
for f in ('science.js', 'vita-logo.png'): shutil.copy('assets/' + f, D + '/assets/' + f)
du = lambda f, t: f'data:{t};base64,' + base64.b64encode(open(f, 'rb').read()).decode()
one = src
for f in ('three.module.min.js', 'RoomEnvironment.js', 'RoundedBoxGeometry.js'): one = one.replace('./vendor/' + f, du('vendor/' + f, 'text/javascript'))
mod = open('assets/science.js').read(); old = "new URL('./vita-logo.png', import.meta.url).href"; assert mod.count(old) == 1
mod = mod.replace(old, "'" + du('assets/vita-logo.png', 'image/png') + "'")
import re; tag = re.search(r'<script type="module" src="assets/science\.js\?v=\d+"></script>', one).group(0)
one = one.replace(tag, '<script type="module">\n' + mod + '\n</script>')
open(D + '/vita-pitch-deck.html', 'w').write(SK + one + '</body></html>'); print('deck built', len(one))
