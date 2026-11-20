"""Agenda do MoviOdds: 160 consultas/dia (odds a cada 15 min + resultados), cache e uma retentativa.

requests é sempre simulado. O dia inteiro passa pelo loop de main() com o relógio no lugar.
Jogos às :00 e às :30 geram entrada cerca de 5 min antes, em qualquer modo.
"""
import os, sys, tempfile, json, logging
from datetime import datetime, timedelta

D = tempfile.mkdtemp()
KEY = "odds-agenda-test-key"
os.environ.update({
    "DATA_DIR": D,
    "TELEGRAM_TOKEN": "x",
    "TELEGRAM_CHAT_ID": "111",
    "TELEGRAM_GROUP_ID": "-100999",
    "MOVIODDS_KEY": KEY,
})
os.environ.pop("MOVIODDS_KEY_2", None)
os.environ.pop("SPORTSAPI365_KEY", None)
os.environ.pop("TELEGRAM_OWNER_ID", None)
os.environ.pop("TELEGRAM_DISCUSSION_ID", None)
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
import requests

class HTTPBlocked(BaseException):
    pass

def _blocked(*a, **k):
    raise HTTPBlocked("real HTTP call attempted")

requests.get = requests.post = _blocked
import bot_filtro_blindado_v5 as b

N = 0
def check(c, m):
    global N
    assert c, m
    N += 1

AGENDA = b.agenda_moviodds()
ODDS = {(h, m) for h, m, k in AGENDA if k == "odds"}
RESULTADOS = {(h, m) for h, m, k in AGENDA if k == "resultados"}

check(b.MOVIODDS_MINUTOS == tuple(sorted(ODDS | RESULTADOS)), b.MOVIODDS_MINUTOS)
check(b.MOVIODDS_MAX_TENTATIVAS == 2 and b.MOVIODDS_RETRY_S == 60, "limites da retentativa")
check(len(AGENDA) == 160 and len(set((h, m) for h, m, _ in AGENDA)) == 160, len(AGENDA))
check(b.MOVIODDS_CHAMADAS_DIA == 160 and b.MOVIODDS_CHAMADAS_DIA <= 161, b.MOVIODDS_CHAMADAS_DIA)
check(b.MOVIODDS_CHAMADAS_MES_31 == 160 * 31 == 4960 and b.MOVIODDS_CHAMADAS_MES_31 < 5000,
      b.MOVIODDS_CHAMADAS_MES_31)
check({h for h, _, _ in AGENDA} == set(range(24)), "as 24 horas")
check(AGENDA[0] == (0, 0, "odds"), AGENDA[0])
check(len(ODDS) == 96 and len(RESULTADOS) == 64, (len(ODDS), len(RESULTADOS)))
for h in range(24):
    check({m for hh, m in ODDS if hh == h} == {0, 15, 30, 45}, h)
    check((h, 10) in RESULTADOS and (h, 40) in RESULTADOS, h)
    # envio ~5 min antes de :00 e de :30: a odd mais recente tem menos de 20 min
    for minuto in (0, 30):
        envio_m = (minuto - 5) % 60
        envio_h = h if minuto >= 5 else (h - 1) % 24
        candidatas = []
        for hh, mm in ODDS:
            if hh == envio_h and mm <= envio_m:
                candidatas.append(envio_m - mm)
            elif minuto < 5 and hh == envio_h and envio_h != h:
                candidatas.append((60 - mm) + envio_m)
        check(candidatas and min(candidatas) < 20, (h, minuto, candidatas))

for hora in range(24):
    for minuto in range(60):
        quando = b.TZ.localize(datetime(2026, 11, 20, hora, minuto))
        got_o = b.slot_moviodds_atual(quando)
        got_r = b.slot_resultados_atual(quando)
        chave = f"2026-11-20|{hora:02d}:{minuto:02d}"
        if (hora, minuto) in ODDS:
            check(got_o == chave and got_r is None, (hora, minuto, got_o, got_r))
        elif (hora, minuto) in RESULTADOS:
            check(got_r == chave and got_o is None, (hora, minuto, got_o, got_r))
        else:
            check(got_o is None and got_r is None, (hora, minuto, got_o, got_r))
