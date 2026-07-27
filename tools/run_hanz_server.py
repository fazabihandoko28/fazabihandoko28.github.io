import argparse
from hanz_server import HanzRealtimeService,SQLiteStateStore
from hanz_server.http_api import run_http_server
from hanz_server.notifier import ConsoleNotifier,TelegramNotifier
p=argparse.ArgumentParser();p.add_argument('--host',default='0.0.0.0');p.add_argument('--port',type=int,default=8080);p.add_argument('--db',default='data/hanz_realtime.db');p.add_argument('--telegram',action='store_true');a=p.parse_args();n=[ConsoleNotifier()]+([TelegramNotifier()] if a.telegram else []);run_http_server(HanzRealtimeService(SQLiteStateStore(a.db),notifiers=n),a.host,a.port)
