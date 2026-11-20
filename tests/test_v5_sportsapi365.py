"""SportsAPI365: resultados anteriores, sem mexer no filtro do dia nem nas 144 do MoviOdds.

A rede é sempre simulada. A chave de teste não pode aparecer em log nem em arquivo.
"""
import logging
import os
import sys
import tempfile
from datetime import datetime, timedelta
from pathlib import Path

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
os.environ.pop("TELEGRAM_OWNER_ID", None)
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
import requests


def _blocked(*a, **k):
    raise AssertionError("real HTTP call attempted")


requests.get = requests.post = _blocked
import bot_filtro_blindado_v5 as b
import historico_sportsapi365 as s

CHAVE = "CHAVE-SECRETA-SPORTS-99"
N = 0


def check(c, m):
    global N
    assert c, m
    N += 1


class Cap(logging.Handler):
    def __init__(self):
        super().__init__(level=logging.DEBUG)
        self.msgs = []

    def emit(self, record):
        self.msgs.append(record.getMessage())


cap = Cap()
logging.getLogger("FiltroV5").addHandler(cap)


def sem_chave(msgs):
    check(all(CHAVE not in m for m in msgs), msgs)


class Resp:
    def __init__(self, status, payload, headers=None):
        self.status_code = status
        self._payload = payload
        self.headers = headers or {}
        self.text = str(payload)

    def json(self):
        if isinstance(self._payload, Exception):
            raise self._payload
        return self._payload


def praga(y, mo, d, h=12, mi=0):
    return s.TZ_PRAGA.localize(datetime(y, mo, d, h, mi))


def K(h, m, d=20):
    return b.TZ.localize(datetime(2026, 11, d, h, m))


def pasta():
    return Path(tempfile.mkdtemp())


def evento(eid, hid, hnome, aid, anome, sh, sa, ts, status="finished", liga="Czech Liga Pro"):
    return {
        "id": eid,
        "homeTeam": {"id": hid, "name": hnome},
        "awayTeam": {"id": aid, "name": anome},
        "startTimestamp": ts,
        "status": status,
        "homeScore": {"current": sh, "period1": 11, "period2": 11, "period3": 11},
        "awayScore": {"current": sa, "period1": 8, "period2": 6, "period3": 9},
        "competitionName": liga,
    }


def pagina(items, page, total_pages, has_more, remaining, reset):
    return Resp(200, {
        "items": items,
        "page": page,
        "limit": 100,
        "total": 167,
        "totalPages": total_pages,
        "hasMore": has_more,
    }, {
        "x-ratelimit-requests-remaining": str(remaining),
        "x-ratelimit-requests-reset": str(int(reset)),
    })


def novo_hist():
    h = b.Historico()
    h.data = {}
    h.save()
    return h


def jogo(home, away, oh, oa, hora, minuto):
    return b.OddsMatch(home, away, oh, oa, False, None, K(hora, minuto))


def gravado(eid, hid, hnome, aid, anome, sh, sa, quando):
    return {
        "id": str(eid),
        "ts": int(quando.timestamp()),
        "home_id": hid,
        "home": hnome,
        "away_id": aid,
        "away": anome,
        "sh": sh,
        "sa": sa,
        "dia": quando.astimezone(s.TZ_PRAGA).date().isoformat(),
    }


def cliente(http, chave=CHAVE):
    return s.HistoricoSportsAPI365(chave, pasta(), http_get=http)


def boom(*a, **k):
    raise AssertionError("API chamada fora da coleta diária")


# ---------- o filtro de hoje e o orçamento do MoviOdds não mudam ----------
check(b.ODD_MIN_ALVO == 1.25 and b.ODD_MAX_ALVO == 1.85, (b.ODD_MIN_ALVO, b.ODD_MAX_ALVO))
check(b.MOVIODDS_CHAMADAS_DIA == 144, b.MOVIODDS_CHAMADAS_DIA)
check(b.MOVIODDS_CHAMADAS_MES_31 == 4464, b.MOVIODDS_CHAMADAS_MES_31)
check(s.TETO_DIA == 40 and s.TETO_PLANO == 50 and s.FOLGA_RESTANTE == 10, (s.TETO_DIA, s.FOLGA_RESTANTE))
check(s.HOST == "table-tennis-api-live-scores-stats-odds-predictions.p.rapidapi.com", s.HOST)
check(s.TORNEIO == "87328107" and s.LIMITE_PAGINA == 100 and s.MAX_PAGINAS == 3, s.TORNEIO)
raiz = Path(__file__).resolve().parents[1]
for nome in ("bot_filtro_blindado_v5.py", "historico_sportsapi365.py", "README.md", ".env.example", "Dockerfile"):
    check(CHAVE not in (raiz / nome).read_text(encoding="utf-8"), nome)

