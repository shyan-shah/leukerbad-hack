# Builds the multi-page site: site-src/base.html + pages/*.html (+ site.css, site.js inlined) -> ~/Desktop/vita-website
import os, re, json, shutil, glob
os.chdir(os.path.expanduser('~/vitalis-website'))
O = os.path.expanduser('~/Desktop/vita-website'); os.makedirs(O + '/vendor', exist_ok=True); os.makedirs(O + '/img', exist_ok=True)
for old in glob.glob(O + '/*.html'): os.remove(old)
app = open('vita-app.html').read()
block = re.search(r'<!--3D-->.*?<!--/3D-->', app, re.S).group(0)
end = '</script>\n<!--/3D-->'; assert block.endswith(end)
three = block[:-len(end)] + open('site-src/hero3d.js').read() + end      # the hero's waving and pulling, site only
base, css, js = (open('site-src/' + f).read() for f in ('base.html', 'site.css', 'site.js'))
base = base.replace('<body>', '<body>\n' + open('site-src/icons.svg').read(), 1)
NAV = [('how-it-works', 'How it works'), ('exercises', 'Exercises'), ('safety', 'Safety'), ('locations', 'For locations')]
for p in sorted(glob.glob('site-src/pages/*.html')):
    name = os.path.basename(p)[:-5]; src = open(p).read()
    meta = json.loads(re.match(r'<!-- (\{.*?\}) -->\n', src).group(1)); body = src[src.index('\n') + 1:]
    nav = ''.join(f'<a href="{k}.html"' + (' aria-current="page"' if meta['nav'] == k else '') + f'>{t}</a>' for k, t in NAV)
    page = base
    for k, v in (('title', meta['title']), ('nav', nav), ('mainclass', 'home' if name == 'index' else 'page'), ('css', css), ('three', three if meta['three'] else ''), ('js', js), ('body', body)):
        page = page.replace('{{' + k + '}}', v)
    open(f'{O}/{name}.html', 'w').write(page); print('built', name, len(page))
for f in ['three.module.min.js', 'RoomEnvironment.js', 'RoundedBoxGeometry.js']: shutil.copy('vendor/' + f, O + '/vendor/' + f)
shutil.copy('assets/vita-logo.png', O + '/img/vita-logo.png')
open(O + '/_headers', 'w').write('/*\n  X-Content-Type-Options: nosniff\n  Referrer-Policy: strict-origin-when-cross-origin\n')
