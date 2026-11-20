import os, sys, tempfile
os.environ.update({"DATA_DIR": tempfile.mkdtemp(), "TELEGRAM_TOKEN": "x", "TELEGRAM_CHAT_ID": "111",
                   "TELEGRAM_GROUP_ID": "-100888", "TELEGRAM_DISCUSSION_ID": "-100777"})
sys.path.insert(0, os.environ.get("BOT_DIR", os.path.join(os.path.dirname(os.path.abspath(__file__)), "..")))
import requests
def _blocked(*a, **k): raise AssertionError("real HTTP")
requests.get = requests.post = _blocked
import bot_filtro_blindado_v5 as b
from datetime import datetime
b.agora_cet = lambda: b.TZ.localize(datetime(2026, 11, 20, 9, 5))
class FakeTG:
    def __init__(s): s.sent = []
    def send(s, t, chat_id=None, reply_to=None): s.sent.append((str(chat_id or b.GROUP_ID), t)); return True
N = 0
def check(c, m):
    global N
    assert c, m; N += 1
hist, ap, conv, tg = b.Historico(), b.Apostas(b.APOSTAS_FILE), b.Conversa("filtro_czech_bot", "999"), FakeTG()
def msg(text, chat="-100777", uid="222", name="João", typ="supergroup", **extra):
    m = {"message_id": 5, "chat": {"id": int(chat), "type": typ}, "from": {"id": int(uid), "first_name": name, "is_bot": False}, "text": text}
    m.update(extra); return {"update_id": 1, "message": m}
# conversa no grupo de discussão
check(b.tratar_update(msg("bom dia"), tg, hist, ap, conv) == "conversa" and tg.sent[-1][0] == "-100777", "bom dia na discussão")
for c in ["/placar", "/semana", "/mes", "/entradas", "/ajuda", "/id@filtro_czech_bot"]:
    check(b.tratar_update(msg(c), tg, hist, ap, conv) == "comando" and tg.sent[-1][0] == "-100777", c)
check("-100777" in tg.sent[-1][1] and "Seu ID" in tg.sent[-1][1], "/id na discussão")
# post do canal repassado automaticamente: ignorar
n = len(tg.sent)
fw = msg("🎯 ENTRADA 08:55 bom dia", uid="777000", name="Telegram", is_automatic_forward=True, sender_chat={"id": -100888, "type": "channel"})
check(b.tratar_update(fw, tg, hist, ap, conv) is None and len(tg.sent) == n, "auto-forward ignorado")
fw2 = msg("/placar", uid="777000", is_automatic_forward=True)
check(b.tratar_update(fw2, tg, hist, ap, conv) is None and len(tg.sent) == n, "comando auto-forward ignorado")
# admin falando "como canal" no grupo: não conversa
check(b.tratar_update(msg("boa tarde", uid="136817688", name="Channel", sender_chat={"id": -100888}), tg, hist, ap, conv) is None, "sender_chat")
# boas-vindas na discussão
check(b.tratar_update(msg("", new_chat_members=[{"first_name": "Maria", "is_bot": False}]), tg, hist, ap, conv) == "boas_vindas" and tg.sent[-1][0] == "-100777", "boas-vindas")
# canal: comandos ok, conversa não
cp = {"update_id": 3, "channel_post": {"message_id": 9, "chat": {"id": -100888, "type": "channel"}, "text": "bom dia"}}
check(b.tratar_update(cp, tg, hist, ap, conv) is None, "canal sem conversa")
cp["channel_post"]["text"] = "/placar"
check(b.tratar_update(cp, tg, hist, ap, conv) == "comando" and tg.sent[-1][0] == "-100888", "comando no canal")
# entradas/saudações continuam no canal (destino padrão)
ev = b.CacheSet(b.EVENTOS_FILE); b.agora_cet = lambda: b.TZ.localize(datetime(2026, 11, 20, 7, 50))
tg2 = FakeTG(); b.tarefas_agendadas(tg2, ap, ev)
check(tg2.sent and tg2.sent[0][0] == "-100888", "bom dia agendado no canal")
# outro grupo qualquer: ignorado (exceto /id)
check(b.tratar_update(msg("bom dia", chat="-100555"), tg, hist, ap, conv) is None, "grupo estranho")
check(b.tratar_update(msg("/id", chat="-100555"), tg, hist, ap, conv) == "comando", "/id em qualquer grupo")
print("DISCUSSAO OK", N, "checks")