check(b.slot_moviodds_atual(b.TZ.localize(datetime(2026, 11, 20, 0, 10))) is None, "00:10 é resultado")
check(b.slot_resultados_atual(b.TZ.localize(datetime(2026, 11, 20, 0, 10))) == "2026-11-20|00:10", "00:10")
check(b.slot_moviodds_atual(b.TZ.localize(datetime(2026, 11, 20, 3, 45))) == "2026-11-20|03:45", "madrugada")

def response(status, payload=None, body=None):
    r = requests.Response()
    r.status_code = status
    r.url = b.MoviOdds.URL + "?sport=table_tennis"
    r.reason = "OK" if status < 400 else "Nope"
    r.encoding = "utf-8"
    r.headers["Content-Type"] = "application/json"
    if body is None:
        body = json.dumps(payload if payload is not None else {"matches": []}).encode()
    r._content = body
    return r

def payload(odd):
    return {
        "matches": [{
            "league": "Czech Liga Pro",
            "home": "A Alfa",
            "away": "B Beta",
            "in_play": False,
            "kickoff_utc": "2026-11-20T08:00:00Z",
            "quotes": [
                {"group_name": "To Win Match", "side": "A Alfa", "odds_dec": odd},
                {"group_name": "To Win Match", "side": "B Beta", "odds_dec": 2.5},
            ],
        }]
    }

class Capture(logging.Handler):
    def __init__(self):
        super().__init__(level=logging.DEBUG)
        self.rows = []
    def emit(self, record):
        self.rows.append((record.levelname, record.getMessage()))

def cet(day, h, m, s=0):
    return b.TZ.localize(datetime(2026, 11, day, h, m, s))

# ---------- cache, erro e retentativa (sem o loop) ----------
http = []
queue = []

def get(url, params=None, headers=None, timeout=None, **extra):
    http.append({
        "url": url, "params": dict(params or {}), "headers": dict(headers or {}),
        "timeout": timeout, "extra": extra,
    })
    if url != b.MoviOdds.URL:
        raise HTTPBlocked(url)
    if not queue:
        raise HTTPBlocked("chamada HTTP extra")
    item = queue.pop(0)
    if isinstance(item, Exception):
        raise item
    return item

b.requests.get = get
cap = Capture()
b.log.addHandler(cap)
b.log.propagate = False
client = b.MoviOdds(KEY)
cache = b.CacheOdds()

def consultar(day, h, m, s, ts):
    return b.obter_odds(client, cache, now=cet(day, h, m, s), agora_ts=ts)

def odds_logs():
    return [m for lvl, m in cap.rows if m.startswith("[ODDS]")]

queue.append(response(200, payload(1.5)))
primeira = consultar(20, 8, 30, 2, 1_000.0)
check(len(http) == 1 and http[0]["headers"] == {"x-api-key": KEY}, http)
check(http[0]["params"] == {"sport": "table_tennis"} and http[0]["timeout"] == 20, http[0])
check(len(primeira) == 1 and primeira[0].odd_home == 1.5, primeira)
check(cache.quando == 1_000.0 and cache.lista is primeira, "cache gravado")
check(odds_logs() == ["[ODDS] consulta 08:30 -> 1 jogos"], odds_logs())
de_novo = consultar(20, 8, 30, 40, 1_040.0)
check(de_novo is primeira and len(http) == 1, "mesmo minuto não consulta de novo")
check(consultar(20, 8, 37, 0, 1_200.0) is primeira and len(http) == 1, "entre slots usa o cache")
check(consultar(20, 8, 40, 0, 1_500.0) is primeira and len(http) == 1, "minuto de resultados não pede odds")

