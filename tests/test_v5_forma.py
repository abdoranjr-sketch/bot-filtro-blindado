"""Score de forma, triangulação, fadiga, horário anterior e decisão.

requests é sempre simulado. A grade do MoviOdds continua em 160 consultas/dia.
"""
import os, sys, tempfile
from datetime import datetime, timedelta

D = tempfile.mkdtemp()
os.environ.update({
    "DATA_DIR": D,
    "TELEGRAM_TOKEN": "x",
    "TELEGRAM_CHAT_ID": "111",
    "TELEGRAM_GROUP_ID": "-100999",
})
os.environ.pop("MOVIODDS_KEY", None)
os.environ.pop("MOVIODDS_KEY_2", None)
os.environ.pop("SPORTSAPI365_KEY", None)
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

def K(h, m, d=20, s=0):
    return b.TZ.localize(datetime(2026, 11, d, h, m, s))

AGORA = K(9, 0)
b.agora_cet = lambda: AGORA

def partida(sf, sc, hora, minuto, adv="", dia=20, fim=None):
    ini = K(hora, minuto, dia)
    return {
        "sets_favor": sf, "sets_contra": sc, "inicio": ini, "adversario": adv,
        "fim": fim if fim is not None else b.estimar_fim(ini, sf, sc),
        "resultado": b.classificar(sf, sc),
    }

def fj(nome, partidas, agora=AGORA):
    return b.metricas_forma(nome, partidas, agora)

def decidir(a, jogador_b, oa=1.50, ob=2.40, agora=AGORA, aa=False, ab=False):
    return b.decidir_entrada(a, jogador_b, oa, ob, agora, aa, ab)

# ---------- a grade de 160 não muda ----------
check(b.MOVIODDS_CHAMADAS_DIA == 160, b.MOVIODDS_CHAMADAS_DIA)
check(b.MOVIODDS_CHAMADAS_MES_31 == 4960, b.MOVIODDS_CHAMADAS_MES_31)
check(len(b.MOVIODDS_MINUTOS_ODDS) == 96, len(b.MOVIODDS_MINUTOS_ODDS))
check(len(b.MOVIODDS_MINUTOS_RESULTADOS) == 64, len(b.MOVIODDS_MINUTOS_RESULTADOS))
check(b.ODD_MIN_ALVO == 1.25 and b.ODD_MAX_ALVO == 1.85, (b.ODD_MIN_ALVO, b.ODD_MAX_ALVO))
check(b.ODDS_CACHE_TTL_S == 20 * 60, b.ODDS_CACHE_TTL_S)
check(all(m not in (5, 20, 50) for _, m in b.MOVIODDS_MINUTOS_RESULTADOS), "sem cron de 5 min")
check(not any(m in (20, 50) and k == "odds" for h, m, k in b.agenda_moviodds()), "sem varredura :20/:50")

# ---------- pesos e janela dos últimos 2–3 em 4 h ----------
check(b.peso_sets(3, 0) == 3.0 and b.peso_sets(3, 1) == 2.0 and b.peso_sets(3, 2) == 0.5, "vitórias")
check(b.peso_sets(2, 3) == -0.5 and b.peso_sets(1, 3) == -2.0 and b.peso_sets(0, 3) == -3.0, "derrotas")

quatro = [partida(3, 0, 6, 20), partida(3, 0, 7, 0), partida(3, 0, 7, 40), partida(3, 1, 8, 20)]
m = fj("Petr", quatro)
check(m.score_forma == 8.0, m.score_forma)  # 3-0 antigo sai; ficam 3+3+2
check(m.jogos_hoje == 4, m.jogos_hoje)
check(m.vitorias_limpas_seguidas == 3, m.vitorias_limpas_seguidas)

so_um = fj("Petr", [partida(3, 0, 8, 0)])
check(so_um.score_forma == 3.0 and so_um.jogos_hoje == 1 and so_um.vitorias_limpas_seguidas == 1, so_um)

