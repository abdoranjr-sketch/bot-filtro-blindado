"""Spec consolidada: alerta fixo, W.O., nomes, horário anterior e auditoria CSV.

requests é sempre simulado. A grade do MoviOdds fica em 144 consultas/dia.
"""
import csv
import logging
import os
import sys
import tempfile
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
os.environ.pop("HORARIO_ANTERIOR", None)
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


def at(h, mi):
    dt = K(h, mi)
    b.agora_cet = lambda: dt
    return dt


# ---------- grade 144 e alerta só às :25 e :55 ----------
check(b.MOVIODDS_CHAMADAS_DIA == 144, b.MOVIODDS_CHAMADAS_DIA)
check(b.MOVIODDS_CHAMADAS_MES_31 == 4464 and b.MOVIODDS_CHAMADAS_MES_31 < 5000, b.MOVIODDS_CHAMADAS_MES_31)
check(len(b.MOVIODDS_MINUTOS_ODDS) == 96 and len(b.MOVIODDS_MINUTOS_RESULTADOS) == 48, "96+48")
check(all(m in (23, 53) for _, m in b.MOVIODDS_MINUTOS_RESULTADOS), "resultados :23/:53")
check(b.dentro_da_antecedencia(K(9, 30), K(9, 25)), ":25 avisa o :30")
check(b.dentro_da_antecedencia(K(9, 30), K(9, 26)), "ciclo atrasado ainda avisa")
check(b.dentro_da_antecedencia(K(9, 30), K(9, 29)), "até 4 min depois")
check(b.dentro_da_antecedencia(K(10, 0), K(9, 55)), ":55 avisa o :00")
check(b.dentro_da_antecedencia(K(0, 0, 21), K(23, 55)), "23:55 avisa 00:00")
check(not b.dentro_da_antecedencia(K(9, 30), K(9, 24)), "antes da janela")
check(not b.dentro_da_antecedencia(K(9, 30), K(9, 30)), "no apito já passou")
check(not b.dentro_da_antecedencia(K(9, 15), K(9, 10)), "bloco :15 não tem alerta")
check(not b.dentro_do_fallback(K(9, 30), K(9, 29)), "sem fallback ao vivo")
lista = [
    b.OddsMatch("A Aa", "B Bb", 1.5, 2.2, False, None, K(9, 30)),
    b.OddsMatch("C Cc", "D Dd", 1.5, 2.2, False, None, K(9, 15)),
]
check([k for k, _ in b.blocos_devidos(lista, K(9, 25))] == ["2026-11-20|09:30"], "só o bloco :30")

# ---------- nomes ----------
check(b.nome_exibicao("{1964} NOVAK, Jan") == "Jan Novak", b.nome_exibicao("{1964} NOVAK, Jan"))
check(b.nome_exibicao("SVOBODA Petr") == "Petr Svoboda", b.nome_exibicao("SVOBODA Petr"))
check(b.nome_exibicao("Bílek, Zdeněk") == "Zdenek Bilek", b.nome_exibicao("Bílek, Zdeněk"))
check(b.nome_exibicao("Petr Svoboda") == "Petr Svoboda", "já canônico")
check(b.mesmo_jogador("{1964} NOVAK, Jan", "jan novak"), "casa odds e resultado")
check(b.mesmo_jogador("[PRO] SVOBODA Petr", "Petr Svoboda"), "colchete")
check(not b.mesmo_jogador("Jan Novakova", "Jan Novak"), "não corta o sobrenome")
check(not b.mesmo_jogador("Novak", "Jan Novak"), "não aceita um token só")
odds = b.OddsMatch("{1964} NOVAK, Jan", "SVOBODA Petr", 1.50, 2.40, False, None, K(9, 30))
check(b.achar_odds("Jan Novak", "Petr Svoboda", [odds]) is odds, "odds casam com o resultado")

# ---------- W.O., desistência, cancelado e placar incompleto ----------
base = {
    "league": "Czech Liga Pro",
    "kickoff_utc": "2026-11-20T08:00:00Z",
    "finished_at": "2026-11-20T08:20:00Z",
}
bruto = {"results": [
    {**base, "status": "finished", "final_score": "3-0", "home": "WO Home", "away": "WO Away",
     "note": "W.O.", "fixture_id": "1"},
    {**base, "status": "finished", "final_score": "W.O.", "home": "A", "away": "B", "fixture_id": "2"},
    {**base, "status": "finished", "final_score": "3-1", "home": "Desist", "away": "Outro",
     "note": "desistência", "fixture_id": "3"},
    {**base, "status": "cancelled", "final_score": "3-0", "home": "Canc", "away": "Outro", "fixture_id": "4"},
    {**base, "status": "finished", "final_score": "3-0", "home": "Canc2", "away": "Outro",
     "comment": "cancelado", "fixture_id": "5"},
    {**base, "status": "finished", "final_score": "1-1", "home": "Inc", "away": "Outro", "fixture_id": "6"},
    {**base, "status": "finished", "final_score": "3-0", "home": "Petr Svoboda", "away": "Jan Novak",
     "fixture_id": "7"},
]}
gravados = b.MoviOdds.parse_results(bruto)
check(len(gravados) == 1 and gravados[0]["home"] == "Petr Svoboda", gravados)