queue.append(requests.ConnectionError("rede caiu"))
mantida = consultar(20, 8, 45, 1, 2_000.0)
check(mantida is primeira and cache.quando == 1_000.0, "erro não apaga o cache")
check(len(http) == 2 and odds_logs()[-1] == "[ODDS] consulta 08:45 -> 0 jogos", odds_logs())
check(consultar(20, 8, 45, 50, 2_050.0) is primeira and len(http) == 2, "ainda não deu 60 s")
check(consultar(20, 8, 45, 59, 2_059.0) is primeira and len(http) == 2, "59 s ainda é cedo")
queue.append(response(200, payload(1.8)))
retentou = consultar(20, 8, 46, 0, 2_060.0)
check(len(http) == 3 and retentou is not primeira and retentou[0].odd_home == 1.8, retentou)
check(cache.quando == 2_060.0 and cache.lista is retentou, "segunda tentativa entra no cache")
check(odds_logs()[-1] == "[ODDS] consulta 08:45 -> 1 jogos", odds_logs()[-1])
check(consultar(20, 8, 47, 0, 2_200.0) is retentou and len(http) == 3, "depois da retentativa, cache")

queue.append(requests.Timeout("timeout"))
check(consultar(20, 9, 0, 0, 3_000.0) is retentou and len(http) == 4, "1ª falha do slot 09:00")
queue.append(requests.ConnectionError("rede caiu de novo"))
check(consultar(20, 9, 1, 5, 3_065.0) is retentou and len(http) == 5, "2ª falha do mesmo slot")
check(cache.quando == 2_060.0, "duas falhas deixam a lista anterior")
check(consultar(20, 9, 3, 30, 3_150.0) is retentou and len(http) == 5, "terceira tentativa não existe")
check(consultar(20, 9, 11, 0, 3_400.0) == [] and len(http) == 5, "cache com mais de 20 min conta como sem odds")
check(cache.lista is retentou and cache.quando == 2_060.0, "a lista antiga fica guardada, mas não é usada")

queue.append(response(200, {"matches": []}))
vazia = consultar(20, 9, 15, 0, 4_000.0)
check(vazia == [] and cache.lista is vazia and cache.quando == 4_000.0, "vazio sem erro substitui o cache")
check(odds_logs()[-1] == "[ODDS] consulta 09:15 -> 0 jogos", odds_logs()[-1])
check(consultar(20, 9, 16, 30, 4_090.0) is vazia and len(http) == 6, "vazio legítimo não repete")

sem_chave = b.MoviOdds("")
cache_sem = b.CacheOdds()
antes = len(http)
nada = b.obter_odds(sem_chave, cache_sem, now=cet(20, 9, 30, 0), agora_ts=5_000.0)
check(nada == [] and len(http) == antes, "sem chave não chama a rede")
check(odds_logs()[-1] == "[ODDS] consulta 09:30 -> 0 jogos", odds_logs()[-1])
check(b.obter_odds(sem_chave, cache_sem, now=cet(20, 9, 31, 0), agora_ts=5_090.0) is nada and len(http) == antes,
      "sem chave também é uma consulta por slot")
check(all(KEY not in m for _, m in cap.rows), "log sem a chave")
b.log.removeHandler(cap)

# ---------- cache em DATA_DIR e uma consulta imediata no reinício ----------
boot_http = {"n": 0}

def get_boot(url, params=None, headers=None, timeout=None, **extra):
    if url != b.MoviOdds.URL:
        raise HTTPBlocked(url)
    boot_http["n"] += 1
    return response(200, payload(1.4))

b.requests.get = get_boot
cap_boot = Capture()
b.log.addHandler(cap_boot)
jogo_1630 = b.OddsMatch("Michal Z", "Richard W", 1.4, 2.6, False, None, cet(20, 16, 30))
fresco = b.CacheOdds(persistir=True)
b.obter_odds(b.MoviOdds(KEY), fresco, now=cet(20, 16, 15), agora_ts=10_000.0)
check(boot_http["n"] == 1 and b.ODDS_CACHE_FILE.exists(), "gravou o cache")
outro = b.CacheOdds(persistir=True)
check(outro.quando == 10_000.0 and len(outro.lista) == 1 and outro.lista[0].odd_home == 1.4, outro.lista)
reusado = b.obter_odds(b.MoviOdds(KEY), outro, now=cet(20, 16, 20), agora_ts=10_300.0)
check(reusado[0].odd_home == 1.4 and boot_http["n"] == 1, "reinício reaproveita odds de menos de 20 min")

