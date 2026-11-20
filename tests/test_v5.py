import os, sys, tempfile, json
D = tempfile.mkdtemp()
os.environ.update({"DATA_DIR": D, "TELEGRAM_TOKEN": "x", "TELEGRAM_CHAT_ID": "111", "TELEGRAM_GROUP_ID": "-100999"})
os.environ.pop("MOVIODDS_KEY", None); os.environ.pop("TELEGRAM_OWNER_ID", None)
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
import requests
def _blocked(*a, **k): raise AssertionError("real HTTP call attempted")
requests.get = requests.post = _blocked
import bot_filtro_blindado_v5 as b
from datetime import datetime, timedelta

def at(y,mo,d,h,mi,s=0):
    dt = b.TZ.localize(datetime(y,mo,d,h,mi,s)); b.agora_cet = lambda: dt; return dt
class FakeTG:
    def __init__(s, ok=True): s.sent=[]; s.ok=ok
    def send(s, t, chat_id=None, reply_to=None):
        if not s.ok: return False
        s.sent.append((str(chat_id or "-100999"), t, reply_to)); return True
    def texts(s): return [t for _, t, _ in s.sent]
N = 0
def check(c, m):
    global N
    assert c, m; N += 1

K = lambda h, m, d=20: b.TZ.localize(datetime(2026, 11, d, h, m))
def par_verde(h, fav, und, ini):
    """Favorito com 2 vitórias limpas hoje e adversário com derrota 0-3."""
    h.definir_jogos(fav, [
        {"resultado": "limpo", "sets_favor": 3, "sets_contra": 0, "inicio": ini},
        {"resultado": "limpo", "sets_favor": 3, "sets_contra": 1, "inicio": ini + timedelta(minutes=20)},
    ])
    h.definir_jogos(und, [
        {"resultado": "derrota", "sets_favor": 0, "sets_contra": 3, "inicio": ini},
    ])
# ---------- 1. entrada 08:55 registra apostas
at(2026,11,20,8,55,5)
hist = b.Historico()
par_verde(hist, "A Alfa", "B Beta", K(8, 0))
par_verde(hist, "C Gama", "D Delta", K(8, 0))
par_verde(hist, "E Eps", "F Fi", K(8, 0))
fx = [b.OddsMatch("A Alfa","B Beta",1.50,2.50,False,None,K(9,0)),
      b.OddsMatch("D Delta","C Gama",2.50,1.50,False,None,K(9,0)),
      b.OddsMatch("E Eps","F Fi",1.50,2.50,False,None,K(9,30))]
tg = FakeTG(); ap = b.Apostas(b.APOSTAS_FILE)
sinais, entradas = b.CacheSet(b.ENVIADOS_FILE), b.CacheSet(b.ENTRADAS_FILE)
b.processar_entrada("2026-11-20|08:55", hist, sinais, entradas, tg, fx, ap)
check(len(tg.sent) == 1 and tg.sent[0][0] == "-100999", "entrada no grupo")
check(len(ap.itens) == 3 and all(a["bloco"] == "09" and a["status"] == "pendente" for a in ap.itens), ap.itens)
check(ap.get(b.chave_sinal("C Gama","D Delta","2026-11-20"))["pick"] == "C Gama", "pick")

# ---------- 2. green / red / anulada
R = b.Resultado
res = [R("A Alfa","B Beta",3,1,K(9,0),"1"),            # green
       R("D Delta","C Gama",3,2,K(9,0),"2"),           # red (pick C Gama perdeu)
       R("A Alfa","B Beta",0,3,K(8,0),"0")]            # mesmo par na 1ª rodada: ignorar (horário)
