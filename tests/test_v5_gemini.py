"""Gemini só nas entradas aprovadas. Sem chave ou com falha, o alerta não muda.

requests.post para o Gemini é simulado. A chave de teste não vai para o log.
"""
import logging
import os
import sys
import tempfile
from datetime import datetime

D = tempfile.mkdtemp()
os.environ.update({
    "DATA_DIR": D,
    "TELEGRAM_TOKEN": "x",
    "TELEGRAM_CHAT_ID": "111",
    "TELEGRAM_GROUP_ID": "-100999",
})
os.environ.pop("GEMINI_API_KEY", None)
os.environ.pop("GEMINI_MODEL", None)
os.environ.pop("MOVIODDS_KEY", None)
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


def K(h, m):
    return b.TZ.localize(datetime(2026, 11, 20, h, m))


b.agora_cet = lambda: K(9, 25)

CHAVE = "chave-de-teste-gemini"
VEREDITO = "Confiança: Alta — alvo com forma estável e odd dentro da faixa"


class Resp:
    def __init__(self, texto):
        self.texto = texto

    def raise_for_status(self):
        return None

    def json(self):
        return {"candidates": [{"content": {"parts": [{"text": self.texto}]}}]}


def historico_verde():
    h = b.Historico()
    h.definir_jogos("Petr", [
        {"resultado": "limpo", "sets_favor": 3, "sets_contra": 0, "inicio": K(7, 0), "adversario": "X"},
        {"resultado": "limpo", "sets_favor": 3, "sets_contra": 1, "inicio": K(7, 40), "adversario": "Y"},
    ])
    h.definir_jogos("Jan", [
        {"resultado": "derrota", "sets_favor": 0, "sets_contra": 3, "inicio": K(7, 20), "adversario": "Z"},
    ])
    h.definir_jogos("Milos", [
        {"resultado": "limpo", "sets_favor": 3, "sets_contra": 0, "inicio": K(7, 5), "adversario": "Q"},
        {"resultado": "limpo", "sets_favor": 3, "sets_contra": 0, "inicio": K(7, 35), "adversario": "W"},
    ])
    h.definir_jogos("Adam", [
        {"resultado": "derrota", "sets_favor": 1, "sets_contra": 3, "inicio": K(7, 15), "adversario": "R"},
    ])
    return h


def jogo(home, away, hora=9, minuto=30):
    return b.OddsMatch(home, away, 1.50, 2.50, False, None, K(hora, minuto))


# ---------- sem chave: nada muda e não há rede ----------
chamadas = []


def post_conta(url, headers=None, json=None, timeout=None):
    chamadas.append(url)
    raise AssertionError("Gemini chamado sem chave")


b.requests.post = post_conta
h = historico_verde()
verde = jogo("Petr", "Jan")
partes, _, _ = b.montar_mensagem_entrada("2026-11-20|09:30", [verde], h, [verde])
check(partes == ["09:30 — Petr vs Jan | Entrada: Petr @ 1.50"], partes)
check(chamadas == [], chamadas)
sem = jogo("Sem Dados", "Jan", 9, 0)
partes_sem, _, _ = b.montar_mensagem_entrada("2026-11-20|09:00", [sem], b.Historico(), [sem])
check(partes_sem == ["09:00 — Sem entrada"], partes_sem)
check("🤖" not in partes_sem[0], partes_sem)

# ---------- uma chamada para o bloco, mesmo com duas entradas ----------
os.environ["GEMINI_API_KEY"] = CHAVE


def post_ok(url, headers=None, json=None, timeout=None):
    chamadas.append((url, timeout, (headers or {}).get("x-goog-api-key") == CHAVE, "key=" not in url))
    return Resp("1. Confiança: Alta — alvo com forma estável e odd dentro da faixa\n"
                "Confiança: Média — gap menor, mas ainda aceitável")


b.requests.post = post_ok
chamadas.clear()
dois = [verde, jogo("Milos", "Adam")]
partes, verts, _ = b.montar_mensagem_entrada("2026-11-20|09:30", dois, h, dois)
check(len(chamadas) == 1, chamadas)
check(chamadas[0][2] and chamadas[0][3], "chave só no header")
check("gemini-2.5-flash" in chamadas[0][0], chamadas[0][0])
check(0 < chamadas[0][1] <= 8, chamadas[0][1])
check(partes[0] == (
    "09:30 — Petr vs Jan | Entrada: Petr @ 1.50\n"
    "🤖 Gemini: Confiança: Alta — alvo com forma estável e odd dentro da faixa\n"
    "09:30 — Milos vs Adam | Entrada: Milos @ 1.50\n"
    "🤖 Gemini: Confiança: Média — gap menor, mas ainda aceitável"
), partes[0])
check(len(verts) == 2 and verts[0][3].startswith("Confiança: Alta"), verts)

