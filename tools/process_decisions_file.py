import argparse,json
from hanz_server import HanzRealtimeService,SQLiteStateStore
from hanz_server.notifier import ConsoleNotifier,TelegramNotifier
p=argparse.ArgumentParser();p.add_argument('--input',required=True);p.add_argument('--db',default='data/hanz_realtime.db');p.add_argument('--telegram',action='store_true');a=p.parse_args();n=[ConsoleNotifier()]+([TelegramNotifier()] if a.telegram else []);e=HanzRealtimeService(SQLiteStateStore(a.db),notifiers=n).process_file(a.input);print(json.dumps({'ok':True,'events':len(e)},ensure_ascii=False))