agora = K(9, 25)
forma = b.metricas_forma("Petr", [
    {"sets_favor": 3, "sets_contra": 0, "fim": K(8, 0), "texto": "W.O."},
    {"sets_favor": 3, "sets_contra": 0, "fim": K(8, 20), "status": "cancelado"},
    {"sets_favor": 1, "sets_contra": 1, "fim": K(8, 30)},
    {"sets_favor": 3, "sets_contra": 0, "fim": K(8, 40)},
    {"sets_favor": 3, "sets_contra": 1, "fim": K(8, 55)},
], agora)
check(forma.jogos_hoje == 2 and forma.score_forma == 5.0 and forma.vitorias_limpas_seguidas == 2, forma)
check(not forma.perdeu_ultimo_jogo, "W.O. não conta como último jogo")

# ---------- horário anterior: rigido ou só 4/5 sets ----------
def anterior(sets_a, sets_b):
    return [{"inicio": K(9, 0), "sets_favor": sets_a, "sets_contra": sets_b}]


os.environ["HORARIO_ANTERIOR"] = "sets"
check(not b.jogou_no_horario_anterior("Petr", K(9, 30), anterior(3, 0)), "3-0 não bloqueia")
check(b.jogou_no_horario_anterior("Petr", K(9, 30), anterior(3, 1)), "4 sets bloqueia")
check(b.jogou_no_horario_anterior("Petr", K(9, 30), anterior(2, 3)), "5 sets bloqueia")
grade = [b.OddsMatch("Petr", "Outro", 1.4, 2.5, False, None, K(9, 0))]
check(not b.jogou_no_horario_anterior("Petr", K(9, 30), [], grade, "Jan"), "sem placar não bloqueia")
os.environ["HORARIO_ANTERIOR"] = "rigido"
check(b.jogou_no_horario_anterior("Petr", K(9, 30), anterior(3, 0)), "rigido bloqueia 3-0")
check(b.jogou_no_horario_anterior("Petr", K(9, 30), [], grade, "Jan"), "rigido bloqueia a grade")
os.environ.pop("HORARIO_ANTERIOR", None)
check(b.modo_horario_anterior() == "rigido", b.modo_horario_anterior())

# ---------- auditoria: GREEN/RED só ~35 min depois, sem rede ----------
at(9, 25)
livro = b.LivroEntradas(b.Path(D) / "entradas_spec.json")
check(livro.registrar("Petr Svoboda", "Jan Novak", "Petr Svoboda", K(9, 30), 1.50, 7.0), "grava")
check(not livro.registrar("Petr Svoboda", "Jan Novak", "Petr Svoboda", K(9, 30), 1.50, 7.0), "não duplica")
check(livro.registrar("{1964} NOVAK, Jan", "SVOBODA Petr", "Jan Novak", K(11, 0), 1.40, 6.0), "segunda")
with b.AUDITORIA_FILE.open(encoding="utf-8", newline="") as fh:
    linhas = list(csv.DictReader(fh))
check(len(linhas) == 2, linhas)
check(linhas[0]["jogo"] == "Petr Svoboda vs Jan Novak", linhas[0])
check(linhas[0]["alvo"] == "Petr Svoboda" and linhas[0]["odd"] == "1.50", linhas[0])
check(linhas[0]["gap"] == "7.0" and linhas[0]["resultado"] == "", linhas[0])
check(linhas[1]["jogo"] == "Jan Novak vs Petr Svoboda" and linhas[1]["resultado"] == "", linhas[1])
check(linhas[0].keys() >= {"data", "horario", "jogo", "alvo", "odd", "gap", "resultado"}, linhas[0])

