import json
from http.server import BaseHTTPRequestHandler,ThreadingHTTPServer
from urllib.parse import urlparse,parse_qs
from .models import DecisionSnapshot
class HanzHandler(BaseHTTPRequestHandler):
    service=None
    def j(self,status,p):
        b=json.dumps(p,ensure_ascii=False).encode(); self.send_response(status); self.send_header('Content-Type','application/json; charset=utf-8'); self.send_header('Content-Length',str(len(b))); self.end_headers(); self.wfile.write(b)
    def do_GET(self):
        if self.path.startswith('/health'):return self.j(200,{'ok':True,'service':'HANZ'})
        if self.path.startswith('/events'):
            q=parse_qs(urlparse(self.path).query); limit=int(q.get('limit',['50'])[0]); return self.j(200,{'ok':True,'events':[e.to_dict() for e in self.service.store.list_events(limit)]})
        self.j(404,{'ok':False,'error':'not_found'})
    def do_POST(self):
        try:p=json.loads(self.rfile.read(int(self.headers.get('Content-Length','0'))).decode())
        except:return self.j(400,{'ok':False,'error':'invalid_json'})
        if self.path=='/decision':
            e=self.service.process_decision(DecisionSnapshot.from_mapping(p)); return self.j(200,{'ok':True,'event':None if e is None else e.to_dict()})
        if self.path=='/decisions':
            es=self.service.process_payload(p); return self.j(200,{'ok':True,'events':[e.to_dict() for e in es]})
        self.j(404,{'ok':False,'error':'not_found'})
    def log_message(self,*a):pass
def run_http_server(service,host='0.0.0.0',port=8080):
    HanzHandler.service=service; s=ThreadingHTTPServer((host,port),HanzHandler); print(f'HANZ server listening on http://{host}:{port}'); s.serve_forever()
