"""Regras do filtro depois da auditoria: favorito da 2ª rodada, odds obrigatórias, nomes e horários.

requests é sempre simulado.
"""
import os, sys, tempfile
from datetime import datetime

D = tempfile.mkdtemp()
os.environ.update({
    "DATA_DIR": D,
    "TELEGRAM_TOKEN": "x",
    "TELEGRAM_CHAT_ID": "111",
    "TELEGRAM_GROUP_ID": "-100999",
})
os.environ.pop("MOVIODDS_KEY", None)
os.environ.pop("MOVIODDS_KEY_2", None)
os.environ.pop("TELEGRAM_OWNER_ID", None)
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
import requests

def _blocked(*a, **k):
    raise AssertionError("real HTTP call attempted")

requests.get = requests.post = _blocked
import bot_filtro_blindado_v5 as b

N = 0
def check(c, m):
    global N
    assert c, m
    N += 1

def K(h, m, d=20):
    return b.TZ.localize(datetime(2026, 11, d, h, m))

def at(h, mi, s=0):
    dt = K(h, mi).replace(second=s)
    b.agora_cet = lambda: dt
    return dt

class FakeTG:
    def __init__(self):
        self.sent = []
    def send(self, t, chat_id=None, reply_to=None):
        self.sent.append(t)
        return True

def novo_hist():
    h = b.Historico()
    h.data = {}
    h.save()
    return h

def gravar(h, nome, resultado, odd, inicio, sets_f=3, sets_c=0):
    h.set_resultado(nome, resultado, sets_f, sets_c, odd, inicio=inicio)

def jogo(home, away, oh, oa, hora, minuto, in_play=False):
    return b.OddsMatch(home, away, oh, oa, in_play, None, K(hora, minuto) if hora is not None else None)

def avaliar(h, match):
    return b.avaliar(match, h, b.montar_odds_map([match] if match.odd_home or match.odd_away else []))

check(b.ODD_MAX_FAVORITO == 1.65, b.ODD_MAX_FAVORITO)
check(b.ODDS_CACHE_TTL_S == 20 * 60, b.ODDS_CACHE_TTL_S)
check(b.HORAS_ENTRADA == (8, 12, 16, 20), b.HORAS_ENTRADA)

# ---------- favorito só pela odd da 2ª rodada ----------
# R2: Petr 1.50 x Jan 2.50. R1 gravou Jan 1.30 e Petr 1.60 (outros adversários).
# O código antigo promovia Jan. Agora o favorito é Petr, que perdeu: não sinaliza Jan.
at(8, 55)
h = novo_hist()
gravar(h, "Jan", "limpo", 1.30, K(8, 0), 3, 0)
gravar(h, "Petr", "derrota", 1.60, K(8, 30), 0, 3)
status, motivos, fav = avaliar(h, jogo("Petr", "Jan", 1.50, 2.50, 9, 0))
check(status == "bloqueado" and fav is None, (status, motivos, fav))
check(any("Inversão" in m and "Petr" in m for m in motivos), motivos)
check(all("Jan" not in m for m in motivos), motivos)

# ---------- sem odds de mercado não há entrada ----------
gravar(h, "Petr", "limpo", None, K(8, 0), 3, 1)
gravar(h, "Jan", "derrota", None, K(8, 0), 1, 3)
status, motivos, fav = avaliar(h, jogo("Petr", "Jan", None, None, 9, 0))
check(status == "bloqueado" and motivos == ["sem odds de mercado"] and fav is None, (status, motivos, fav))

# ---------- cache acima de 20 min conta como sem odds ----------
cache = b.CacheOdds()
cache.lista = [jogo("Petr", "Jan", 1.50, 2.50, 9, 0)]
cache.quando = 50_000.0
cliente = b.MoviOdds("")
no_limite = b.obter_odds(cliente, cache, now=K(10, 5), agora_ts=50_000.0 + 20 * 60)
check(no_limite is cache.lista and len(no_limite) == 1, "20 min ainda vale")
vencido = b.obter_odds(cliente, cache, now=K(10, 6), agora_ts=50_000.0 + 20 * 60 + 1)
check(vencido == [] and cache.lista is not vencido and cache.quando == 50_000.0, vencido)
status, motivos, fav = b.avaliar(jogo("Petr", "Jan", 1.50, 2.50, 9, 0), h, b.montar_odds_map(vencido))
check(status == "bloqueado" and motivos == ["sem odds de mercado"] and fav is None, (status, motivos, fav))