# fim há 3h30 entra no score (4 h) e não em jogos_hoje (3 h)
velho = partida(3, 0, 5, 20, fim=AGORA - timedelta(hours=3, minutes=30))
meio = fj("Petr", [velho])
check(meio.score_forma == 3.0 and meio.jogos_hoje == 0, (meio.score_forma, meio.jogos_hoje))
no_limite = partida(3, 1, 6, 0, fim=AGORA - timedelta(hours=3))
lim = fj("Petr", [no_limite])
check(lim.jogos_hoje == 1 and lim.score_forma == 2.0, (lim.jogos_hoje, lim.score_forma))
fora = partida(0, 3, 4, 0, fim=AGORA - timedelta(hours=4, seconds=1))
check(fj("Petr", [fora]).score_forma == 0.0 and fj("Petr", [fora]).jogos_hoje == 0, "fora de 4 h")
exato4 = partida(0, 3, 5, 0, fim=AGORA - timedelta(hours=4))
check(fj("Petr", [exato4]).score_forma == -3.0, "4 h inclusive")

# sequência quebra em 3-2 e em derrota; o 4º jogo não entra na sequência
quebra = fj("Petr", [partida(3, 0, 7, 0), partida(3, 1, 7, 40), partida(3, 2, 8, 20)])
check(quebra.vitorias_limpas_seguidas == 0 and quebra.score_forma == 5.5, (quebra.vitorias_limpas_seguidas, quebra.score_forma))
perda = fj("Petr", [partida(3, 0, 7, 0), partida(3, 1, 7, 30), partida(1, 3, 8, 10)])
check(perda.perdeu_ultimo_jogo and perda.vitorias_limpas_seguidas == 0 and perda.score_forma == 3.0, perda)

# ---------- fadiga: 5 sets há menos de 45 min ----------
def com_fim(sf, sc, minutos):
    fim = AGORA - timedelta(minutes=minutos)
    ini = fim - timedelta(minutes=b.duracao_estimada_min(sf, sc))
    return partida(sf, sc, ini.hour, ini.minute, fim=fim)

check(fj("Petr", [com_fim(3, 2, 44)]).desgaste_ultimo_jogo, "44 min")
check(fj("Petr", [com_fim(2, 3, 10)]).desgaste_ultimo_jogo, "derrota em 5 sets")
check(not fj("Petr", [com_fim(3, 2, 45)]).desgaste_ultimo_jogo, "45 min não entra")
check(not fj("Petr", [com_fim(3, 0, 10)]).desgaste_ultimo_jogo, "3-0 não é fadiga")
# último 3-2 recente: o flag é verdadeiro, mas a decisão pede domínio antes
fad = fj("Petr", [partida(3, 0, 7, 10), partida(3, 1, 7, 40), com_fim(3, 2, 20)])
check(fad.desgaste_ultimo_jogo and fad.vitorias_limpas_seguidas == 0, (fad.desgaste_ultimo_jogo, fad.vitorias_limpas_seguidas))
adv_ruim = fj("Jan", [partida(0, 3, 8, 0)])
d_fad = decidir(fad, adv_ruim)
check(d_fad.status == "bloqueado" and d_fad.motivos == ["PASSAR (Sem domínio comprovado)"], d_fad.motivos)
# o portão de 5 sets existe para o caso em que o domínio já passou
sint = b.FormaJogador("Petr", 5.0, 2, 2, True, False, [])
d_sint = decidir(sint, b.FormaJogador("Jan", -3.0, 1, 0, False, True, []))
check(d_sint.status == "bloqueado" and d_sint.motivos == ["PASSAR (Alvo vem de 5 sets)"], d_sint.motivos)

# ---------- triangulação nas últimas 3 h ----------
def bloco(nome, jogos):
    return fj(nome, jogos)

alvo_c = bloco("Petr", [
    partida(3, 1, 7, 30, "Karel Novak"),
    partida(3, 1, 8, 10, "Outro X"),
])
adv_c = bloco("Jan", [
    partida(0, 3, 7, 40, "Novak Karel"),
    partida(3, 0, 8, 20, "Outro Y"),
])
check(alvo_c.score_forma == 4.0 and adv_c.score_forma == 0.0, (alvo_c.score_forma, adv_c.score_forma))
check(b.bonus_triangulacao(alvo_c, adv_c, AGORA) == 2.0, "3-1 contra 0-3 = +2")
check(b.bonus_triangulacao(adv_c, alvo_c, AGORA) == 0.0, "o bônus não inverte")
d_bonus = decidir(alvo_c, adv_c, 1.45, 2.60)
check(d_bonus.status == "verde" and d_bonus.gap == 6.0 and d_bonus.bonus == 2.0, (d_bonus.status, d_bonus.gap, d_bonus.bonus))
sem = decidir(b.FormaJogador(alvo_c.nome, alvo_c.score_forma, alvo_c.jogos_hoje, alvo_c.vitorias_limpas_seguidas,
                             False, False, []),
              b.FormaJogador(adv_c.nome, adv_c.score_forma, adv_c.jogos_hoje, 0, False, False, []))
