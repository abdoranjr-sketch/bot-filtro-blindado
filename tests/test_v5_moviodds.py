"""Fallback da chave reserva do MoviOdds. requests.get é sempre simulado."""
import os, sys, tempfile, logging
D = tempfile.mkdtemp()
os.environ.update({"DATA_DIR": D, "TELEGRAM_TOKEN": "x", "TELEGRAM_CHAT_ID": "111", "TELEGRAM_GROUP_ID": "-100999"})
os.environ.pop("MOVIODDS_KEY", None)
os.environ.pop("MOVIODDS_KEY_2", None)
os.environ.pop("TELEGRAM_OWNER_ID", None)
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
import requests

class HTTPBlocked(BaseException):
    pass

def _blocked(*a, **k):
    raise HTTPBlocked("real HTTP call attempted")

requests.get = requests.post = _blocked
import bot_filtro_blindado_v5 as b

PRIMARY = "movi-primary-test"
BACKUP = "movi-backup-test"
THIRD = "movi-third-test"
HOLD = 30 * 60
WARN = "MoviOdds: chave reserva em uso por 30 min (falha da principal: %s)"

class Clock:
    def __init__(self):
        self.now = 1_000_000.0
    def __call__(self):
        return self.now

clock = Clock()
b.time.monotonic = clock

N = 0
def check(c, m):
    global N
    assert c, m
    N += 1

class Capture(logging.Handler):
    def __init__(self):
        super().__init__(level=logging.DEBUG)
        self.rows = []
    def emit(self, record):
        self.rows.append((record.levelname, record.getMessage()))

def response(status, payload=None, body=None, reason=None):
    r = requests.Response()
    r.status_code = status
    r.url = b.MoviOdds.URL + "?sport=table_tennis"
    r.reason = reason or ("OK" if status < 400 else "Nope")
    r.encoding = "utf-8"
    r.headers["Content-Type"] = "application/json"
    if body is None:
        import json
        body = json.dumps(payload if payload is not None else {"matches": []}).encode()
    r._content = body
    return r

def payload(home_odd):
    return {
        "matches": [
            {
                "league": "Czech Liga Pro",
                "home": "A Alfa",
                "away": "B Beta",
                "in_play": False,
                "kickoff_utc": "2026-11-20T08:00:00Z",
                "quotes": [
                    {"group_name": "To Win Match", "side": "A Alfa", "odds_dec": home_odd},
                    {"group_name": "To Win Match", "side": "B Beta", "odds_dec": 2.5},
                ],
            },
            {"league": "Outra Liga", "home": "Zeta", "away": "Yps", "quotes": []},
        ]
    }

def assert_call(call, key):
    check(call["url"] == b.MoviOdds.URL, call["url"])
    check(call["params"] == {"sport": "table_tennis"}, call["params"])
    check(call["timeout"] == 20, call["timeout"])
    check(call["headers"] == {"x-api-key": key}, call["headers"])
    check(call["extra"] == {}, call["extra"])
    check(key not in call["url"] and all(key not in str(v) for v in call["params"].values()), call)

def assert_match(result, odd):
    check(len(result) == 1, result)
    m = result[0]
    check(isinstance(m, b.OddsMatch) and m.home == "A Alfa" and m.away == "B Beta", m)
    check(m.odd_home == odd and m.odd_away == 2.5 and m.in_play is False and m.kickoff is not None, m)

def no_secrets(messages):
    blob = "\n".join(messages)
    for secret in (PRIMARY, BACKUP, THIRD):
        check(secret not in blob, blob)

def attempt(client, outcomes):
    calls = []
    queue = list(outcomes)
    def get(url, params=None, headers=None, timeout=None, **extra):
        calls.append({
            "url": url, "params": dict(params or {}), "headers": dict(headers or {}),
            "timeout": timeout, "extra": extra,
        })
        if not queue:
            raise HTTPBlocked("chamada HTTP extra")
        item = queue.pop(0)
        if isinstance(item, Exception):
            raise item
        return item
    b.requests.get = get
    cap = Capture()
    prev = b.log.propagate
    b.log.addHandler(cap)
    b.log.propagate = False
    try:
        result = client.fetch_czech()
    finally:
        b.log.removeHandler(cap)
        b.log.propagate = prev
        b.requests.get = _blocked
    messages = [m for _, m in cap.rows]
    check(all(level == "WARNING" for level, _ in cap.rows), cap.rows)
    no_secrets(messages)
    return result, calls, messages