forma_dia = b.FormaDia(b.Path(D) / "forma_spec.json")
forma_dia.jogos = [{
    "home": "Petr Svoboda", "away": "Jan Novak", "sets_home": 3, "sets_away": 1,
    "inicio": K(9, 30).isoformat(), "fim": K(9, 50).isoformat(), "league": "Czech Liga Pro",
}]
check(b.liquidar_livro(livro, forma_dia, None, K(9, 50)) == 1, "liquida cedo")
check(livro.itens[0]["status"] == "green", livro.itens[0])
with b.AUDITORIA_FILE.open(encoding="utf-8", newline="") as fh:
    cedo = list(csv.DictReader(fh))
check(cedo[0]["resultado"] == "" and cedo[1]["resultado"] == "", "ainda não passaram 35 min")
check(b.liquidar_livro(livro, forma_dia, None, K(10, 5)) == 0, "já estava liquidada")
with b.AUDITORIA_FILE.open(encoding="utf-8", newline="") as fh:
    depois = list(csv.DictReader(fh))
check(depois[0]["resultado"] == "GREEN" and depois[1]["resultado"] == "", depois)
forma_dia.jogos.append({
    "home": "{1964} NOVAK, Jan", "away": "SVOBODA Petr", "sets_home": 0, "sets_away": 3,
    "inicio": K(11, 0).isoformat(), "fim": K(11, 20).isoformat(), "league": "Czech Liga Pro",
})
check(b.liquidar_livro(livro, forma_dia, None, K(11, 20)) == 1, "segunda liquida")
with b.AUDITORIA_FILE.open(encoding="utf-8", newline="") as fh:
    meio = list(csv.DictReader(fh))
check(meio[1]["resultado"] == "", "11:20 ainda é cedo para a de 11:00")
check(b.liquidar_livro(livro, forma_dia, None, K(11, 35)) == 0, "sem chamada nova")
with b.AUDITORIA_FILE.open(encoding="utf-8", newline="") as fh:
    fim = list(csv.DictReader(fh))
check(fim[0]["resultado"] == "GREEN" and fim[1]["resultado"] == "RED", fim)
check(livro.itens[1]["status"] == "red", livro.itens[1])

# ---------- ciclo de ~38 s atravessa :25 e manda uma mensagem só ----------
class _TG:
    def __init__(self):
        self.sent = []

    def send(self, texto, chat_id=None, reply_to=None):
        self.sent.append(texto)
        return True

class _Log(logging.Handler):
    def __init__(self):
        super().__init__()
        self.rows = []

    def emit(self, record):
        self.rows.append(record.getMessage())

base = b.TZ.localize(datetime(2026, 11, 20, 19, 24, 40))
jogo = b.OddsMatch("Petr Svoboda", "Jan Novak", 1.50, 2.40, True, None, b.TZ.localize(datetime(2026, 11, 20, 19, 30)))
caminho = b.Path(D) / "entradas_ciclo.json"
entradas = b.CacheSet(caminho)
sinais = b.CacheSet(b.Path(D) / "sinais_ciclo.json")
hist = b.Historico()
tg = _TG()
tent = {}
cap = _Log()
b.log.addHandler(cap)
try:
    for i in range(8):
        agora = base + timedelta(seconds=38 * i)
        b.agora_cet = lambda a=agora: a
        b.despachar_alerta(agora, [jogo], entradas, tent, tg, hist, sinais, odds_frescas=True)
finally:
    b.log.removeHandler(cap)
check(len(tg.sent) == 1, tg.sent)
check(tg.sent[0] == "19:30 — Sem entrada", tg.sent[0])
check(any(m.startswith("[ENTRADA 2026-11-20|19:30] 1 jogos avaliados, 0 aprovados") for m in cap.rows), cap.rows)
reinicio = b.CacheSet(caminho)
tg2 = _TG()
b.agora_cet = lambda: base + timedelta(seconds=38 * 3)
check(b.despachar_alerta(b.agora_cet(), [jogo], reinicio, {}, tg2, hist, sinais) is False, "não repete")
check(tg2.sent == [], tg2.sent)

vazio = _TG()
cap2 = _Log()
b.log.addHandler(cap2)
try:
    quando = b.TZ.localize(datetime(2026, 11, 20, 20, 25, 20))
    b.agora_cet = lambda: quando
    b.despachar_alerta(quando, [], b.CacheSet(b.Path(D) / "entradas_vazio.json"), {}, vazio,
                       hist, b.CacheSet(b.Path(D) / "sinais_vazio.json"), odds_frescas=False)
finally:
    b.log.removeHandler(cap2)
check(vazio.sent == ["20:30 — Sem entrada"], vazio.sent)
check(any("0 jogos avaliados, 0 aprovados (sem odds frescas / 0 jogos na grade)" in m for m in cap2.rows), cap2.rows)

print("SPEC OK", N, "checks")