check(sem.status == "bloqueado" and sem.motivos == ["PASSAR (Desnível insuficiente)"], sem.motivos)

# +1: 3-0 fora dos 3 do score, adversário foi a 5 sets contra o mesmo C
a_mais = bloco("Petr", [
    partida(3, 0, 6, 20, "Camil"),
    partida(2, 3, 7, 10, "Duda"),
    partida(3, 1, 8, 0, "Ema"),
    partida(3, 1, 8, 20, "Felipe"),
])
b_mais = bloco("Jan", [partida(2, 3, 7, 20, "Camil")])
check(a_mais.score_forma == 3.5 and a_mais.vitorias_limpas_seguidas == 2, (a_mais.score_forma, a_mais.vitorias_limpas_seguidas))
check(b.bonus_triangulacao(a_mais, b_mais, AGORA) == 1.0, b.bonus_triangulacao(a_mais, b_mais, AGORA))
d_mais = decidir(a_mais, b_mais, 1.55, 2.30)
check(d_mais.status == "verde" and d_mais.gap == 5.0 and d_mais.bonus == 1.0, (d_mais.gap, d_mais.bonus, d_mais.status))
# 0-3 e 5 sets no mesmo C não somam +3
b_feio = bloco("Jan", [partida(0, 3, 7, 20, "Camil")])
check(b.bonus_triangulacao(a_mais, b_feio, AGORA) == 2.0, "só o +2")
# fora de 3 h não triangula
antigo = partida(3, 0, 5, 0, "Camil", fim=AGORA - timedelta(hours=3, minutes=5))
a_fora = bloco("Petr", [antigo, partida(3, 1, 8, 10, "Ema"), partida(3, 1, 8, 40, "Felipe")])
check(b.bonus_triangulacao(a_fora, b_feio, AGORA) == 0.0, "C fora de 3 h")
# dois C somam
a2 = bloco("Petr", [partida(3, 0, 7, 20, "Camil"), partida(3, 1, 8, 10, "Duda")])
b2 = bloco("Jan", [partida(1, 3, 7, 30, "Camil"), partida(0, 3, 8, 0, "Duda")])
check(b.bonus_triangulacao(a2, b2, AGORA) == 4.0, b.bonus_triangulacao(a2, b2, AGORA))
# o confronto mais recente contra C é o que vale
a3 = bloco("Petr", [partida(3, 0, 7, 0, "Camil"), partida(1, 3, 8, 20, "Camil")])
b3 = bloco("Jan", [partida(0, 3, 8, 0, "Camil")])
check(b.bonus_triangulacao(a3, b3, AGORA) == 0.0, "o último contra C foi derrota")

# ---------- decisão: ordem do pseudocódigo, alvo pela forma ----------
vazio = b.FormaJogador("Sem", 0.0, 0, 0, False, False, [])
cheio = b.FormaJogador("Petr", 5.0, 2, 2, False, False, [])
ruim = b.FormaJogador("Jan", -3.0, 1, 0, False, True, [])
check(decidir(vazio, ruim).motivos == ["PASSAR (Sem dados do dia)"], "sem dados")
check(decidir(vazio, ruim).status == "indefinido", "sem dados é espera")

# empate de score escolhe B; a odd alta de B reprova antes de olhar o favorito A
emp_a = b.FormaJogador("Casa", 5.0, 2, 2, False, False, [])
emp_b = b.FormaJogador("Fora", 5.0, 2, 2, False, False, [])
emp = decidir(emp_a, emp_b, 1.40, 2.50)
check(emp.motivos == ["PASSAR (Odd fora da faixa: 2.50)"], emp.motivos)

# não é o favorito da casa: A tem forma e odd 1.70; B tem a odd menor e o dia ruim
nao_fav = decidir(cheio, b.FormaJogador("Jan", -6.0, 2, 0, False, True, []), 1.70, 1.40)
check(nao_fav.status == "verde" and nao_fav.alvo == "Petr" and nao_fav.odd == 1.70, nao_fav)
check(nao_fav.gap == 11.0 and nao_fav.score_adv == -6.0, (nao_fav.gap, nao_fav.score_adv))