velho = b.CacheOdds(persistir=True)
velho.quando = 10_000.0
velho.salvar()
b.agora_cet = lambda: cet(20, 16, 16)
check(b.modo_atual() == "R2", b.modo_atual())
renascido = b.CacheOdds(persistir=True)
saiu = b.talvez_odds_imediatas(b.MoviOdds(KEY), renascido, [jogo_1630], now=cet(20, 16, 16), agora_ts=10_000.0 + 21 * 60)
check(boot_http["n"] == 2 and len(saiu) == 1, (boot_http["n"], saiu))
check(any(m == "[ODDS] consulta 16:16 -> 1 jogos" for _, m in cap_boot.rows), cap_boot.rows)
segunda = b.CacheOdds(persistir=True)
segunda.quando = 1.0
segunda.salvar()
parado = b.talvez_odds_imediatas(b.MoviOdds(KEY), segunda, [jogo_1630], now=cet(20, 16, 18), agora_ts=10_000.0 + 40 * 60)
check(boot_http["n"] == 2 and parado == [], "o dia só gasta uma consulta imediata")

# 14:55 com jogos às 16:00/16:30 não é "hora vazia": o bloco sai ~5 min antes, mesmo em R2
quadro = [jogo_1630, b.OddsMatch("A Alfa", "B Beta", 1.5, 2.2, False, None, cet(20, 16, 0))]
b.agora_cet = lambda: cet(20, 14, 55)
check(b.modo_atual() == "ENTRADA", b.modo_atual())
check(b.blocos_devidos(quadro) == [], b.blocos_devidos(quadro))
b.agora_cet = lambda: cet(20, 16, 25)
check(b.modo_atual() == "R2", b.modo_atual())
check([k for k, _ in b.blocos_devidos(quadro)] == ["2026-11-20|16:30"], b.blocos_devidos(quadro))
so_fixture = [b.OddsMatch("So Fixt", "Xis", None, None, False, None, cet(20, 17, 0))]
unido = b.fonte_entrada(so_fixture, [jogo_1630])
check({o.home for o in unido} == {"So Fixt", "Michal Z"}, [o.home for o in unido])
check([k for k, _ in b.blocos_devidos(unido)] == ["2026-11-20|16:30"], "odds não somem atrás do fixture")
alias = b.MoviOdds.parse({"matches": [{
    "league": "Czechia - Liga Pro", "home": "A Alfa", "away": "B Beta", "in_play": False,
    "kickoff_utc": "2026-11-20T15:30:00Z",
    "quotes": [
        {"group_name": "Game", "line": "To Win", "side": "A Alfa", "odds_dec": 1.45},
        {"group_name": "Game", "line": "To Win", "side": "B Beta", "odds_dec": 2.6},
    ],
}, {"league": "TT Elite Series", "home": "Zeta", "away": "Yps", "quotes": []}]})
check(len(alias) == 1 and alias[0].odd_home == 1.45 and alias[0].odd_away == 2.6, alias)
b.log.removeHandler(cap_boot)
for nome in ("odds_cache_v5.json", "odds_boot_v5.json", "odds_cache_v5.tmp", "odds_boot_v5.tmp"):
    caminho = b.DATA_DIR / nome
    if caminho.exists():
        caminho.unlink()

# ---------- dia simulado: grade de 160 e um bloco :00 e :30 por hora ----------
fetch_calls = []
real_fetch = b.MoviOdds.fetch_czech
def spy_fetch(self):
    result = real_fetch(self)
    fetch_calls.append((b.agora_cet(), result))
    return result
b.MoviOdds.fetch_czech = spy_fetch

proc_calls = []
real_proc = b.processar
def spy_proc(*a, **k):
    proc_calls.append((b.agora_cet(), a[6]))
    return real_proc(*a, **k)
b.processar = spy_proc

