import json,os,urllib.parse,urllib.request
class ConsoleNotifier:
    def send(self,event): print(json.dumps(event.to_dict(),ensure_ascii=False)); return True
class TelegramNotifier:
    def __init__(self,token=None,chat_id=None): self.token=token or os.getenv('HANZ_TELEGRAM_BOT_TOKEN'); self.chat_id=chat_id or os.getenv('HANZ_TELEGRAM_CHAT_ID')
    def send(self,event):
        if not self.token or not self.chat_id:return False
        lines=[f'HANZ • {event.symbol}',f'AKSI: {event.new_action}',f'EVIDENCE: {event.evidence}',f'RISIKO: {event.risk}']
        if event.price is not None:lines.append(f'HARGA: {event.price:g}')
        if event.trigger:lines.append(f'PEMICU: {event.trigger}')
        data=urllib.parse.urlencode({'chat_id':self.chat_id,'text':'\n'.join(lines)}).encode(); req=urllib.request.Request(f'https://api.telegram.org/bot{self.token}/sendMessage',data=data,method='POST')
        try:
            with urllib.request.urlopen(req,timeout=15) as r:return bool(json.loads(r.read().decode()).get('ok'))
        except:return False