# ---------- sem chave: não chama a rede e devolve []
for keys in ("", "   ", None, [], ["", "  "], ["", None], ("",)):
    client = b.MoviOdds(keys)
    check(client.keys == [], client.keys)
    check(client.fetch_czech() == [], keys)
check(b.MOVIODDS_KEY == "" and b.MOVIODDS_KEY_2 == "", "env de teste sem chaves")
check(b.MoviOdds.BACKUP_HOLD_SECONDS == HOLD, b.MoviOdds.BACKUP_HOLD_SECONDS)

# ---------- uma chave (string ou lista) continua igual: um request, sem reserva
client = b.MoviOdds(f"  {PRIMARY}\n")
check(client.keys == [PRIMARY], client.keys)
result, calls, logs = attempt(client, [response(200, payload(1.5))])
assert_match(result, 1.5)
check(len(calls) == 1 and logs == [], logs)
assert_call(calls[0], PRIMARY)

err = response(401, reason="Unauthorized")
result, calls, logs = attempt(b.MoviOdds([PRIMARY]), [err, response(200, payload(3.0))])
check(result == [] and len(calls) == 1, (result, len(calls), logs))
assert_call(calls[0], PRIMARY)
check(logs == [f"MoviOdds erro: 401 Client Error: Unauthorized for url: {err.url}"], logs)
check("reserva" not in logs[0], logs)

result, calls, logs = attempt(b.MoviOdds(PRIMARY), [requests.ConnectionError(f"rede {PRIMARY}")])
check(result == [] and len(calls) == 1, (len(calls), logs))
check(logs == ["MoviOdds erro: rede ***"], logs)

# lista com a principal vazia: a reserva é a única chave, sem fallback
client = b.MoviOdds(["", "  " + BACKUP + " "])
check(client.keys == [BACKUP], client.keys)
result, calls, logs = attempt(client, [response(429), response(200, payload(3.0))])
check(result == [] and len(calls) == 1, (len(calls), logs))
assert_call(calls[0], BACKUP)
check(len(logs) == 1 and logs[0].startswith("MoviOdds erro:") and "reserva" not in logs[0], logs)

# ---------- duas chaves: sucesso na principal não toca a reserva
result, calls, logs = attempt(b.MoviOdds([PRIMARY, BACKUP]), [response(200, payload(1.5))])
assert_match(result, 1.5)
check(len(calls) == 1 and logs == [], logs)
assert_call(calls[0], PRIMARY)

# HTTP que derruba a principal: repete a MESMA requisição uma vez com a reserva
for status in (401, 403, 429, 500, 502, 503, 599):
    clock.now += 1
    client = b.MoviOdds([PRIMARY, BACKUP])
    result, calls, logs = attempt(client, [response(status), response(200, payload(3.0))])
    assert_match(result, 3.0)
    check(len(calls) == 2, (status, len(calls)))
    assert_call(calls[0], PRIMARY)
    assert_call(calls[1], BACKUP)
    same = {k: v for k, v in calls[0].items() if k != "headers"}
    check(same == {k: v for k, v in calls[1].items() if k != "headers"}, (status, calls))
    check(logs == [WARN % f"HTTP {status}"], (status, logs))
    check(client._backup_until == clock.now + HOLD, (status, client._backup_until))

# estes erros NÃO trocam de chave (comportamento de uma chave: loga e devolve [])
for status in (400, 404, 408, 422):
    client = b.MoviOdds([PRIMARY, BACKUP])
    result, calls, logs = attempt(client, [response(status), response(200, payload(3.0))])
    check(result == [] and len(calls) == 1, (status, len(calls), logs))
    assert_call(calls[0], PRIMARY)
    check(len(logs) == 1 and logs[0].startswith("MoviOdds erro:") and "reserva" not in logs[0], (status, logs))
    check(client._backup_until is None, client._backup_until)

# JSON inválido e erro ao decodificar o corpo também não são failover
for bad in (response(200, body=b"{"),):
    client = b.MoviOdds([PRIMARY, BACKUP])
    result, calls, logs = attempt(client, [bad, response(200, payload(3.0))])
    check(result == [] and len(calls) == 1, (len(calls), logs))
    check(logs and logs[0].startswith("MoviOdds erro:") and "reserva" not in logs[0], logs)
    check(client._backup_until is None, client._backup_until)

client = b.MoviOdds([PRIMARY, BACKUP])
result, calls, logs = attempt(client, [requests.exceptions.ContentDecodingError(f"gzip {PRIMARY}"), response(200, payload(3.0))])
check(result == [] and len(calls) == 1 and client._backup_until is None, (len(calls), logs))
check(logs == ["MoviOdds erro: gzip ***"], logs)