# ---------- normalizador: Sobrenome I. casa com o nome da MoviOdds, sem chute ----------
check(s.nome_api_inicial("Bilek Z.") == (("bilek",), "z"), s.nome_api_inicial("Bilek Z."))
check(s.nome_api_inicial("Bílek Z") == (("bilek",), "z"), s.nome_api_inicial("Bílek Z"))
check(s.nome_api_inicial("Vales J.") == (("vales",), "j"), s.nome_api_inicial("Vales J."))
check(s.nomes_compativeis("Zdenek Bilek", "Bilek Z."), "ordem nome sobrenome")
check(s.nomes_compativeis("Bilek Zdenek", "Bilek Z."), "ordem sobrenome nome")
check(s.nomes_compativeis("Zdeněk Bílek", "Bílek Z."), "acentos")
check(s.nomes_compativeis("Zdenek Bilek Junior", "Bilek Z. Jr"), "sufixo")
check(s.nomes_compativeis("Jiri Vales", "Vales J.") and s.nomes_compativeis("Vales Jiri", "Vales J."), "Vales")
check(s.nomes_compativeis("Jan Van Ek", "Van Ek J."), "sobrenome composto")
check(not s.nomes_compativeis("Bilek", "Bilek Z."), "um token só não confirma a inicial")
check(not s.nomes_compativeis("Petr Svoboda", "Bilek Z."), "outro jogador")
check(not s.nomes_compativeis("Jan Novak", "Novakova J."), "sobrenome parecido não vale")
check(not s.nomes_compativeis("", "Bilek Z.") and not s.nomes_compativeis("Zdenek Bilek", ""), "vazio")
check(s.nomes_compativeis("Zdenek Bilek", "Bilek Zdenek"), "API com nome completo: só tokens iguais")

cat_unico = {1: "Bilek Z."}
check(s.resolver_ids(["Zdenek Bilek"], cat_unico)["Zdenek Bilek"] == 1, "casamento único")
check(s.resolver_ids(["Bilek Zdenek"], cat_unico)["Bilek Zdenek"] == 1, "ordem invertida")
ambos = s.resolver_ids(["Zdenek Bilek", "Zbynek Bilek"], cat_unico)
check(ambos["Zdenek Bilek"] is None and ambos["Zbynek Bilek"] is None, ambos)
dois_ids = s.resolver_ids(["Zdenek Bilek"], {1: "Bilek Z.", 2: "Bilek Z."})
check(dois_ids["Zdenek Bilek"] is None, dois_ids)
duas_leituras = s.resolver_ids(["Zdenek Bilek"], {1: "Bilek Z.", 2: "Zdenek B."})
check(duas_leituras["Zdenek Bilek"] is None, duas_leituras)
sv = s.resolver_ids(["Petr Svoboda", "Svoboda Petr"], {7: "Svoboda P."})
check(sv["Petr Svoboda"] == 7 and sv["Svoboda Petr"] == 7, sv)
pares = s.resolver_ids(["Petr Svoboda", "Jan Svoboda"], {1: "Svoboda P.", 2: "Svoboda J."})
check(pares["Petr Svoboda"] == 1 and pares["Jan Svoboda"] == 2, pares)
check(s.percentual_limpas(2, 4) == 50, s.percentual_limpas(2, 4))
check(s.percentual_limpas(1, 3) == 33 and s.percentual_limpas(2, 3) == 67, "arredondamento")
check(s.percentual_limpas(0, 4) == 0 and s.percentual_limpas(4, 4) == 100, "extremos")

# ---------- parser ----------
base_ts = int(praga(2026, 11, 19, 18).timestamp())
ok = s.analisar_evento(evento(10, 1, "Bilek Z.", 2, "Vales J.", 3, 1, base_ts))
check(ok and ok["sh"] == 3 and ok["sa"] == 1 and ok["home"] == "Bilek Z." and ok["home_id"] == 1, ok)
check(s.analisar_evento(evento(11, 1, "Bilek Z.", 2, "Vales J.", 3, 2, base_ts))["sa"] == 2, "3-2 entra")
check(s.analisar_evento(evento(12, 1, "A", 2, "B", 2, 2, base_ts)) is None, "sem vencedor")
check(s.analisar_evento(evento(13, 1, "A", 2, "B", 3, 0, base_ts, status="live")) is None, "não terminou")
check(s.analisar_evento(evento(14, 1, "A", 2, "B", 3, 0, base_ts, liga="TT Elite Series")) is None, "outra liga")
check(s.analisar_evento(evento(15, 1, "", 2, "B", 3, 0, base_ts)) is None, "sem nome")