ent_calls = []
real_ent = b.processar_entrada
def spy_ent(*a, **k):
    ent_calls.append((b.agora_cet(), b.modo_atual(), a[0]))
    return real_ent(*a, **k)
b.processar_entrada = spy_ent

http_dia = []
seq = {"n": 0}
def get_dia(url, params=None, headers=None, timeout=None, **extra):
    if url not in (b.MoviOdds.URL, b.MoviOdds.RESULTS_URL):
        raise HTTPBlocked(url)
    seq["n"] += 1
    http_dia.append({
        "quando": b.agora_cet(),
        "url": url,
        "params": dict(params or {}),
        "headers": dict(headers or {}),
        "timeout": timeout,
    })
    return response(200, payload(1.5 + seq["n"]))
b.requests.get = get_dia

class TG:
    def __init__(self, token, chat_id):
        self.chat_id = str(chat_id)
        self.conflitos_seguidos = 0
    def send(self, text, chat_id=None, reply_to=None):
        # falha o envio para o bloco repetir dentro da janela de ~5 min, com o mesmo cache
        return "Sem entrada" not in text and "\nEntrada:" not in text
    def get_me(self):
        return {"username": "filtrobot", "id": 999}
    def get_updates(self, offset=0):
        return []

b.Telegram = TG
b.ScoreMondo.fetch = lambda self: [b.LiveMatch("P Um", "Q Dois", 0, 1, "S1", False)]
def fixtures_liga(self):
    out = []
    for day in (20, 21):
        for h in range(24):
            for m in (0, 30):
                out.append(b.OddsMatch(
                    f"Casa{day}{h:02d}{m:02d}", f"Fora{day}{h:02d}{m:02d}",
                    None, None, False, None, cet(day, h, m)))
    return out
b.ScoreMondo.fetch_fixtures = fixtures_liga
b.ScoreMondo.fetch_results = lambda self: []

inicio = cet(19, 23, 45, 0)
limite = cet(21, 0, 5, 0)
clock = {"dt": inicio, "ts": 1_700_000_000.0}
b.agora_cet = lambda: clock["dt"]
b.time.time = lambda: clock["ts"]
def dormir(sec):
    clock["ts"] += sec
    clock["dt"] = clock["dt"] + timedelta(seconds=sec)
    if clock["dt"] >= limite:
        raise KeyboardInterrupt
b.time.sleep = dormir

cap_dia = Capture()
b.log.addHandler(cap_dia)
for handler in logging.getLogger().handlers:
    if isinstance(handler, logging.StreamHandler):
        handler.setLevel(logging.ERROR)
b.main()
b.log.removeHandler(cap_dia)

esperados = []
for day in (19, 20, 21):
    for h, m, kind in AGENDA:
        dt = cet(day, h, m)
        if inicio <= dt < limite:
            esperados.append((dt, kind))
por_dia = {}
for dt, _kind in esperados:
    por_dia[dt.day] = por_dia.get(dt.day, 0) + 1
check(por_dia[20] == 160 and all(n <= 161 for n in por_dia.values()), por_dia)
check(por_dia[20] * 31 <= 4960, por_dia)

check(len(http_dia) == len(esperados), (len(http_dia), len(esperados)))
check([(c["quando"], "odds" if c["url"] == b.MoviOdds.URL else "resultados") for c in http_dia]
      == esperados, (http_dia[0], esperados[0], http_dia[-1]))
odds_esperados = [dt for dt, kind in esperados if kind == "odds"]
check([dt for dt, _ in fetch_calls] == odds_esperados, (len(fetch_calls), len(odds_esperados)))
check(all(c["headers"] == {"x-api-key": KEY} and c["timeout"] == 20
          and c["params"].get("sport") == "table_tennis" for c in http_dia), http_dia[0])
check(all(("date" in c["params"]) == (c["url"] == b.MoviOdds.RESULTS_URL) for c in http_dia), "date só em resultados")