check(decidir(cheio, ruim, 1.24, 2.40).motivos == ["PASSAR (Odd fora da faixa: 1.24)"], "1.24")
check(decidir(cheio, ruim, 1.86, 2.10).motivos == ["PASSAR (Odd fora da faixa: 1.86)"], "1.86")
ok_min = decidir(cheio, ruim, 1.25, 3.0)
ok_max = decidir(cheio, ruim, 1.85, 1.90)
check(ok_min.status == "verde" and ok_min.odd == 1.25, ok_min)
check(ok_max.status == "verde" and ok_max.gap == 8.0, ok_max)
check(decidir(cheio, ruim, None, 2.0).motivos == ["PASSAR (Sem odds de mercado)"], "sem odd")

sem_dom = b.FormaJogador("Petr", 3.0, 1, 1, False, False, [])
check(decidir(sem_dom, ruim).motivos == ["PASSAR (Sem domínio comprovado)"], "uma limpa")
perdeu = b.FormaJogador("Petr", 1.0, 2, 0, False, True, [])
check(decidir(perdeu, ruim, 1.37, 2.90).motivos == ["PASSAR (Sem domínio comprovado)"], "perdeu o último")

ambos = decidir(cheio, b.FormaJogador("Jan", 4.0, 2, 2, False, False, []), 1.50, 1.60)
check(ambos.motivos == ["PASSAR (Ambos vêm de vitórias)"], ambos.motivos)
# adv com score positivo não entra, mesmo com gap grande
positivo = decidir(cheio, b.FormaJogador("Jan", 0.5, 1, 0, False, False, []))
check(positivo.motivos == ["PASSAR (Desnível insuficiente)"], positivo.motivos)

base = decidir(cheio, ruim, 1.50, 2.50)
check(base.status == "verde" and base.alvo == "Petr" and base.gap == 8.0 and base.bonus == 0.0, base)
check("score_forma 5.0" in base.motivos[0] and "odd 1.50" in base.motivos[0], base.motivos)
check("score_forma -3.0" in base.motivos[1], base.motivos[1])
check("Gap: 8.0" in base.motivos[2] and "bônus triangulação +0.0" in base.motivos[2], base.motivos[2])

# ---------- horário anterior: resultado gravado ou só a grade ----------
def jogo(home, away, oh, oa, hora, minuto, in_play=False):
    return b.OddsMatch(home, away, oh, oa, in_play, None, K(hora, minuto))

hist = b.Historico()
hist.definir_jogos("Petr", [
    {"resultado": "limpo", "sets_favor": 3, "sets_contra": 0, "inicio": K(7, 10), "adversario": "X"},
    {"resultado": "limpo", "sets_favor": 3, "sets_contra": 1, "inicio": K(7, 40), "adversario": "Y"},
])
hist.definir_jogos("Jan", [
    {"resultado": "derrota", "sets_favor": 0, "sets_contra": 3, "inicio": K(7, 20), "adversario": "Z"},
])
alvo_jogo = jogo("Petr", "Jan", 1.50, 2.50, 9, 30)
st, mot, fav = b.avaliar(alvo_jogo, hist, b.montar_odds_map([alvo_jogo]))
check(st == "verde" and fav == "Petr", (st, mot, fav))  # 7:40 → 9:30 tem mais de 45 min

# decisão às 9:25, apito 9:30: o 3-1 das 8:50 já terminou e ainda é horário anterior
b.agora_cet = lambda: K(9, 25)
hist.definir_jogos("Petr", [
    {"resultado": "limpo", "sets_favor": 3, "sets_contra": 0, "inicio": K(8, 0), "adversario": "X"},
    {"resultado": "limpo", "sets_favor": 3, "sets_contra": 1, "inicio": K(8, 50), "adversario": "Y"},
])
st, mot, fav = b.avaliar(jogo("Petr", "Jan", 1.50, 2.50, 9, 30), hist, b.montar_odds_map([jogo("Petr", "Jan", 1.50, 2.50, 9, 30)]))
check(st == "bloqueado" and mot == ["PASSAR (jogou no horário anterior)"] and fav is None, (st, mot))