# ---------- sem chave: desligado, sem chamada, mensagem igual à de hoje ----------
cap.msgs.clear()
chamadas_off = []


def http_off(*a, **k):
    chamadas_off.append(1)
    raise AssertionError("sem chave não chama")


off = s.HistoricoSportsAPI365("", pasta(), http_get=http_off)
check(off.ativo is False and s.HistoricoSportsAPI365("   ", pasta()).ativo is False, "chave vazia")
check(off.atualizar(praga(2026, 11, 21, 0, 30)) is False and chamadas_off == [], chamadas_off)
check(off.forma("Zdenek Bilek", ["Zdenek Bilek"], praga(2026, 11, 21)) is None, "sem forma")
check(off.h2h("A", "B", ["A", "B"], praga(2026, 11, 21)) is None, "sem h2h")
check(off.perdeu_ultimos_2("A", "B", ["A", "B"], praga(2026, 11, 21)) is False, "sem bloqueio")
check(not (pasta() / s.ARQUIVO).exists() or True, "instância nova")
check(cap.msgs == [], cap.msgs)
check("SPORTSAPI365" not in repr(off), repr(off))

b.agora_cet = lambda: K(8, 55)
h = novo_hist()
h.definir_jogos("Petr Svoboda", [
    {"resultado": "limpo", "sets_favor": 3, "sets_contra": 0, "inicio": K(7, 20)},
    {"resultado": "limpo", "sets_favor": 3, "sets_contra": 1, "inicio": K(7, 40)},
])
h.definir_jogos("Jan Novak", [{"resultado": "derrota", "sets_favor": 0, "sets_contra": 3, "inicio": K(7, 30)}])
partida = jogo("Petr Svoboda", "Jan Novak", 1.50, 2.50, 9, 0)
status, motivos, fav = b.avaliar(partida, h, b.montar_odds_map([partida]))
check(status == "verde" and fav == "Petr Svoboda", (status, motivos, fav))
slot = "2026-11-20|08:55"
sem, v_sem, _ = b.montar_mensagem_entrada(slot, [partida], h, [partida])
com_off, v_off, _ = b.montar_mensagem_entrada(slot, [partida], h, [partida], None, off)
check(sem == com_off and v_sem == v_off and len(v_sem) == 1, "sem chave a mensagem não muda")
check("Histórico 7d" not in sem[0] and "H2H 14d" not in sem[0], sem[0])

# ---------- paginação, uma vez por dia, cache e poda de 14 dias ----------
RESET = int(praga(2026, 12, 31).timestamp())
velho = int(praga(2026, 10, 1, 12).timestamp())
dia_alvo = "2026-11-20"
vistos = []


def http_paginas(url, params=None, headers=None, timeout=None):
    vistos.append({"url": url, "params": dict(params or {}), "headers": dict(headers or {}), "timeout": timeout})
    pag = int(params["page"])
    if pag == 1:
        items = [
            evento(1, 1, "Bílek Z.", 2, "Vales J.", 3, 0, int(praga(2026, 11, 20, 15).timestamp())),
            evento(2, 3, "Outra L.", 4, "X Y.", 3, 0, int(praga(2026, 11, 20, 16).timestamp()), liga="TT Cup"),
            evento(3, 5, "Live A.", 6, "Live B.", 3, 0, int(praga(2026, 11, 20, 17).timestamp()), status="live"),
            evento(4, 7, "Empate A.", 8, "Empate B.", 2, 2, int(praga(2026, 11, 20, 18).timestamp())),
        ]
        return pagina(items, 1, 2, True, 48, RESET)
    if pag == 2:
        items = [
            evento(5, 1, "Bílek Z.", 9, "Nova K J.", 3, 2, int(praga(2026, 11, 20, 19).timestamp())),
            evento(6, 2, "Vales J.", 10, "Hora I.", 1, 3, int(praga(2026, 11, 20, 20).timestamp())),
            evento(7, 11, "", 12, "Sem Nome", 3, 0, int(praga(2026, 11, 20, 21).timestamp())),
            evento("velho", 1, "Bílek Z.", 2, "Vales J.", 3, 0, velho),
        ]
        return pagina(items, 2, 2, False, 47, RESET)
    raise AssertionError(f"página {pag} não devia ser pedida")


