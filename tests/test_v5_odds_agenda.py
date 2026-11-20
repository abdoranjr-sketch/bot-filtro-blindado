"""Agenda do MoviOdds: 52 consultas/dia, cache entre slots, retentativa única se a API falha.

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

GRADE = (
    (0, 48), (0, 54), (0, 55),
    (1, 0), (1, 6), (1, 12), (1, 18), (1, 20), (1, 24),
    (1, 30), (1, 36), (1, 42), (1, 48),
)
ESPERADOS = [(h + off, minute) for h in (8, 12, 16, 20) for off, minute in GRADE]

check(b.MOVIODDS_MINUTOS == GRADE, b.MOVIODDS_MINUTOS)
check(b.MOVIODDS_MAX_TENTATIVAS == 2 and b.MOVIODDS_RETRY_S == 60, "limites da retentativa")
check(len(ESPERADOS) == 52 and len(set(ESPERADOS)) == 52, len(ESPERADOS))
check(all(8 <= h <= 21 for h, _ in ESPERADOS), ESPERADOS)

slots = set(ESPERADOS)
for hora in range(24):
    for minuto in range(60):
        got = b.slot_moviodds_atual(b.TZ.localize(datetime(2026, 11, 20, hora, minuto)))
        if (hora, minuto) in slots:
            check(got == f"2026-11-20|{hora:02d}:{minuto:02d}", got)
        else:
            check(got is None, (hora, minuto, got))
# hh:00–hh:47 da 1ª rodada fica de fora; :20 entra, :18 e :24 também, :28 não
for h in (8, 12, 16, 20):
    check(b.slot_moviodds_atual(b.TZ.localize(datetime(2026, 11, 20, h, 0))) is None, h)
    check(b.slot_moviodds_atual(b.TZ.localize(datetime(2026, 11, 20, h, 47))) is None, h)
    check(b.slot_moviodds_atual(b.TZ.localize(datetime(2026, 11, 20, h + 1, 20))) == f"2026-11-20|{h+1:02d}:20", h)
    check(b.slot_moviodds_atual(b.TZ.localize(datetime(2026, 11, 20, h + 1, 28))) is None, h)

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
primeira = consultar(20, 8, 48, 2, 1_000.0)
check(len(http) == 1 and http[0]["headers"] == {"x-api-key": KEY}, http)
check(http[0]["params"] == {"sport": "table_tennis"} and http[0]["timeout"] == 20, http[0])
check(len(primeira) == 1 and primeira[0].odd_home == 1.5, primeira)
check(cache.quando == 1_000.0 and cache.lista is primeira, "cache gravado")
check(odds_logs() == ["[ODDS] consulta 08:48 -> 1 jogos"], odds_logs())
de_novo = consultar(20, 8, 48, 40, 1_040.0)
check(de_novo is primeira and len(http) == 1, "mesmo minuto não consulta de novo")
check(consultar(20, 8, 50, 0, 1_200.0) is primeira and len(http) == 1, "entre slots usa o cache")

queue.append(requests.ConnectionError("rede caiu"))
mantida = consultar(20, 9, 0, 1, 2_000.0)
check(mantida is primeira and cache.quando == 1_000.0, "erro não apaga o cache")
check(len(http) == 2 and odds_logs()[-1] == "[ODDS] consulta 09:00 -> 0 jogos", odds_logs())
check(consultar(20, 9, 0, 50, 2_050.0) is primeira and len(http) == 2, "ainda não deu 60 s")
check(consultar(20, 9, 0, 59, 2_059.0) is primeira and len(http) == 2, "59 s ainda é cedo")
queue.append(response(200, payload(1.8)))
retentou = consultar(20, 9, 1, 0, 2_060.0)
check(len(http) == 3 and retentou is not primeira and retentou[0].odd_home == 1.8, retentou)
check(cache.quando == 2_060.0 and cache.lista is retentou, "segunda tentativa entra no cache")
check(odds_logs()[-1] == "[ODDS] consulta 09:00 -> 1 jogos", odds_logs()[-1])
check(consultar(20, 9, 3, 0, 2_200.0) is retentou and len(http) == 3, "depois da retentativa, cache")

queue.append(requests.Timeout("timeout"))
check(consultar(20, 9, 6, 0, 3_000.0) is retentou and len(http) == 4, "1ª falha do slot 09:06")
queue.append(requests.ConnectionError("rede caiu de novo"))
check(consultar(20, 9, 7, 5, 3_065.0) is retentou and len(http) == 5, "2ª falha do mesmo slot")
check(cache.quando == 2_060.0, "duas falhas deixam a lista anterior")
check(consultar(20, 9, 8, 30, 3_150.0) is retentou and len(http) == 5, "terceira tentativa não existe")
check(consultar(20, 9, 11, 0, 3_400.0) is retentou and len(http) == 5, "segue no cache até o próximo slot")

queue.append(response(200, {"matches": []}))
vazia = consultar(20, 9, 12, 0, 4_000.0)
check(vazia == [] and cache.lista is vazia and cache.quando == 4_000.0, "vazio sem erro substitui o cache")
check(odds_logs()[-1] == "[ODDS] consulta 09:12 -> 0 jogos", odds_logs()[-1])
check(consultar(20, 9, 13, 30, 4_090.0) is vazia and len(http) == 6, "vazio legítimo não repete")

sem_chave = b.MoviOdds("")
cache_sem = b.CacheOdds()
antes = len(http)
nada = b.obter_odds(sem_chave, cache_sem, now=cet(20, 9, 18, 0), agora_ts=5_000.0)
check(nada == [] and len(http) == antes, "sem chave não chama a rede")
check(odds_logs()[-1] == "[ODDS] consulta 09:18 -> 0 jogos", odds_logs()[-1])
check(b.obter_odds(sem_chave, cache_sem, now=cet(20, 9, 19, 0), agora_ts=5_090.0) is nada and len(http) == antes,
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
    if url != b.MoviOdds.URL:
        raise HTTPBlocked(url)
    seq["n"] += 1
    http_dia.append({
        "quando": b.agora_cet(),
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
limite = cet(21, 8, 48, 0)
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

check(len(fetch_calls) == 52, len(fetch_calls))
check(len(http_dia) == 52, len(http_dia))
check([(dt.month, dt.day, dt.hour, dt.minute) for dt, _ in fetch_calls]
      == [(11, 20, h, m) for h, m in ESPERADOS],
      [(dt.hour, dt.minute) for dt, _ in fetch_calls])
check(all(c["headers"] == {"x-api-key": KEY} and c["params"] == {"sport": "table_tennis"}
          and c["timeout"] == 20 for c in http_dia), http_dia[0])
for dt, _ in fetch_calls:
    if dt.hour in b.HORAS_ENTRADA:
        check(dt.minute >= 48, dt)

logs_dia = [m for lvl, m in cap_dia.rows if m.startswith("[ODDS]")]
check(logs_dia == [f"[ODDS] consulta {h:02d}:{m:02d} -> 1 jogos" for h, m in ESPERADOS], logs_dia[:3])
check(all(KEY not in m for _, m in cap_dia.rows), "dia sem vazar a chave")

def confere_cache(chamadas):
    fi = 0
    ativo = None
    for dt, odds in chamadas:
        while fi < len(fetch_calls) and fetch_calls[fi][0] <= dt:
            ativo = fetch_calls[fi][1]
            fi += 1
        if ativo is None:
            check(odds == [], (dt, odds))
        else:
            check(odds is ativo, (dt, getattr(ativo[0], "odd_home", None), getattr(odds[0], "odd_home", None) if odds else None))

check(proc_calls, "R1/R2 chamou processar")
confere_cache(proc_calls)
check(ent_calls, "entrada chamou processar_entrada")
confere_cache(ent_calls)

primeira_consulta = fetch_calls[0][0]
antes = [odds for dt, odds in proc_calls if dt < primeira_consulta]
check(antes and all(odds is antes[0] and odds == [] for odds in antes), "R1 antes das 08:48 usa cache vazio")
check(all(dt.hour == 8 and dt.minute < 48 for dt, _ in proc_calls if dt < primeira_consulta), "só a 1ª rodada das 08")

for h in (8, 12, 16, 20):
    repetidas = [odds for dt, odds in ent_calls if dt.hour == h and dt.minute >= 55]
    check(len(repetidas) >= 2, (h, len(repetidas)))
    check(all(odds is repetidas[0] for odds in repetidas), h)
    da_entrada = [lista for dt, lista in fetch_calls if dt.hour == h and dt.minute == 55]
    check(len(da_entrada) == 1 and repetidas[0] is da_entrada[0], h)
    check(not any(dt.hour == h and 56 <= dt.minute <= 59 for dt, _ in fetch_calls), h)

ultima = fetch_calls[-1]
check(ultima[0].hour == 21 and ultima[0].minute == 48, ultima[0])
manha = [(dt, odds) for dt, odds in proc_calls if dt.day == 21]
check(manha and all(dt.hour == 8 and dt.minute < 48 and odds is ultima[1] for dt, odds in manha),
      "08:00–08:47 do dia seguinte reusa o cache das 21:48, sem consulta nova")
check(all(dt.day == 20 for dt, _ in fetch_calls), "nenhuma consulta no dia seguinte antes das 08:48")

print("ODDS AGENDA OK", N, "checks")
