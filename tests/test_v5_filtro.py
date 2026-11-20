"""Regras do filtro depois da auditoria: favorito da 2ª rodada, odds obrigatórias, nomes e horários.

requests é sempre simulado.
"""
import os, re, sys, tempfile
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
# Jan aparece só como resultado da 1ª rodada, nunca como favorito.
check(all("favorito Jan" not in m and "favorito (Jan" not in m for m in motivos), motivos)

# ---------- sem odds de mercado não há entrada ----------
gravar(h, "Petr", "limpo", None, K(8, 0), 3, 1)
gravar(h, "Jan", "derrota", None, K(8, 0), 1, 3)
status, motivos, fav = avaliar(h, jogo("Petr", "Jan", None, None, 9, 0))
check(status == "bloqueado" and fav is None and any(m.startswith("sem odds de mercado") for m in motivos), (status, motivos, fav))

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
check(status == "bloqueado" and fav is None and any(m.startswith("sem odds de mercado") for m in motivos), (status, motivos, fav))

# ---------- 1.80/2.00 não é favorito claro; 1.65 é ----------
gravar(h, "Petr", "limpo", 1.40, K(8, 0), 3, 0)
gravar(h, "Jan", "derrota", 2.10, K(8, 0), 0, 3)
status, motivos, fav = avaliar(h, jogo("Petr", "Jan", 1.80, 2.00, 9, 0))
check(status == "bloqueado" and fav is None and any(
    "sem favorito claro" in m and "1.80" in m and "2.00" in m for m in motivos), (status, motivos, fav))
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

# ---------- motivos com placar, odds e jogos que ficaram de fora ----------
def tlen(s):
    return len(s.encode("utf-16-le")) // 2

at(8, 55)
h = novo_hist()
gravar(h, "Jan Novak", "limpo", 1.40, K(8, 0), 3, 1)
gravar(h, "Petr Svoboda", "limpo", 1.30, K(8, 10), 3, 0)
status, motivos, fav = avaliar(h, jogo("Jan Novak", "Petr Svoboda", 1.50, 2.20, 9, 10))
check(status == "bloqueado" and fav is None, (status, motivos, fav))
junto = " ".join(motivos)
check("Duelo de Vencedores (Regra 2)" in junto, junto)
check("Jan venceu 3-1" in junto and "Petr venceu 3-0" in junto, junto)

gravar(h, "Petr Svoboda", "derrota", None, K(8, 10), 0, 3)
gravar(h, "Jan Novak", "limpo", None, K(8, 0), 3, 1)
status, motivos, fav = avaliar(h, jogo("Jan Novak", "Petr Svoboda", None, None, 9, 10))
check(status == "bloqueado" and fav is None, (status, motivos))
check(any(m.startswith("sem odds de mercado") for m in motivos), motivos)
check(any("Jan venceu 3-1" in m and "Petr perdeu 0-3" in m for m in motivos), motivos)

gravar(h, "Petr Svoboda", "limpo", 1.40, K(8, 0), 3, 0)
gravar(h, "Jan Novak", "derrota", 2.10, K(8, 20), 0, 3)
status, motivos, fav = avaliar(h, jogo("Petr Svoboda", "Jan Novak", 1.80, 2.00, 9, 10))
check(status == "bloqueado" and fav is None, (status, motivos, fav))
check(any(
    m.startswith("odds 1.80 x 2.00, sem favorito claro (máx 1.65)")
    and "Petr venceu 3-0" in m and "Jan perdeu 0-3" in m
    for m in motivos
), motivos)
check(any(f"máx {b.ODD_MAX_FAVORITO:.2f}" in m for m in motivos), motivos)

gravar(h, "Petr Svoboda", "derrota", 1.70, K(8, 5), 1, 3)
gravar(h, "Jan Novak", "limpo", 1.30, K(8, 15), 3, 1)
status, motivos, fav = avaliar(h, jogo("Petr Svoboda", "Jan Novak", 1.45, 2.40, 9, 10))
check(status == "bloqueado" and fav is None, (status, motivos, fav))
check(any(
    "Inversão" in m and "favorito Petr (1.45) perdeu 1-3 na 1ª" in m and "Jan venceu 3-1" in m
    for m in motivos
), motivos)
check(all("favorito Jan" not in m for m in motivos), motivos)

