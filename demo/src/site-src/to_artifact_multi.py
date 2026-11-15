import re, glob, os
SRC = os.path.expanduser('~/Desktop/vita-website/'); S = '/private/tmp/claude-501/-Users-matveyshelkovnikov/246ec8a5-69c2-457d-b80b-9610c58b0c4e/scratchpad/vita-artifact/'
for old in glob.glob(S + '*.html'): os.remove(old)
V = 'https://cdn.jsdelivr.net/npm/three@0.160.0/'
for p in glob.glob(SRC + '*.html'):
    name = os.path.basename(p); s = open(p).read()
    s = re.sub(r'<meta property="og:[^>]*>\n', '', s); s = s.replace('<link rel="icon" href="img/icon.png">\n', '')
    s = s.replace('"three":"./vendor/three.module.min.js","three/addons/environments/RoomEnvironment.js":"./vendor/RoomEnvironment.js","three/addons/geometries/RoundedBoxGeometry.js":"./vendor/RoundedBoxGeometry.js"', f'"three":"{V}build/three.module.min.js","three/addons/":"{V}examples/jsm/"')
    s = s.replace(' data-netlify="true" netlify-honeypot="company-website"', '')
    if "try { const r = await fetch('/'," in s:
        a = s.index("    try { const r = await fetch('/',"); e = "msg.textContent = 'Sending did not work. Please try again in a moment.'; } });"; b = s.index(e) + len(e)
        s = s[:a] + "    f.innerHTML = '<div class=\"sent\"><div class=\"t\">✓</div><h3>Thanks, ' + f.name.value.trim().replace(/[<>&]/g, '') + '.</h3><p>This is a preview of the site, so your message was not sent. We will connect the form before launch.</p></div>'; });" + s[b:]
        s = s.replace("b.disabled = true; b.textContent = 'Sending…'; msg.textContent = '';", "msg.textContent = '';")
    s = s.replace('header { position: sticky; top: 0;', 'header { position: sticky; top: env(safe-area-inset-top, 0px);')
    assert './vendor/' not in s, name
    if name == 'index.html':      # the artifact's own page: no skeleton, the service adds it
        s = s[s.index('<title>'):]; s = s.replace('</head>\n<body>\n', '', 1); s = s.rstrip(); assert s.endswith('</body>\n</html>'); s = s[:-len('</body>\n</html>')] + '\n'
    open(S + name, 'w').write(s); print(name, len(s))