# 60 min antes não é o horário anterior; 45 min exatos é
hist.definir_jogos("Petr", [
    {"resultado": "limpo", "sets_favor": 3, "sets_contra": 0, "inicio": K(7, 40), "adversario": "X"},
    {"resultado": "limpo", "sets_favor": 3, "sets_contra": 1, "inicio": K(8, 30), "adversario": "Y"},
])
st60, _, _ = b.avaliar(jogo("Petr", "Jan", 1.50, 2.50, 9, 30), hist, b.montar_odds_map([jogo("Petr", "Jan", 1.50, 2.50, 9, 30)]))
check(st60 == "verde", st60)
hist.definir_jogos("Petr", [
    {"resultado": "limpo", "sets_favor": 3, "sets_contra": 0, "inicio": K(7, 20), "adversario": "X"},
    {"resultado": "limpo", "sets_favor": 3, "sets_contra": 0, "inicio": K(8, 45), "adversario": "Y"},
])
jogo45 = jogo("Petr", "Jan", 1.50, 2.50, 9, 30)
st45, mot45, _ = b.avaliar(jogo45, hist, b.montar_odds_map([jogo45]))
check(st45 == "bloqueado" and mot45 == ["PASSAR (jogou no horário anterior)"], (st45, mot45))
b.agora_cet = lambda: AGORA

# sem resultado: o nome está na grade do bloco anterior (ao vivo)
hist.definir_jogos("Petr", [
    {"resultado": "limpo", "sets_favor": 3, "sets_contra": 0, "inicio": K(7, 10), "adversario": "X"},
    {"resultado": "limpo", "sets_favor": 3, "sets_contra": 1, "inicio": K(7, 40), "adversario": "Y"},
])
atual = jogo("Petr", "Jan", 1.50, 2.50, 9, 0)
anterior = b.OddsMatch("Petr", "Outro", 1.40, 2.70, True, "1-1", K(8, 30))
grade = b.coletar_agenda([anterior, atual], AGORA)
check(any(o.in_play and o.home == "Petr" for o in grade), grade)
st_g, mot_g, _ = b.avaliar(atual, hist, b.montar_odds_map([atual]), agenda=grade)
check(st_g == "bloqueado" and mot_g == ["PASSAR (jogou no horário anterior)"], (st_g, mot_g))
# o adversário é que jogou antes: não bloqueia o alvo
so_jan = b.OddsMatch("Jan", "Outro", 1.40, 2.70, True, None, K(8, 30))
st_adv, _, fav_adv = b.avaliar(atual, hist, b.montar_odds_map([atual]), agenda=[so_jan, atual])
check(st_adv == "verde" and fav_adv == "Petr", (st_adv, fav_adv))
# a própria partida, mesmo ao vivo na grade, não conta como horário anterior
check(b.jogou_no_horario_anterior("Petr", atual.kickoff, [], [atual], "Jan") is False, "o próprio jogo")
velha = b.OddsMatch("Petr", "Outro", None, None, False, None, K(4, 0))
mantida = b.coletar_agenda([anterior], AGORA, [velha])
check(all(o.kickoff.hour != 4 for o in mantida) and any(o.in_play for o in mantida), mantida)

# ---------- mensagem: campos, ordenação por gap, NENHUMA, H2H só informativo ----------
class HistInfo:
    ativo = True
    def forma(self, nome, universo, agora):
        if nome == "Petr":
            return (4, 1, 60)
        if nome == "Jan":
            return (1, 3, 20)
        return None
    def h2h(self, home, away, universo, agora):
        return (0, 2)

forma_msg = b.FormaDia(b.Path(D) / "msg.json")
def gravar_forma(home, away, sh, sa, hora, minuto):
    ini = K(hora, minuto)
    forma_msg.mesclar_movi([{
        "id": f"{home}|{away}|{hora}:{minuto}",
        "home": home, "away": away, "sets_home": sh, "sets_away": sa,
        "inicio": ini, "fim": b.estimar_fim(ini, sh, sa),
        "fim_estimado": True, "league": "Czech Liga Pro",
    }], AGORA)