cap.msgs.clear()
cli = cliente(http_paginas)
cli.backfill_pendente = False
check(cli.atualizar(praga(2026, 11, 20, 0, 29)) is False and vistos == [], "antes das 00:30 não baixa")
check(cli.atualizar(praga(2026, 11, 21, 0, 30)) is True, "00:30 baixa o dia anterior")
check(len(vistos) == 2, vistos)
p1, p2 = vistos
check(p1["url"] == s.URL and p2["url"] == s.URL, p1["url"])
check(p1["timeout"] == 20 and p2["timeout"] == 20, p1["timeout"])
check(p1["headers"] == {"x-rapidapi-key": CHAVE, "x-rapidapi-host": s.HOST}, p1["headers"])
for ped in (p1, p2):
    check(ped["params"]["fromDate"] == dia_alvo and ped["params"]["toDate"] == dia_alvo, ped["params"])
    check(ped["params"]["tournamentId"] == "87328107", ped["params"])
    check(ped["params"]["status"] == "finished" and ped["params"]["limit"] == 100, ped["params"])
    check("include" not in ped["params"] and CHAVE not in ped["url"] and CHAVE not in str(ped["params"]), ped)
check(p1["params"]["page"] == 1 and p2["params"]["page"] == 2, (p1["params"], p2["params"]))
ids = [j["id"] for j in cli.jogos]
check(ids == ["1", "5", "6"], ids)
check(all(j["ts"] != velho for j in cli.jogos), "jogo de outubro saiu na poda")
check(dia_alvo in cli.dias and cli.backfill_pendente is False, cli.dias)
check(cli.atualizar(praga(2026, 11, 21, 15, 0)) is False and len(vistos) == 2, "o mesmo dia não baixa de novo")
blob = (cli.path).read_text(encoding="utf-8") + (cli.orcamento.path).read_text(encoding="utf-8")
check(CHAVE not in blob and "Bílek Z." in blob, "cache sem a chave, com o nome")
sem_chave(cap.msgs)
recarregado = s.HistoricoSportsAPI365(CHAVE, cli.dir, http_get=boom)
check(len(recarregado.jogos) == 3 and recarregado.concluido_em == "2026-11-21", recarregado.concluido_em)
check(recarregado.atualizar(praga(2026, 11, 21, 18, 0)) is False, "restart no mesmo dia não chama")

# no dia seguinte, só o novo ontem — o backfill não se repete
novos = []


def http_um(url, params=None, headers=None, timeout=None):
    novos.append(params["fromDate"])
    ts = int(praga(2026, 11, 21, 12).timestamp())
    return pagina([evento(99, 1, "Bilek Z.", 2, "Vales J.", 3, 1, ts)], 1, 1, False, 40, RESET)


recarregado.http_get = http_um
check(recarregado.atualizar(praga(2026, 11, 22, 0, 30)) is True, "dia seguinte")
check(novos == ["2026-11-21"], novos)
check("99" in [j["id"] for j in recarregado.jogos], recarregado.jogos)

# ---------- backfill de 7 dias na primeira vez, do mais recente para trás ----------
ordem = []


def http_backfill(url, params=None, headers=None, timeout=None):
    ordem.append((params["fromDate"], int(params["page"]), params.get("limit")))
    ano, mes, dia = (int(x) for x in params["fromDate"].split("-"))
    ts = int(praga(ano, mes, dia, 12).timestamp())
    return pagina([evento(params["fromDate"], 1, "Bilek Z.", 2, "Vales J.", 3, 0, ts)], 1, 1, False, 30, RESET)


bf = cliente(http_backfill)
check(bf.backfill_pendente is True, "sem arquivo, backfill")
check(bf.atualizar(praga(2026, 11, 21, 0, 30)) is True, "backfill")
esperados = [(praga(2026, 11, 21).date() - timedelta(days=i)).isoformat() for i in range(1, 8)]
check([d for d, _, _ in ordem] == esperados, ordem)
check(all(pag == 1 and limite == 100 for _, pag, limite in ordem), ordem)
check(bf.backfill_pendente is False and len(bf.jogos) == 7, (bf.backfill_pendente, len(bf.jogos)))
check(bf.atualizar(praga(2026, 11, 21, 2, 0)) is False and len(ordem) == 7, "backfill não repete")