at(2026,11,20,9,40)
check(b.resolver_apostas(ap, res) == 2, "2 resolvidas")
check(b.notificar_resultados(ap, tg) == 2, "2 avisos")
t_green, t_red = tg.texts()[1], tg.texts()[2]
check("GREEN" in t_green and "3-1" in t_green and "Hoje: 1 ✅ / 0 ❌ — 100%" in t_green, t_green)
check("RED" in t_red and "Hoje: 1 ✅ / 1 ❌ — 50%" in t_red, t_red)
at(2026,11,20,11,0); b.resolver_apostas(ap, res)
check(ap.get(b.chave_sinal("E Eps","F Fi","2026-11-20"))["status"] == "pendente", "ainda pendente <3h")
at(2026,11,20,12,31); b.resolver_apostas(ap, res); b.notificar_resultados(ap, tg)
check(ap.get(b.chave_sinal("E Eps","F Fi","2026-11-20"))["status"] == "anulada" and "anulada" in tg.texts()[-1], "anulada")
check(len(tg.sent) == 4, "4 msgs")

# ---------- 3. reinício: sem duplicar
ap2 = b.Apostas(b.APOSTAS_FILE)
check(b.notificar_resultados(ap2, tg) == 0 and b.resolver_apostas(ap2, res) == 0, "restart no dup")
b.processar_entrada("2026-11-20|08:55", hist, sinais, b.CacheSet(b.ENTRADAS_FILE), tg, fx, ap2)
check(len(tg.sent) == 4 and len(ap2.itens) == 3, "entrada não reenviada")

# ---------- 4. falha de envio → tenta de novo
at(2026,11,20,16,55,3)
par_verde(hist, "G Gi", "H Ha", K(16, 0))
b.processar_entrada("2026-11-20|16:55", hist, sinais, entradas, tg, [b.OddsMatch("G Gi","H Ha",1.50,2.50,False,None,K(17,0))], ap2)
at(2026,11,20,17,30); b.resolver_apostas(ap2, [R("H Ha","G Gi",1,3,K(17,0),"9")])
bad = FakeTG(ok=False); check(b.notificar_resultados(ap2, bad) == 0, "falhou")
check(b.notificar_resultados(b.Apostas(b.APOSTAS_FILE), tg) == 1 and "GREEN" in tg.texts()[-1], "reenviou após falha")

# ---------- 5. entrada ao vivo + resolução pela página ao vivo
at(2026,11,20,21,10)
par_verde(hist, "I Io", "J Jo", K(20, 0))
ap3 = b.Apostas(b.APOSTAS_FILE)
b.processar([b.LiveMatch("J Jo","I Io",None,None,None,False,K(21,30))], hist, b.CacheSet(b.FINISHED_FILE), sinais, tg, "R2",
            [b.OddsMatch("J Jo","I Io",2.50,1.50,False,None,K(21,30))], ap3)
a = ap3.get(b.chave_sinal("I Io","J Jo","2026-11-20"))
check(a and a["origem"] == "ao_vivo" and a["bloco"] == "21" and a["pick"] == "I Io", a)
at(2026,11,20,21,30); b.resolver_apostas(ap3, [R("J Jo","I Io",3,0,None,"live")]); b.notificar_resultados(ap3, tg)
check("RED" in tg.texts()[-1] and "J Jo 3-0 I Io" in tg.texts()[-1], tg.texts()[-1])

# ---------- 6/7. agenda: saudações e resumo
ev = b.CacheSet(b.EVENTOS_FILE); tg2 = FakeTG()
def run(h, m, d=21):
    at(2026,11,d,h,m); return b.tarefas_agendadas(tg2, ap3, ev)
check(run(7,49) == [] and run(7,50) == ["bomdia"] and run(7,55) == [] , "bom dia 1x")
check(run(8,21) == [] and run(12,40) == ["boatarde"] and run(12,41) == [], "boa tarde")
check(run(22,29) == [] , "antes do resumo")
at(2026,11,20,22,30)
tg3 = FakeTG(); ev20 = b.CacheSet(b.EVENTOS_FILE)
check(b.tarefas_agendadas(tg3, ap3, ev20) == ["resumo"], "resumo 22:30")
resumo = tg3.texts()[0]
check("Resumo do dia 20/11" in resumo and "2 ✅ / 2 ❌ — 50%" in resumo and "Anuladas: 1" in resumo and "09h: 1 ✅ / 1 ❌" in resumo
      and "17h: 1 ✅" in resumo and "21h: 0 ✅ / 1 ❌" in resumo and "No mês" in resumo and "+18" in resumo, resumo)