# erro de rede na principal: uma tentativa com a reserva
for exc_type in (
    requests.ConnectionError, requests.Timeout, requests.exceptions.ReadTimeout,
    requests.exceptions.ConnectTimeout, requests.exceptions.SSLError,
    requests.exceptions.ChunkedEncodingError, requests.exceptions.ProxyError,
):
    clock.now += 1
    client = b.MoviOdds([PRIMARY, BACKUP])
    result, calls, logs = attempt(client, [exc_type(f"falha {PRIMARY}"), response(200, payload(3.0))])
    assert_match(result, 3.0)
    check(len(calls) == 2, (exc_type.__name__, len(calls)))
    assert_call(calls[0], PRIMARY)
    assert_call(calls[1], BACKUP)
    check(logs == [WARN % "erro de rede"], (exc_type.__name__, logs))

# as duas falham: avisa a reserva, não vaza chave, e segura a reserva
clock.now = 8_000.0
client = b.MoviOdds([PRIMARY, BACKUP, THIRD])
result, calls, logs = attempt(client, [
    requests.Timeout(f"timeout {PRIMARY}"),
    requests.ConnectionError(f"down {BACKUP}"),
    response(200, payload(3.0)),
])
check(result == [] and len(calls) == 2, (len(calls), logs))
assert_call(calls[0], PRIMARY)
assert_call(calls[1], BACKUP)
check(logs == [WARN % "erro de rede", "MoviOdds erro: down ***"], logs)
check(client._backup_until == 8_000.0 + HOLD, client._backup_until)
# dentro da janela nem a principal nem uma terceira chave são tentadas
clock.now = 8_000.0 + HOLD - 0.001
result, calls, logs = attempt(client, [response(401), response(200, payload(3.0))])
check(result == [] and len(calls) == 1, (len(calls), logs))
assert_call(calls[0], BACKUP)
check(logs == ["MoviOdds erro: 401 Client Error: Nope for url: " + calls[0]["url"] + "?sport=table_tennis"], logs)

# aos 30 min a principal volta; se ela falhar de novo, a reserva ganha mais 30 min
clock.now = 8_000.0 + HOLD
result, calls, logs = attempt(client, [response(503), response(200, payload(3.0))])
assert_match(result, 3.0)
check(len(calls) == 2, len(calls))
assert_call(calls[0], PRIMARY)
assert_call(calls[1], BACKUP)
check(logs == [WARN % "HTTP 503"], logs)
check(client._backup_until == clock.now + HOLD, client._backup_until)
clock.now += 10
result, calls, logs = attempt(client, [response(200, payload(3.0))])
assert_match(result, 3.0)
check(len(calls) == 1 and logs == [], logs)
assert_call(calls[0], BACKUP)

# janela esgotada e principal saudável: fica na principal
clock.now = 9_000.0
client = b.MoviOdds(["  " + PRIMARY + " ", "", BACKUP])
check(client.keys == [PRIMARY, BACKUP], client.keys)
attempt(client, [response(401), response(200, payload(3.0))])
clock.now = 9_000.0 + HOLD
result, calls, logs = attempt(client, [response(200, payload(1.5))])
assert_match(result, 1.5)
check(len(calls) == 1 and logs == [] and client._backup_until is None, (len(calls), logs, client._backup_until))
assert_call(calls[0], PRIMARY)
result, calls, logs = attempt(client, [response(200, payload(1.5))])
check(len(calls) == 1 and logs == [], logs)
assert_call(calls[0], PRIMARY)

# ---------- aviso de startup: sem chave continua igual; uma chave não avisa
def capture(fn):
    cap = Capture()
    prev = b.log.propagate
    b.log.addHandler(cap)
    b.log.propagate = False
    try:
        fn()
    finally:
        b.log.removeHandler(cap)
        b.log.propagate = prev
    return [m for _, m in cap.rows]

check(b.MOVIODDS_KEY == "" and b.MOVIODDS_KEY_2 == "", "globals ainda vazios")
msgs = capture(b.checar_config)
check(msgs == ["MOVIODDS_KEY não definida: rodando sem odds (só regra 'limpo vs derrota')."], msgs)
b.MOVIODDS_KEY = PRIMARY
try:
    check(capture(b.checar_config) == [], "principal sozinha não avisa")
finally:
    b.MOVIODDS_KEY = ""
b.MOVIODDS_KEY_2 = BACKUP
try:
    check(capture(b.checar_config) == [], "reserva sozinha não avisa")
finally:
    b.MOVIODDS_KEY_2 = ""

print("MOVIODDS OK", N, "checks")