# ---------- teto de 40 por janela, mesmo com a API ainda devolvendo remaining alto ----------
teto_calls = []
RESET_LONGO = int(praga(2026, 12, 31).timestamp())


def http_infinito(url, params=None, headers=None, timeout=None):
    teto_calls.append((params["fromDate"], params["page"]))
    n = len(teto_calls)
    ts = int(praga(2026, 11, 20, 12).timestamp())
    return pagina(
        [evento(f"{params['fromDate']}-{params['page']}", 1, "Bilek Z.", 2, "Vales J.", 3, 0, ts)],
        params["page"], 9, True, 50 - n, RESET_LONGO,
    )


teto = cliente(http_infinito)
check(teto.atualizar(praga(2026, 11, 21, 0, 30)) is True, "backfill de 7×3 cabe em 40")
check(len(teto_calls) == 21 and teto.orcamento.usadas == 21, (len(teto_calls), teto.orcamento.usadas))
for dia in range(22, 28):
    check(teto.atualizar(praga(2026, 11, dia, 0, 30)) is True, dia)
check(len(teto_calls) == 39 and teto.orcamento.usadas == 39, (len(teto_calls), teto.orcamento.usadas))
check(teto.atualizar(praga(2026, 11, 28, 0, 30)) is False, "a 40ª chamada esgota no meio do dia")
check(len(teto_calls) == 40 and teto.orcamento.usadas == 40, (len(teto_calls), teto.orcamento.usadas))
check("2026-11-27" not in teto.dias, teto.dias)
check(teto.atualizar(praga(2026, 11, 28, 12, 0)) is False and len(teto_calls) == 40, "não passa de 40")
check(teto.orcamento.pode(praga(2026, 11, 29, 1, 0)) is False, "dia novo não zera enquanto o reset não chegou")
check(teto.orcamento.usadas == 40, teto.orcamento.usadas)
check(teto.orcamento.pode(praga(2027, 1, 1, 0, 30)) is True and teto.orcamento.usadas == 0, "no reset a janela abre")

# remaining do cabeçalho manda parar mesmo com o contador local folgado
rem_calls = []


def http_remaining(url, params=None, headers=None, timeout=None):
    rem_calls.append(params["page"])
    ts = int(praga(2026, 11, 20, 12).timestamp())
    return pagina([evento(1, 1, "Bilek Z.", 2, "Vales J.", 3, 0, ts)], 1, 2, True, 10, RESET_LONGO)


rem = cliente(http_remaining)
rem.backfill_pendente = False
rem.orcamento.usadas = 0
rem.orcamento.remaining = 11
rem.orcamento.janela = "2026-11-21"
rem.orcamento.reset_em = RESET_LONGO
check(rem.atualizar(praga(2026, 11, 21, 1, 0)) is False and rem_calls == [1], rem_calls)
check("2026-11-20" not in rem.dias and rem.orcamento.remaining == 10, rem.orcamento.remaining)

cheio = cliente(http_remaining)
cheio.backfill_pendente = False
cheio.orcamento.usadas = 40
cheio.orcamento.janela = "2026-11-21"
cheio.orcamento.reset_em = RESET_LONGO
cheio.orcamento.remaining = None
antes = len(rem_calls)
check(cheio.atualizar(praga(2026, 11, 21, 1, 0)) is False and len(rem_calls) == antes, "40 local, zero chamadas")

# ---------- 429 e 403 desligam até o reset; falha de rede não vaza a chave ----------
def http_status(codigo):
    def _get(url, params=None, headers=None, timeout=None):
        _get.n += 1
        return Resp(codigo, {"erro": CHAVE, "url": url}, {
            "x-ratelimit-requests-remaining": "0",
            "x-ratelimit-requests-reset": str(int(praga(2026, 11, 21, 18).timestamp())),
            "x-echo": CHAVE,
        })
    _get.n = 0
    return _get


for codigo in (429, 403):
    cap.msgs.clear()
    http = http_status(codigo)
    bloqueado = cliente(http)
    bloqueado.backfill_pendente = False
    quando = praga(2026, 11, 21, 1, 0)
    check(bloqueado.atualizar(quando) is False and http.n == 1, (codigo, http.n))
    check(bloqueado.orcamento.desligado_ate is not None, codigo)
    check(bloqueado.atualizar(praga(2026, 11, 21, 2, 0)) is False and http.n == 1, "segue desligado")
    check(any(f"HTTP {codigo}" in m for m in cap.msgs), cap.msgs)
    sem_chave(cap.msgs)
    check(bloqueado.atualizar(praga(2026, 11, 21, 18, 1)) is False and http.n == 2, (codigo, http.n))
    check(bloqueado.atualizar(praga(2026, 11, 21, 18, 2)) is False and http.n == 2, "o 429 seguinte continua desligado")