at(2026,11,20,22,35)
check(b.tarefas_agendadas(tg3, ap3, b.CacheSet(b.EVENTOS_FILE)) == ["boanoite"], "boa noite depois do resumo (após restart)")
check(b.tarefas_agendadas(tg3, ap3, b.CacheSet(b.EVENTOS_FILE)) == [], "sem duplicar")
# boa noite não sai antes do resumo
ev_x = b.CacheSet(b.EVENTOS_FILE); 
at(2026,11,22,22,36); tg4 = FakeTG(); b.tarefas_agendadas(tg4, ap3, ev_x)
check(tg4.texts()[0].startswith("📊") and "Boa noite" in tg4.texts()[1], "ordem resumo→boa noite")
for _, h, m in b.AGENDA_SAUDACOES:
    check(not (m <= 55 <= m + b.JANELA_SAUDACAO_MIN and h in b.HORAS_ENTRADA), "sem colisão com :55")
check(len(b.FRASES) >= 40 and len(set(b.FRASES)) == len(b.FRASES), "40+ frases")

# ---------- 8. comandos
at(2026,11,20,22,40)
conv = b.Conversa("filtrobot", "999")
def upd(text, chat="-100999", uid="222", name="João Silva", **extra):
    m = {"message_id": 7, "chat": {"id": int(chat), "type": "supergroup" if chat.startswith("-") else "private"},
         "from": {"id": int(uid), "first_name": name, "is_bot": False}, "text": text}; m.update(extra)
    return {"update_id": 1, "message": m}
tg5 = FakeTG()
for c in ["/placar", "/semana", "/mes", "/entradas", "/ajuda", "/id", "/placar@filtrobot"]:
    check(b.tratar_update(upd(c), tg5, hist, ap3, conv) == "comando", c)
check(len(tg5.sent) == 7 and all(s[0] == "-100999" and s[2] == 7 for s in tg5.sent), "respostas no grupo")
check("Placar de hoje" in tg5.texts()[0] and "Placar da semana" in tg5.texts()[1] and "Placar do mês" in tg5.texts()[2], "placares")
check("Entradas de hoje" in tg5.texts()[3] and "✅" in tg5.texts()[3], tg5.texts()[3])
check("-100999" in tg5.texts()[5], "/id")
check(b.tratar_update(upd("/placar@outrobot"), tg5, hist, ap3, conv) is None, "outro bot")
n0 = len(tg5.sent)
b.tratar_update(upd("/zerar"), tg5, hist, ap3, conv)
check("só para o admin" in tg5.texts()[-1] and len(hist.data) > 0, "zerar bloqueado")
b.tratar_update(upd("/zerar", chat="111", uid="111"), tg5, hist, ap3, conv)
check(tg5.sent[-1][0] == "111" and len(hist.data) == 0, "zerar pelo dono")
check(b.tratar_update(upd("/placar", chat="-100555"), tg5, hist, ap3, conv) is None, "chat estranho ignorado")
check(b.tratar_update(upd("/id", chat="-100555"), tg5, hist, ap3, conv) == "comando" and "-100555" in tg5.texts()[-1], "/id em qualquer chat")