gravar(h, "Petr Svoboda", "limpo", 1.40, K(8, 0), 3, 1)
gravar(h, "Jan Novak", "derrota", 2.20, K(8, 25), 1, 3)
status, motivos, fav = avaliar(h, jogo("Petr Svoboda", "Jan Novak", 1.50, 2.50, 9, 10))
check(status == "verde" and fav == "Petr Svoboda", (status, fav, motivos))
check(any(m.startswith("✓ Favorito:") and "odd 1.50" in m and "Petr Svoboda" in m for m in motivos), motivos)
check(any("✓ Vitória limpa na 1ª rodada (Petr venceu 3-1)" == m for m in motivos), motivos)
check(any("✓ Adversário veio de derrota (Jan perdeu 1-3)" == m for m in motivos), motivos)
check(any("✓ Odds: Petr Svoboda 1.50 x Jan Novak 2.50" == m for m in motivos), motivos)
check(any(m.startswith("✓ ") for m in motivos), motivos)

# mensagem hh:55: verdes e, em seguida, cada jogo que não entrou
h = novo_hist()
gravar(h, "Petr Svoboda", "limpo", 1.40, K(8, 0), 3, 1)
gravar(h, "Jan Novak", "derrota", 2.20, K(8, 25), 1, 3)
gravar(h, "Ivan Hora", "limpo", 1.20, K(8, 5), 3, 1)
gravar(h, "Adam Kral", "limpo", 1.20, K(8, 15), 3, 0)
gravar(h, "Lukas Maly", "derrota", 1.80, K(8, 20), 1, 3)
gravar(h, "Com Historico", "limpo", 1.40, K(8, 30), 3, 0)
slot = "2026-11-20|08:55"
verde = jogo("Petr Svoboda", "Jan Novak", 1.50, 2.50, 9, 0)
vencedores = jogo("Ivan Hora", "Adam Kral", 1.40, 2.60, 9, 10)
sem_odd = jogo("Lukas Maly", "Com Historico", None, None, 9, 20)
indef = jogo("Sem & Placar", "Com Historico", 1.55, 2.30, 9, 30)
especial = jogo("Tom & Jerry", "A < B", 1.70, 2.10, 9, 40)
gravar(h, "Tom & Jerry", "limpo", 1.20, K(8, 40), 3, 0)
gravar(h, "A < B", "limpo", 1.20, K(8, 42), 3, 1)
partes, verdes_msg, defs = b.montar_mensagem_entrada(
    slot, [verde, vencedores, sem_odd, indef, especial], h,
    [verde, vencedores, sem_odd, indef, especial],
)
check(len(partes) == 1 and all(tlen(p) <= b.TG_LIMITE for p in partes), [tlen(p) for p in partes])
msg = partes[0]
check("<b>SINAL VERDE</b>" in msg and "Petr Svoboda" in msg and "odd 1.50" in msg, msg)
check(msg.index("<b>SINAL VERDE</b>") < msg.index("<b>Sem entrada</b>"), msg)
check("❌ <b>Ivan Hora</b> vs <b>Adam Kral</b> (09:10) — Duelo de Vencedores (Regra 2): Ivan venceu 3-1, Adam venceu 3-0" in msg, msg)
check("sem odds de mercado" in msg and "Lukas perdeu 1-3" in msg, msg)
check("⏳ <b>Sem &amp; Placar</b> vs <b>Com Historico</b> (09:30) — sem placar da 1ª rodada de Sem &amp; Placar" in msg, msg)
check("Tom &amp; Jerry" in msg and "A &lt; B" in msg, msg)
check("Tom & Jerry" not in msg and "A < B" not in msg, msg)
check("… e mais" not in msg, msg)
check(any(o.home == "Ivan Hora" for o in defs) and any(o.home == "Sem & Placar" for o in defs) is False, defs)
check(len(verdes_msg) == 1 and verdes_msg[0][1] == "Petr Svoboda", verdes_msg)