# ---------- 1.80/2.00 não é favorito claro; 1.65 é ----------
gravar(h, "Petr", "limpo", 1.40, K(8, 0), 3, 0)
gravar(h, "Jan", "derrota", 2.10, K(8, 0), 0, 3)
status, motivos, fav = avaliar(h, jogo("Petr", "Jan", 1.80, 2.00, 9, 0))
check(status == "bloqueado" and fav is None and any("50/50" in m for m in motivos), (status, motivos, fav))
status, motivos, fav = avaliar(h, jogo("Petr", "Jan", 1.65, 2.20, 9, 0))
check(status == "verde" and fav == "Petr", (status, motivos, fav))

# ---------- 1.50/2.50 limpo contra derrota é verde, mesmo com odd da 1ª invertida ----------
gravar(h, "Petr", "limpo", 1.60, K(8, 0), 3, 1)
gravar(h, "Jan", "derrota", 1.30, K(8, 30), 1, 3)
status, motivos, fav = avaliar(h, jogo("Petr", "Jan", 1.50, 2.50, 9, 30))
check(status == "verde" and fav == "Petr", (status, motivos, fav))
check(any("odd 1.50" in m for m in motivos), motivos)

# ---------- favorito que veio de 3-2 continua bloqueado ----------
gravar(h, "Petr", "desgaste", 1.20, K(8, 0), 3, 2)
gravar(h, "Jan", "derrota", 1.90, K(8, 0), 2, 3)
status, motivos, fav = avaliar(h, jogo("Petr", "Jan", 1.50, 2.50, 9, 0))
check(status == "bloqueado" and fav is None and any("3-2" in m for m in motivos), (status, motivos, fav))

# vencedor x vencedor e perdedor x perdedor não mudam
gravar(h, "Petr", "limpo", 1.20, K(8, 0), 3, 0)
gravar(h, "Jan", "limpo", 1.20, K(8, 0), 3, 1)
status, motivos, fav = avaliar(h, jogo("Petr", "Jan", 1.50, 2.50, 9, 0))
check(status == "bloqueado" and any("Vencedores" in m for m in motivos), motivos)
gravar(h, "Petr", "derrota", 1.20, K(8, 0), 1, 3)
gravar(h, "Jan", "derrota", 1.20, K(8, 0), 0, 3)
status, motivos, fav = avaliar(h, jogo("Petr", "Jan", 1.50, 2.50, 9, 0))
check(status == "bloqueado" and any("Perdedores" in m for m in motivos), motivos)

# ---------- nome: sem substring ----------
h = novo_hist()
gravar(h, "Jan Novak", "limpo", 1.40, K(8, 0), 3, 0)
check(h.get("Novak") is None, "Novak não é Jan Novak")
check(h.get("Jan Novakova") is None, "Jan Novakova não é Jan Novak")
check(h.get("Jan Novak")["resultado"] == "limpo", "nome exato")
check(h.get("novak jan")["resultado"] == "limpo", "mesmo jogador normalizado")
gravar(h, "Petr Hora", "derrota", 2.00, K(8, 0), 0, 3)
status, motivos, fav = b.avaliar(
    jogo("Novak", "Petr Hora", 1.50, 2.50, 9, 0), h,
    b.montar_odds_map([jogo("Novak", "Petr Hora", 1.50, 2.50, 9, 0)]),
)
check(status == "indefinido", (status, motivos))

# ---------- jogo sem horário não é 2ª rodada ----------
slot = "2026-11-20|08:55"
com = jogo("A Alfa", "B Beta", 1.50, 2.50, 9, 0)
sem = jogo("C Gama", "D Delta", 1.50, 2.50, None, None)
fora = jogo("E Eps", "F Fi", 1.50, 2.50, 10, 0)
ao_vivo = b.OddsMatch("G Gi", "H Ha", 1.50, 2.50, True, None, K(9, 0))
nomes = [o.home for o in b.confrontos_rodada2([sem, fora, ao_vivo, com], slot)]
check(nomes == ["A Alfa"], nomes)