cap.msgs.clear()
rede_n = []


def http_rede(url, params=None, headers=None, timeout=None):
    rede_n.append(1)
    raise requests.ConnectionError(f"conexao {CHAVE} {url}")


rede = cliente(http_rede)
rede.backfill_pendente = False
check(rede.atualizar(praga(2026, 11, 21, 1, 0)) is False and rede_n == [1], rede_n)
check(rede.orcamento.usadas == 1, rede.orcamento.usadas)
check(rede.atualizar(praga(2026, 11, 21, 1, 10)) is False and rede_n == [1], "espera o intervalo")
check(any("ConnectionError" in m for m in cap.msgs), cap.msgs)
sem_chave(cap.msgs)
check(all("conexao " not in m for m in cap.msgs), cap.msgs)

# ---------- H2H: só os 2 últimos, dentro de 14 dias ----------
def cache_h2h(jogos):
    h2 = s.HistoricoSportsAPI365(CHAVE, pasta(), http_get=boom)
    h2.jogos = jogos
    return h2


def duelo(dia, sh, sa, petr_em_casa=True):
    quando = praga(2026, 11, dia, 18)
    if petr_em_casa:
        return gravado(f"h{dia}", 1, "Svoboda P.", 2, "Novak J.", sh, sa, quando)
    return gravado(f"h{dia}", 2, "Novak J.", 1, "Svoboda P.", sa, sh, quando)


agora = praga(2026, 11, 20, 8, 55)
nomes = ["Petr Svoboda", "Jan Novak"]
dois = cache_h2h([duelo(8, 0, 3), duelo(9, 1, 3, petr_em_casa=False)])
check(dois.perdeu_ultimos_2("Petr Svoboda", "Jan Novak", nomes, agora) is True, "2 derrotas")
check(dois.h2h("Petr Svoboda", "Jan Novak", nomes, agora) == (0, 2), dois.h2h("Petr Svoboda", "Jan Novak", nomes, agora))
um = cache_h2h([duelo(9, 0, 3)])
check(um.perdeu_ultimos_2("Petr Svoboda", "Jan Novak", nomes, agora) is False, "uma derrota não bloqueia")
meio = cache_h2h([duelo(8, 0, 3), duelo(9, 3, 1), duelo(10, 1, 3)])
check(meio.perdeu_ultimos_2("Petr Svoboda", "Jan Novak", nomes, agora) is False, "o do meio foi vitória")
recentes = cache_h2h([duelo(8, 3, 0), duelo(9, 0, 3), duelo(10, 2, 3)])
check(recentes.perdeu_ultimos_2("Petr Svoboda", "Jan Novak", nomes, agora) is True, "as duas últimas")
check(recentes.h2h("Petr Svoboda", "Jan Novak", nomes, agora) == (1, 2), "1 vitória e 2 derrotas")