# ---------- 9. conversa
tg6 = FakeTG()
at(2026,11,21,9,5)
check(b.tratar_update(upd("Bom dia pessoal!"), tg6, hist, ap3, conv) == "conversa" and tg6.texts()[-1].startswith("Bom dia, João!"), tg6.texts())
check(b.tratar_update(upd("bom dia de novo"), tg6, hist, ap3, conv) is None, "rate limit")
check(b.tratar_update(upd("bom dia", uid="333", name="Ana"), tg6, hist, ap3, conv) == "conversa" and "Ana" in tg6.texts()[-1], "outro usuário")
at(2026,11,21,14,0)
check(b.tratar_update(upd("boa tarde"), tg6, hist, ap3, conv) == "conversa" and tg6.texts()[-1].startswith("Boa tarde, João"), "tarde")
at(2026,11,21,21,0)
check(b.tratar_update(upd("oi"), tg6, hist, ap3, conv) == "conversa" and tg6.texts()[-1].startswith("Boa noite"), "oi à noite")
check(b.tratar_update(upd("valeu!"), tg6, hist, ap3, conv) == "conversa" and "Tamo junto, João" in tg6.texts()[-1], "obrigado")
check(b.tratar_update(upd("@FiltroBot qual o placar?"), tg6, hist, ap3, conv) == "conversa" and "Placar" in tg6.texts()[-1], "menção placar")
check(b.tratar_update(upd("@filtrobot e aí, tudo certo?", uid="444", name="Rui"), tg6, hist, ap3, conv) == "conversa", "menção + saudação")
check(b.tratar_update(upd("alguém viu o jogo ontem? foi muito bom mesmo"), tg6, hist, ap3, conv) is None, "conversa normal ignorada")
check(b.tratar_update(upd("bom dia", chat="-100555", uid="555"), tg6, hist, ap3, conv) is None, "outro grupo ignorado")
check(b.tratar_update(upd("<script>", uid="666", name="<b>X</b>", reply_to_message={"from": {"id": 999}}), tg6, hist, ap3, conv) == "conversa"
      and "<b>X" not in tg6.texts()[-1], "menção por reply + escape")

# ---------- 10/11. bot adicionado / boas-vindas
tg7 = FakeTG()
u = {"update_id": 2, "my_chat_member": {"chat": {"id": -100777, "title": "Meu Grupo", "type": "supergroup"},
     "new_chat_member": {"status": "administrator"}}}
check(b.tratar_update(u, tg7, hist, ap3, conv) == "grupo_adicionado" and tg7.sent[0][0] == "111" and "-100777" in tg7.texts()[0], "id do grupo ao dono")
check(b.tratar_update(upd("", new_chat_members=[{"first_name": "Maria", "is_bot": False}]), tg7, hist, ap3, conv) == "boas_vindas", "boas-vindas")

# ---------- persisted file content
data = json.loads(open(b.APOSTAS_FILE).read())
check({"dia","bloco","home","away","pick","status","placar"} <= set(data[0]), "arquivo de resultados")
print("ALL OK", N, "checks")
print("---- exemplo GREEN ----\n" + t_green + "\n---- resumo ----\n" + resumo)

# ---------- canal privado: /id e bot adicionado
tg8 = FakeTG()
cp = {"update_id": 9, "channel_post": {"message_id": 3, "chat": {"id": -100888, "title": "Canal VIP", "type": "channel"},
      "sender_chat": {"id": -100888}, "text": "/id"}}
check(b.tratar_update(cp, tg8, hist, ap3, conv) == "comando" and tg8.sent[-1][0] == "-100888" and "-100888" in tg8.texts()[-1], "/id em canal")
cp2 = {"update_id": 10, "channel_post": {"message_id": 4, "chat": {"id": -100888, "type": "channel"}, "text": "bom dia"}}
check(b.tratar_update(cp2, tg8, hist, ap3, conv) is None, "canal não conversa")
uc = {"update_id": 11, "my_chat_member": {"chat": {"id": -100888, "title": "Canal VIP", "type": "channel"}, "new_chat_member": {"status": "administrator"}}}
check(b.tratar_update(uc, tg8, hist, ap3, conv) == "grupo_adicionado" and "canal" in tg8.texts()[-1], "canal adicionado")
check(b.tratar_update(upd("/id@filtro_czech_bot", chat="-100321"), tg8, hist, ap3, b.Conversa("filtro_czech_bot", "9")) == "comando", "/id@bot em grupo não configurado")
print("CANAL OK", N)