# ---------- 1ª rodada fora de hh:00–hh:50 do ciclo não entra ----------
h = novo_hist()
gravar(h, "Petr", "limpo", 1.40, K(7, 30), 3, 0)
gravar(h, "Jan", "derrota", 2.00, K(8, 0), 1, 3)
status, motivos, fav = avaliar(h, jogo("Petr", "Jan", 1.50, 2.50, 9, 0))
check(status == "bloqueado" and fav is None and any("hh:00" in m for m in motivos), (status, motivos))
gravar(h, "Petr", "limpo", 1.40, K(8, 50), 3, 0)
status, motivos, fav = avaliar(h, jogo("Petr", "Jan", 1.50, 2.50, 9, 0))
check(status == "verde" and fav == "Petr", (status, motivos, fav))

# ---------- ao vivo: grava R1 só na janela; entrada só pré-jogo da 2ª ----------
at(8, 40)
h = novo_hist()
fin = b.CacheSet(b.FINISHED_FILE)
sinais = b.CacheSet(b.ENVIADOS_FILE)
ap = b.Apostas(b.APOSTAS_FILE)
tg = FakeTG()
b.processar([
    b.LiveMatch("A Alfa", "B Beta", 3, 1, "S4", True, K(8, 30)),
    b.LiveMatch("C Gama", "D Delta", 3, 0, "S3", True, None),
    b.LiveMatch("E Eps", "F Fi", 3, 0, "S3", True, K(7, 0)),
], h, fin, sinais, tg, "R1", [], ap)
check(h.get("A Alfa")["resultado"] == "limpo" and h.get("B Beta")["resultado"] == "derrota", h.data)
check(h.get("A Alfa")["inicio"].startswith("2026-11-20T08:30:00"), h.get("A Alfa"))
check(h.get("C Gama") is None and h.get("E Eps") is None, h.data)
check(tg.sent == [], tg.sent)

at(9, 10)
gravar(h, "Petr", "limpo", 1.60, K(8, 0), 3, 0)
gravar(h, "Jan", "derrota", 1.30, K(8, 30), 1, 3)
ap = b.Apostas(b.APOSTAS_FILE)
antes = len(ap.itens)
futuro = b.LiveMatch("Petr", "Jan", None, None, None, False, K(9, 30))
comecou = b.LiveMatch("A Alfa", "B Beta", 0, 1, "S2", False, K(9, 0))
sem_hora = b.LiveMatch("C Gama", "D Delta", None, None, None, False, None)
odds = [
    jogo("Petr", "Jan", 1.50, 2.50, 9, 30),
    jogo("A Alfa", "B Beta", 1.40, 2.80, 9, 0),
    b.OddsMatch("C Gama", "D Delta", 1.40, 2.60, True, None, K(9, 30)),
]
b.processar([futuro, comecou, sem_hora, b.LiveMatch("C Gama", "D Delta", None, None, None, False, K(9, 30))],
            h, fin, sinais, tg, "R2", odds, ap)
check(len(ap.itens) == antes + 1, ap.itens)
entrada = ap.get(b.chave_sinal("Petr", "Jan", "2026-11-20"))
check(entrada and entrada["pick"] == "Petr" and entrada["origem"] == "ao_vivo", entrada)
check(ap.get(b.chave_sinal("A Alfa", "B Beta", "2026-11-20")) is None, "jogo já iniciado")
check(ap.get(b.chave_sinal("C Gama", "D Delta", "2026-11-20")) is None, "sem hora ou odd ao vivo")

# ---------- primeira consulta do dia é 07:48, antes do jogo das 08:00 ----------
slots = []
for hora in range(24):
    for minuto in range(60):
        quando = b.TZ.localize(datetime(2026, 11, 20, hora, minuto))
        if b.slot_moviodds_atual(quando):
            slots.append((hora, minuto))
check(slots[0] == (7, 48), slots[0])
check(all(hora > 7 or (hora == 7 and minuto >= 48) for hora, minuto in slots), slots[:3])
check(b.slot_moviodds_atual(b.TZ.localize(datetime(2026, 11, 20, 7, 47))) is None, "07:47 fora")
check(b.slot_moviodds_atual(b.TZ.localize(datetime(2026, 11, 20, 7, 48))) == "2026-11-20|07:48", "07:48")

print("FILTRO OK", N, "checks")