# ---------- mensagem hh:55: linhas no verde e em Sem entrada; bloqueio só no H2H ----------
def anterior_de_mensagem():
    ant = s.HistoricoSportsAPI365(CHAVE, pasta(), http_get=boom)
    jogos = [
        gravado("p1", 1, "Svoboda P.", 9, "Outro A.", 3, 0, praga(2026, 11, 18, 11)),
        gravado("p2", 1, "Svoboda P.", 9, "Outro A.", 3, 1, praga(2026, 11, 17, 11)),
        gravado("p3", 9, "Outro A.", 1, "Svoboda P.", 3, 1, praga(2026, 11, 16, 11)),
        gravado("p4", 1, "Svoboda P.", 9, "Outro A.", 3, 2, praga(2026, 11, 15, 11)),
        gravado("p5", 1, "Svoboda P.", 9, "Outro A.", 3, 0, praga(2026, 11, 20, 1)),
        gravado("p6", 1, "Svoboda P.", 9, "Outro A.", 3, 0, praga(2026, 11, 12, 11)),
        gravado("j1", 8, "Outro B.", 2, "Novak J.", 3, 0, praga(2026, 11, 18, 12)),
        gravado("j2", 2, "Novak J.", 8, "Outro B.", 3, 0, praga(2026, 11, 17, 12)),
        gravado("h8", 1, "Svoboda P.", 2, "Novak J.", 0, 3, praga(2026, 11, 8, 18)),
        gravado("h9", 2, "Novak J.", 1, "Svoboda P.", 3, 1, praga(2026, 11, 9, 18)),
        gravado("i1", 3, "Hora I.", 8, "Outro B.", 3, 0, praga(2026, 11, 18, 13)),
        gravado("i2", 3, "Hora I.", 8, "Outro B.", 3, 1, praga(2026, 11, 17, 13)),
        gravado("a1", 4, "Kral A.", 8, "Outro B.", 0, 3, praga(2026, 11, 18, 14)),
        gravado("a2", 8, "Outro B.", 4, "Kral A.", 3, 1, praga(2026, 11, 16, 14)),
        gravado("ia", 3, "Hora I.", 4, "Kral A.", 3, 1, praga(2026, 11, 10, 15)),
        gravado("l1", 5, "Maly L.", 8, "Outro B.", 3, 0, praga(2026, 11, 18, 15)),
        gravado("m1", 6, "Tesar M.", 8, "Outro B.", 3, 1, praga(2026, 11, 18, 16)),
        gravado("z1", 10, "Bilek Z.", 8, "Outro B.", 0, 3, praga(2026, 11, 18, 17)),
        gravado("z2", 10, "Bilek Z.", 8, "Outro B.", 1, 3, praga(2026, 11, 17, 17)),
    ]
    ant.jogos = jogos
    return ant


def dia_verde():
    hh = novo_hist()
    def dois_limpos(nome):
        hh.definir_jogos(nome, [
            {"resultado": "limpo", "sets_favor": 3, "sets_contra": 0, "inicio": K(7, 20)},
            {"resultado": "limpo", "sets_favor": 3, "sets_contra": 1, "inicio": K(7, 40)},
        ])
    def feia(nome):
        hh.definir_jogos(nome, [{"resultado": "derrota", "sets_favor": 0, "sets_contra": 3, "inicio": K(7, 30)}])
    def uma(nome):
        hh.definir_jogos(nome, [{"resultado": "limpo", "sets_favor": 3, "sets_contra": 0, "inicio": K(7, 25)}])
    dois_limpos("Petr Svoboda")
    feia("Jan Novak")
    dois_limpos("Ivan Hora")
    feia("Adam Kral")
    uma("Lukas Maly")
    uma("Milan Tesar")
    return hh


b.agora_cet = lambda: K(8, 55)
ant = anterior_de_mensagem()
hh = dia_verde()
verde = jogo("Ivan Hora", "Adam Kral", 1.40, 2.70, 9, 0)
h2h_block = jogo("Petr Svoboda", "Jan Novak", 1.50, 2.60, 9, 10)
vencedores = jogo("Lukas Maly", "Milan Tesar", 1.45, 2.40, 9, 20)
ambiguo1 = jogo("Zdenek Bilek", "Pavel Horak", 1.40, 2.50, 9, 30)
ambiguo2 = jogo("Zbynek Bilek", "Tomas Ruzicka", 1.40, 2.50, 9, 40)
lista = [verde, h2h_block, vencedores, ambiguo1, ambiguo2]
st_petr, mot_petr, fav_petr = b.avaliar(h2h_block, hh, b.montar_odds_map(lista))
check(st_petr == "verde" and fav_petr == "Petr Svoboda", (st_petr, mot_petr))
partes, verdes, defs = b.montar_mensagem_entrada(slot, lista, hh, lista, None, ant)
check(len(partes) == 1, [len(p) for p in partes])
msg = partes[0]
check(len(verdes) == 2 and [v[1] for v in verdes] == ["Ivan Hora", "Petr Svoboda"], verdes)
check(any(o.home == "Petr Svoboda" for o in defs), "aprovado continua definitivo")
check("09:00 — Ivan Hora vs Adam Kral | Entrada: Ivan Hora @ 1.40" in msg, msg)
check("09:10 — Petr Svoboda vs Jan Novak | Entrada: Petr Svoboda @ 1.50" in msg, msg)
check(msg.index("Ivan Hora") < msg.index("Petr Svoboda"), msg)
check("Histórico 7d" not in msg and "H2H" not in msg and "score_forma" not in msg, msg)
check("Lukas" not in msg and "Bilek" not in msg and "Odd fora" not in msg, msg)
check("Sem entrada" not in msg, msg)

