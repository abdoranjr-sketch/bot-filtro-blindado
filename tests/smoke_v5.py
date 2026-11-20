import os, sys, tempfile
os.environ.update({"DATA_DIR": tempfile.mkdtemp(), "TELEGRAM_TOKEN": "x", "TELEGRAM_CHAT_ID": "111", "TELEGRAM_GROUP_ID": "-100999"})
os.environ.pop("SPORTSAPI365_KEY", None)
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
import requests
def _blocked(*a, **k): raise AssertionError("real HTTP")
requests.get = requests.post = _blocked
import bot_filtro_blindado_v5 as b
from datetime import datetime, timedelta
clock = [b.TZ.localize(datetime(2026,11,20,7,49,50))]
b.agora_cet = lambda: clock[0]
sent = []
class TG:
    def __init__(s, *a): pass
    def send(s, t, chat_id=None, reply_to=None): sent.append((chat_id or "grp", t[:40])); return True
    def get_me(s): return {"username": "filtrobot", "id": 999}
    def get_updates(s, o=0): return [{"update_id": 5, "message": {"message_id": 1, "chat": {"id": -100999}, "from": {"id": 2, "first_name": "Zé"}, "text": "bom dia"}}] if o == 0 else []
b.Telegram = TG
b.ScoreMondo.fetch = lambda s: []
b.ScoreMondo.fetch_results = lambda s: []
b.ScoreMondo.fetch_fixtures = lambda s: []
n = [0]
def fake_sleep(sec):
    n[0] += 1; clock[0] += timedelta(minutes=5)
    if n[0] > 14: raise KeyboardInterrupt
b.time.sleep = fake_sleep
b.main()
for s in sent: print(s)
