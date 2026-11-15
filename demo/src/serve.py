#!/usr/bin/env python3
"""Preview server for the Vitalis site: python serve.py [port]. Sends every file fresh (no browser cache), so a change shows on a normal refresh."""
import http.server, os, sys

class Fresh(http.server.SimpleHTTPRequestHandler):
    def end_headers(self):
        self.send_header('Cache-Control', 'no-store')
        super().end_headers()
    def log_message(self, *a): pass

os.chdir(os.path.dirname(os.path.abspath(__file__)))
port = int(sys.argv[1]) if len(sys.argv) > 1 else 8801
print(f'Vitalis site on http://127.0.0.1:{port}/')
http.server.ThreadingHTTPServer(('127.0.0.1', port), Fresh).serve_forever()