gravar_forma("Petr", "Camil", 3, 0, 7, 10)
gravar_forma("Duda", "Petr", 1, 3, 7, 40)          # Petr vence 3-1
gravar_forma("Milos", "Ema", 3, 0, 7, 0)
gravar_forma("Milos", "Felipe", 3, 0, 7, 30)       # score 6, sem C em comum
gravar_forma("Camil", "Jan", 3, 0, 7, 20)          # Jan perde 0-3 para Camil
gravar_forma("Zeta", "Adam", 3, 0, 7, 15)          # Adam perde 0-3
hist_msg = b.Historico()
forte = jogo("Milos", "Adam", 1.40, 2.80, 9, 30)   # gap 6 - (-3) = 9
medio = jogo("Petr", "Jan", 1.55, 2.40, 9, 30)    # gap 5 - (-3) + 2 = 10
fraco = jogo("Sem Dados", "Jan", 1.40, 2.50, 9, 30)
slot = "2026-11-20|09:30"
partes, verdes, defs = b.montar_mensagem_entrada(
    slot, [medio, fraco, forte], hist_msg, [medio, fraco, forte], forma_msg, HistInfo())
check(len(verdes) == 2 and verdes[0][1] == "Petr" and verdes[1][1] == "Milos", verdes)
msg = partes[0]
check(msg == (
    "09:30 — Petr x Jan\nEntrada: <b>Petr</b> @ 1.55\n\n"
    "09:30 — Milos x Adam\nEntrada: <b>Milos</b> @ 1.40"
), msg)
check("score_forma" not in msg and "Gap" not in msg and "Histórico" not in msg and "H2H" not in msg, msg)
check("Sem Dados" not in msg, msg)
check(any(o.home == "Sem Dados" for o in defs) is False, defs)

so, vazios, _ = b.montar_mensagem_entrada(slot, [fraco], hist_msg, [fraco], forma_msg)
check(vazios == [] and so == ["09:30 — Sem entrada"], so)

# ---------- fim gravado, fim estimado e meia-noite ----------
check(b.duracao_estimada_min(3, 0) == 15 and b.duracao_estimada_min(3, 1) == 20 and b.duracao_estimada_min(3, 2) == 25, "duração")
cru = {"results": [
    {"league": "Czech Liga Pro", "status": "finished", "home": "Petr", "away": "Jan",
     "final_score": "3-1", "kickoff_utc": "2026-11-20T07:00:00Z", "fixture_id": "1"},
    {"league": "Czech Liga Pro", "status": "finished", "home": "Ana", "away": "Bia",
     "final_score": "3-2", "finished_at": "2026-11-20T08:00:00Z", "fixture_id": "2"},
]}
parsed = b.MoviOdds.parse_results(cru)
sem_fim = next(p for p in parsed if p["id"] == "1")
com_fim = next(p for p in parsed if p["id"] == "2")
check(sem_fim["fim_estimado"] is True and sem_fim["fim"] - sem_fim["inicio"] == timedelta(minutes=20), sem_fim)
check(com_fim["fim_estimado"] is False and com_fim["inicio_estimado"] is True, com_fim)
check(com_fim["fim"] - com_fim["inicio"] == timedelta(minutes=25), com_fim["inicio"])

forma = b.FormaDia(b.Path(D) / "forma_teste.json")
tarde = {
    "id": "noite", "home": "Petr", "away": "Jan", "sets_home": 3, "sets_away": 0,
    "inicio": K(23, 20), "fim": K(23, 40), "fim_estimado": False, "league": "Czech Liga Pro",
}
forma.mesclar_movi([tarde], K(23, 50))
check(len(forma.jogos) == 1 and forma.jogos[0]["fim"].endswith("23:40:00+01:00"), forma.jogos[0])
forma.mesclar_movi([], K(0, 30, 21))
check(forma.dia == "2026-11-21" and len(forma.jogos) == 1, forma.jogos)
madrugada = K(0, 30, 21)
b.agora_cet = lambda: madrugada
petr = fj("Petr", forma.partidas_de("Petr"), madrugada)
check(petr.score_forma == 3.0 and petr.jogos_hoje == 1, (petr.score_forma, petr.jogos_hoje))

legado = {"sets_home": 3, "sets_away": 1, "quando": "2026-11-20T08:00:00+01:00", "home": "A", "away": "B"}
norm = b._normalizar_gravado(legado)
check(norm["fim_estimado"] is True and norm["inicio"].startswith("2026-11-20T08:00:00"), norm)
check(norm["fim"].startswith("2026-11-20T08:20:00"), norm["fim"])

print("FORMA OK", N, "checks")
