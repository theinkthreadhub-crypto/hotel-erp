import json, http.server, sys
PNG='data:image/png;base64,iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mNk+M9QDwADhgGAWjR9awAAAABJRU5ErkJggg=='
class H(http.server.BaseHTTPRequestHandler):
    def _j(self, o):
        b=json.dumps(o).encode(); self.send_response(200); self.send_header('Content-Type','application/json'); self.send_header('Content-Length',str(len(b))); self.end_headers(); self.wfile.write(b)
    def do_GET(self): self._j({'state':'qr','qr':PNG,'me':'','sentToday':0,'limit':400,'queued':0})
    def do_POST(self): self._j({'ok':True})
    def log_message(self,*a): pass
http.server.HTTPServer(('127.0.0.1',int(sys.argv[1])),H).serve_forever()
