"""Agenda do MoviOdds: 160 consultas/dia (odds + resultados), cache e uma retentativa.

requests é sempre simulado. O dia inteiro passa pelo loop de main() com o relógio no lugar.
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
check(AGENDA[0] == (0, 10, "resultados"), AGENDA[0])
check((7, 48, "resultados") in AGENDA and AGENDA[0] != (7, 48, "resultados"), "07:48 não é a primeira")
for h in range(24):
    antes = [m for hh, m in ODDS if hh == h and m < 55]
    check(any(0 < 55 - m <= 20 for m in antes), (h, antes))
    check((h, 55) in ODDS, h)
    check((h, 10) in RESULTADOS and (h, 48) in RESULTADOS, h)

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
check(b.slot_resultados_atual(b.TZ.localize(datetime(2026, 11, 20, 7, 47))) is None, "07:47 fora")
check(b.slot_moviodds_atual(b.TZ.localize(datetime(2026, 11, 20, 3, 55))) == "2026-11-20|03:55", "madrugada")

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
primeira = consultar(20, 8, 40, 2, 1_000.0)
check(len(http) == 1 and http[0]["headers"] == {"x-api-key": KEY}, http)
check(http[0]["params"] == {"sport": "table_tennis"} and http[0]["timeout"] == 20, http[0])
check(len(primeira) == 1 and primeira[0].odd_home == 1.5, primeira)
check(cache.quando == 1_000.0 and cache.lista is primeira, "cache gravado")
check(odds_logs() == ["[ODDS] consulta 08:40 -> 1 jogos"], odds_logs())
de_novo = consultar(20, 8, 40, 40, 1_040.0)
check(de_novo is primeira and len(http) == 1, "mesmo minuto não consulta de novo")
check(consultar(20, 8, 44, 0, 1_200.0) is primeira and len(http) == 1, "entre slots usa o cache")
check(consultar(20, 8, 48, 0, 1_500.0) is primeira and len(http) == 1, "minuto de resultados não pede odds")

queue.append(requests.ConnectionError("rede caiu"))
mantida = consultar(20, 8, 52, 1, 2_000.0)
check(mantida is primeira and cache.quando == 1_000.0, "erro não apaga o cache")
check(len(http) == 2 and odds_logs()[-1] == "[ODDS] consulta 08:52 -> 0 jogos", odds_logs())
check(consultar(20, 8, 52, 50, 2_050.0) is primeira and len(http) == 2, "ainda não deu 60 s")
check(consultar(20, 8, 52, 59, 2_059.0) is primeira and len(http) == 2, "59 s ainda é cedo")
queue.append(response(200, payload(1.8)))
retentou = consultar(20, 8, 53, 0, 2_060.0)
check(len(http) == 3 and retentou is not primeira and retentou[0].odd_home == 1.8, retentou)
check(cache.quando == 2_060.0 and cache.lista is retentou, "segunda tentativa entra no cache")
check(odds_logs()[-1] == "[ODDS] consulta 08:52 -> 1 jogos", odds_logs()[-1])
check(consultar(20, 8, 54, 0, 2_200.0) is retentou and len(http) == 3, "depois da retentativa, cache")

queue.append(requests.Timeout("timeout"))
check(consultar(20, 8, 55, 0, 3_000.0) is retentou and len(http) == 4, "1ª falha do slot 08:55")
queue.append(requests.ConnectionError("rede caiu de novo"))
check(consultar(20, 8, 56, 5, 3_065.0) is retentou and len(http) == 5, "2ª falha do mesmo slot")
check(cache.quando == 2_060.0, "duas falhas deixam a lista anterior")
check(consultar(20, 8, 58, 30, 3_150.0) is retentou and len(http) == 5, "terceira tentativa não existe")
check(consultar(20, 9, 11, 0, 3_400.0) == [] and len(http) == 5, "cache com mais de 20 min conta como sem odds")
check(cache.lista is retentou and cache.quando == 2_060.0, "a lista antiga fica guardada, mas não é usada")

queue.append(response(200, {"matches": []}))
vazia = consultar(20, 9, 40, 0, 4_000.0)
check(vazia == [] and cache.lista is vazia and cache.quando == 4_000.0, "vazio sem erro substitui o cache")
check(odds_logs()[-1] == "[ODDS] consulta 09:40 -> 0 jogos", odds_logs()[-1])
check(consultar(20, 9, 41, 30, 4_090.0) is vazia and len(http) == 6, "vazio legítimo não repete")

sem_chave = b.MoviOdds("")
cache_sem = b.CacheOdds()
antes = len(http)
nada = b.obter_odds(sem_chave, cache_sem, now=cet(20, 9, 52, 0), agora_ts=5_000.0)
check(nada == [] and len(http) == antes, "sem chave não chama a rede")
check(odds_logs()[-1] == "[ODDS] consulta 09:52 -> 0 jogos", odds_logs()[-1])
check(b.obter_odds(sem_chave, cache_sem, now=cet(20, 9, 53, 0), agora_ts=5_090.0) is nada and len(http) == antes,
      "sem chave também é uma consulta por slot")
check(all(KEY not in m for _, m in cap.rows), "log sem a chave")
b.log.removeHandler(cap)

# ---------- dia simulado: o loop de main() consulta exatamente 52 vezes ----------
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
    ent_calls.append((b.agora_cet(), a[5]))
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
        # falha o envio da entrada para o loop repetir hh:55–hh:59 com o mesmo cache
        return not text.startswith("🎯 <b>ENTRADA")
    def get_me(self):
        return {"username": "filtrobot", "id": 999}
    def get_updates(self, offset=0):
        return []

b.Telegram = TG
b.ScoreMondo.fetch = lambda self: [b.LiveMatch("P Um", "Q Dois", 0, 1, "S1", False)]
b.ScoreMondo.fetch_fixtures = lambda self: []
b.ScoreMondo.fetch_results = lambda self: []

inicio = cet(20, 0, 0, 0)
limite = cet(21, 7, 48, 0)
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
for day in (20, 21):
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
check(ent_calls, "entrada chamou processar_entrada")
confere_cache(ent_calls)

primeira_consulta = http_dia[0]["quando"]
check(primeira_consulta.hour == 0 and primeira_consulta.minute == 10, primeira_consulta)
check(http_dia[0]["url"] == b.MoviOdds.RESULTS_URL, "a primeira do dia é resultado, não 07:48")
check(any(c["quando"].day == 20 and c["quando"].hour == 7 and c["quando"].minute == 48
          and c["url"] == b.MoviOdds.RESULTS_URL for c in http_dia), "07:48 permanece")
check(all(c["quando"] >= primeira_consulta for c in http_dia), "nada antes das 00:10")

for h in range(24):
    repetidas = [odds for dt, odds in ent_calls if dt.day == 20 and dt.hour == h and dt.minute >= 55]
    check(len(repetidas) >= 2, (h, len(repetidas)))
    check(all(odds is repetidas[0] for odds in repetidas), h)
    da_entrada = [lista for dt, lista in fetch_calls if dt.day == 20 and dt.hour == h and dt.minute == 55]
    check(len(da_entrada) == 1 and repetidas[0] is da_entrada[0], h)
    check(not any(dt.day == 20 and dt.hour == h and 56 <= dt.minute <= 59 for dt, _ in fetch_calls), h)

dia20 = [c for c in http_dia if c["quando"].day == 20]
check(dia20[-1]["quando"].hour == 23 and dia20[-1]["quando"].minute == 55, dia20[-1]["quando"])
check(dia20[-1]["url"] == b.MoviOdds.URL, "23:55 pede odds")
check(any(c["quando"].hour == 2 and c["quando"].minute == 10 for c in dia20), "madrugada tem resultado")
check(len(dia20) <= 161, len(dia20))

print("ODDS AGENDA OK", N, "checks")