# sem entrada não chama, mesmo com a chave
chamadas.clear()
b.montar_mensagem_entrada("2026-11-20|09:00", [sem], b.Historico(), [sem])
check(chamadas == [], "sem entrada não chama")

# ---------- timeout e fallback: o alerta segue sem a linha ----------
def post_timeout(url, headers=None, json=None, timeout=None):
    chamadas.append(url)
    raise b.requests.Timeout("demorou")


b.requests.post = post_timeout
chamadas.clear()
partes, verts, _ = b.montar_mensagem_entrada("2026-11-20|09:30", [verde], h, [verde])
check(partes == ["09:30 — Petr vs Jan | Entrada: Petr @ 1.50"], partes)
check(verts[0][3] == "", verts)
check(len(chamadas) == 2, chamadas)  # os dois modelos, dentro do prazo

vistos = []


def post_fallback(url, headers=None, json=None, timeout=None):
    vistos.append(url)
    if "gemini-2.5-flash" in url:
        raise b.requests.HTTPError("modelo")
    return Resp(VEREDITO)


b.requests.post = post_fallback
texto = b.consultar_gemini("uma entrada")
check(texto == VEREDITO, texto)
check(any("gemini-2.0-flash" in u for u in vistos), vistos)

os.environ["GEMINI_MODEL"] = "gemini-2.5-pro"
vistos.clear()


def post_modelo(url, headers=None, json=None, timeout=None):
    vistos.append(url)
    if "gemini-2.5-pro" in url:
        raise b.requests.HTTPError("modelo")
    return Resp(VEREDITO)


b.requests.post = post_modelo
check(b.consultar_gemini("uma entrada") == VEREDITO, "modelo do env")
check(vistos[0].endswith("gemini-2.5-pro:generateContent"), vistos[0])
check(any("gemini-2.0-flash" in u for u in vistos), vistos)
os.environ.pop("GEMINI_MODEL", None)

# ---------- CSV antigo ganha a coluna e o veredito ----------
os.environ.pop("GEMINI_API_KEY", None)
antigo = b.AUDITORIA_FILE
antigo.write_text(
    "data,horario,jogo,alvo,odd,gap,resultado\n"
    "2026-11-19,09:00,Ana vs Bia,Ana,1.40,6.0,\n",
    encoding="utf-8",
)
livro = b.LivroEntradas(b.Path(D) / "livro_gemini.json")
check(livro.registrar("Petr", "Jan", "Petr", K(9, 30), 1.50, 8.0, VEREDITO), "grava")
import csv
with antigo.open(encoding="utf-8", newline="") as fh:
    rows = list(csv.DictReader(fh))
check(rows[0]["gemini"] == "", rows[0])
check(rows[1]["gemini"] == VEREDITO, rows[1])
check(rows[1]["resultado"] == "", rows[1])
livro.itens[0]["status"] = "green"
livro.itens[0]["placar"] = "3-1"
check(b.fechar_auditoria(livro, K(10, 10)) == 1, "fecha")
with antigo.open(encoding="utf-8", newline="") as fh:
    rows = list(csv.DictReader(fh))
check(rows[1]["resultado"] == "GREEN" and rows[1]["gemini"] == VEREDITO, rows[1])
check(rows[0]["resultado"] == "" and "gemini" in rows[0], rows[0])

# o log da falha não carrega a chave
os.environ["GEMINI_API_KEY"] = CHAVE


class Cap(logging.Handler):
    def __init__(self):
        super().__init__()
        self.rows = []

    def emit(self, record):
        self.rows.append(record.getMessage())


cap = Cap()
b.log.addHandler(cap)
try:
    b.requests.post = post_timeout
    b.consultar_gemini("ficha")
finally:
    b.log.removeHandler(cap)
junto = "\n".join(cap.rows)
check("sem análise" in junto and CHAVE not in junto, "log sem a chave")

print("GEMINI OK", N, "checks")