logs_odds = [m for lvl, m in cap_dia.rows if m.startswith("[ODDS]")]
logs_res = [m for lvl, m in cap_dia.rows if m.startswith("[RESULTADOS]")]
check(logs_odds == [f"[ODDS] consulta {dt.hour:02d}:{dt.minute:02d} -> 1 jogos" for dt in odds_esperados], logs_odds[:2])
check(len(logs_res) == len(esperados) - len(odds_esperados), (len(logs_res), len(esperados)))
check(all(KEY not in m for _, m in cap_dia.rows), "dia sem vazar a chave")

def confere_cache(chamadas):
    fi = 0
    ativo = None
    ativo_dt = None
    for dt, odds in chamadas:
        while fi < len(fetch_calls) and fetch_calls[fi][0] <= dt:
            ativo_dt, ativo = fetch_calls[fi]
            fi += 1
        velho = ativo_dt is not None and (dt - ativo_dt).total_seconds() > 20 * 60
        if ativo is None or velho:
            check(odds == [], (dt, ativo_dt))
        else:
            check(odds is ativo, (dt, getattr(ativo[0], "odd_home", None),
                                  getattr(odds[0], "odd_home", None) if odds else None))

check(proc_calls, "R1/R2 chamou processar")
confere_cache(proc_calls)

primeira_consulta = http_dia[0]["quando"]
check(primeira_consulta == cet(19, 23, 45) and http_dia[0]["url"] == b.MoviOdds.URL, primeira_consulta)
dia20_primeira = next(c for c in http_dia if c["quando"].day == 20)
check(dia20_primeira["quando"] == cet(20, 0, 0) and dia20_primeira["url"] == b.MoviOdds.URL, dia20_primeira)
check(all(c["quando"] >= inicio for c in http_dia), "nada antes do relógio")

blocos = {}
for dt, modo, slot in ent_calls:
    blocos.setdefault(slot, []).append((dt, modo))
esperados_blocos = [f"2026-11-20|{h:02d}:{m:02d}" for h in range(24) for m in (0, 30)]
esperados_blocos.append("2026-11-21|00:00")
check(set(esperados_blocos) <= set(blocos), sorted(set(esperados_blocos) - set(blocos))[:8])
modos = {modo for _, modo, _ in ent_calls}
check({"R2", "ENTRADA", "FORA"} <= modos, modos)
for slot, chamadas in blocos.items():
    if slot not in esperados_blocos:
        continue
    check(len(chamadas) >= 2, (slot, len(chamadas)))
    for dt, modo in chamadas:
        anteriores = [fdt for fdt, _ in fetch_calls if fdt <= dt]
        check(anteriores, (slot, dt))
        idade = (dt - anteriores[-1]).total_seconds()
        check(0 <= idade <= 20 * 60, (slot, dt, idade, modo))
        delta = (b.instante_bloco(slot) - dt).total_seconds()
        check(b.ENTRADA_ANTES_MIN_S <= delta <= b.ENTRADA_ANTES_MAX_S, (slot, dt, delta, modo))

logs_entrada = [m for _, m in cap_dia.rows if m.startswith("[ENTRADA ") and "jogos avaliados" in m]
check(logs_entrada, "log de entrada")
check(all("aprovados" in m for m in logs_entrada), logs_entrada[0])
check(any(m.startswith("[ENTRADA 2026-11-20|00:30]") for m in logs_entrada), "bloco :30")
check(any(m.startswith("[ENTRADA 2026-11-20|16:00]") for m in logs_entrada), "bloco :00")
check(not any("sem jogos da Czech Liga Pro nesta hora" in m for _, m in cap_dia.rows), "sem o falso vazio")

dia20 = [c for c in http_dia if c["quando"].day == 20]
check(dia20[-1]["quando"].hour == 23 and dia20[-1]["quando"].minute == 45, dia20[-1]["quando"])
check(dia20[-1]["url"] == b.MoviOdds.URL, "23:45 pede odds")
check(any(c["quando"].hour == 2 and c["quando"].minute == 10 for c in dia20), "madrugada tem resultado")
check(len(dia20) <= 161, len(dia20))
check(not any("|inicio" in (c["quando"].strftime("%H:%M")) for c in http_dia), "grade não ganha consulta extra")

print("ODDS AGENDA OK", N, "checks")