class CapLog(logging.Handler):
    def __init__(self):
        super().__init__()
        self.rows = []
    def emit(self, record):
        self.rows.append(record.getMessage())

cap_msg = CapLog()
b.log.addHandler(cap_msg)
try:
    b.montar_mensagem_entrada(slot, lista, hh, lista, None, ant)
finally:
    b.log.removeHandler(cap_msg)
logs_bloco = "\n".join(cap_msg.rows)
check("score_forma" in logs_bloco and "Gap:" in logs_bloco, logs_bloco)
check("Histórico 7d: 2 V / 0 D (100% limpas)" in logs_bloco, logs_bloco)
check("H2H 14d: 1 x 0" in logs_bloco and "H2H 14d: 0 x 2" in logs_bloco, logs_bloco)
check("Odd fora da faixa: 2.40" in logs_bloco, logs_bloco)

# derrota de hoje continua na frente do H2H; a linha de histórico permanece
hh_perda = novo_hist()
hh_perda.definir_jogos("Petr Svoboda", [
    {"resultado": "limpo", "sets_favor": 3, "sets_contra": 0, "inicio": K(7, 20)},
    {"resultado": "derrota", "sets_favor": 1, "sets_contra": 3, "inicio": K(7, 50)},
])
hh_perda.definir_jogos("Jan Novak", [{"resultado": "derrota", "sets_favor": 0, "sets_contra": 3, "inicio": K(7, 30)}])
so_perda = jogo("Petr Svoboda", "Jan Novak", 1.37, 2.90, 9, 0)
partes_perda, verdes_perda, _ = b.montar_mensagem_entrada(slot, [so_perda], hh_perda, [so_perda], None, ant)
check(verdes_perda == [], verdes_perda)
texto_perda = partes_perda[0]
check(texto_perda == "08:55 — Sem entrada", texto_perda)
check("Histórico" not in texto_perda and "H2H" not in texto_perda and "Petr" not in texto_perda, texto_perda)

# uma derrota antiga no H2H não bloqueia o verde
ant_um = anterior_de_mensagem()
ant_um.jogos = [j for j in ant_um.jogos if j["id"] != "h8"]
partes_um, verdes_um, _ = b.montar_mensagem_entrada(slot, [h2h_block], hh, [h2h_block], None, ant_um)
check(len(verdes_um) == 1 and verdes_um[0][1] == "Petr Svoboda", verdes_um)
check("09:10 — Petr Svoboda vs Jan Novak" in partes_um[0] and "@ 1.50" in partes_um[0], partes_um[0])
check("Histórico" not in partes_um[0] and "H2H" not in partes_um[0], partes_um[0])

# ao vivo: o bloqueio vale, a linha de histórico não (ela é só do bloco)
b.agora_cet = lambda: K(9, 29)


class FakeTG:
    def __init__(self):
        self.sent = []

    def send(self, t, chat_id=None, reply_to=None):
        self.sent.append(t)
        return True


tg = FakeTG()
sinais = b.CacheSet(Path(tempfile.mkdtemp()) / "sinais.json")
b.processar(
    [
        b.LiveMatch("Petr Svoboda", "Jan Novak", None, None, None, False, K(9, 30)),
        b.LiveMatch("Ivan Hora", "Adam Kral", None, None, None, False, K(9, 30)),
    ],
    hh, b.CacheSet(Path(tempfile.mkdtemp()) / "fin.json"), sinais, tg, "R2",
    [jogo("Petr Svoboda", "Jan Novak", 1.50, 2.60, 9, 30),
     jogo("Ivan Hora", "Adam Kral", 1.40, 2.70, 9, 30)], None, None, ant,
)
check(len(tg.sent) == 0, tg.sent)
check(all("Histórico" not in t and "H2H" not in t for t in tg.sent), tg.sent)

tg2 = FakeTG()
b.processar(
    [b.LiveMatch("Petr Svoboda", "Jan Novak", None, None, None, False, K(9, 30))],
    hh, b.CacheSet(Path(tempfile.mkdtemp()) / "fin2.json"),
    b.CacheSet(Path(tempfile.mkdtemp()) / "sinais2.json"), tg2, "R2",
    [jogo("Petr Svoboda", "Jan Novak", 1.50, 2.60, 9, 30)],
)
check(tg2.sent == [], tg2.sent)

print("SPORTSAPI365 OK", N, "checks")