# ao vivo: o verde usa os mesmos motivos; bloqueado não gera mensagem
at(9, 10)
tg = FakeTG()
sinais = b.CacheSet(b.ENVIADOS_FILE)
b.processar(
    [
        b.LiveMatch("Jan Novak", "Petr Svoboda", None, None, None, False, K(9, 20)),
        b.LiveMatch("Ivan Hora", "Adam Kral", None, None, None, False, K(9, 30)),
    ],
    h, b.CacheSet(b.FINISHED_FILE), sinais, tg, "R2",
    [
        jogo("Jan Novak", "Petr Svoboda", 2.50, 1.50, 9, 20),
        jogo("Ivan Hora", "Adam Kral", 1.40, 2.60, 9, 30),
    ],
)
check(len(tg.sent) == 1, tg.sent)
ao_vivo = tg.sent[0]
check("SINAL VERDE" in ao_vivo and "Petr venceu 3-1" in ao_vivo and "Jan perdeu 1-3" in ao_vivo, ao_vivo)
check("✓ Odds: Jan Novak 2.50 x Petr Svoboda 1.50" in ao_vivo, ao_vivo)
check("Ivan Hora" not in ao_vivo and "Duelo de Vencedores" not in ao_vivo, ao_vivo)
check("Jan Novak" in ao_vivo and "<b>Jan Novak</b>" in ao_vivo, ao_vivo)

# sem nenhum verde, a mensagem lista cada jogo em vez de só o resumo
so_fora = [vencedores, indef]
partes_fora, verdes_fora, _ = b.montar_mensagem_entrada(slot, so_fora, h, so_fora)
check(verdes_fora == [] and len(partes_fora) == 1, partes_fora)
fora = partes_fora[0]
check("Nenhuma entrada verde (2 confrontos avaliados)." in fora, fora)
check("❌ <b>Ivan Hora</b> vs <b>Adam Kral</b> (09:10)" in fora, fora)
check("⏳ <b>Sem &amp; Placar</b> vs <b>Com Historico</b> (09:30) — sem placar da 1ª rodada de Sem &amp; Placar" in fora, fora)
check("<b>SINAL VERDE</b>" not in fora, fora)

# mensagem longa: cada envio cabe no Telegram e o corte diz quantos jogos faltam
at(12, 55)
h = novo_hist()
gravar(h, "Verde Bom", "limpo", 1.40, K(12, 5), 3, 0)
gravar(h, "Verde Ruim", "derrota", 2.10, K(12, 15), 0, 3)
gravar(h, "Tom & Jerry", "limpo", 1.20, K(12, 0), 3, 0)
gravar(h, "A < B", "limpo", 1.20, K(12, 0), 3, 1)
gravar(h, "Com Historico", "derrota", 1.80, K(12, 20), 0, 3)
lista = [
    jogo("Verde Bom", "Verde Ruim", 1.40, 2.60, 13, 0),
    jogo("Tom & Jerry", "A < B", 1.70, 2.10, 13, 1),
    jogo("Sem & Placar", "Com Historico", 1.55, 2.30, 13, 2),
]
total_fora = 2
for i in range(45):
    a = f"Aaa{i:02d} " + ("X" * 70)
    c = f"Bbb{i:02d} " + ("Y" * 70)
    gravar(h, a, "limpo", 1.2, K(12, 0), 3, 1)
    gravar(h, c, "limpo", 1.2, K(12, 0), 3, 0)
    lista.append(jogo(a, c, 1.50, 2.40, 13, 10 + (i % 40)))
    total_fora += 1
slot = "2026-11-20|12:55"
tg = FakeTG()
ok = b.processar_entrada(slot, h, b.CacheSet(b.ENVIADOS_FILE), b.CacheSet(b.ENTRADAS_FILE), tg, lista, None)
check(ok and tg.sent, "envio da entrada longa")
check(all(0 < tlen(t) <= b.TG_LIMITE for t in tg.sent), [tlen(t) for t in tg.sent])
junto = "\n".join(tg.sent)
omitidos = sum(int(n) for n in re.findall(r"… e mais (\d+) jogos", junto))
listados = junto.count("❌") + junto.count("⏳")
check(listados + omitidos == total_fora, (listados, omitidos, total_fora))
check("… e mais" in junto or len(tg.sent) > 1, "passou de 4096 e foi cortada ou dividida")
check(junto.count("🚨") == 1 and "Verde Bom" in junto and "Verde Ruim" in junto, junto[:500])
check("Tom &amp; Jerry" in junto and "A &lt; B" in junto, junto)
check("Tom & Jerry" not in junto and "<b>A < B</b>" not in junto, "escape HTML")
check("sem placar da 1ª rodada de Sem &amp; Placar" in junto, junto)
check("Duelo de Vencedores (Regra 2)" in junto and "venceu 3-1" in junto, "motivos na lista de fora")

print("FILTRO OK", N, "checks")
