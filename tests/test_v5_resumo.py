"""Resumo diário das 00:05: entradas persistidas, liquidação sem rede e um envio só.

requests é sempre simulado. A grade do MoviOdds fica em 144 consultas/dia.
"""
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

def K(y, mo, d, h, mi):
    return b.TZ.localize(datetime(y, mo, d, h, mi))

class TG:
    def __init__(self):
        self.sent = []
    def send(self, text, chat_id=None, reply_to=None):
        self.sent.append(text)
        return True

class TGFalha(TG):
    def send(self, text, chat_id=None, reply_to=None):
        return False

def jogo_forma(home, away, sh, sa, inicio):
    return {
        "home": home, "away": away, "sets_home": sh, "sets_away": sa,
        "inicio": inicio.isoformat(), "fim": (inicio + timedelta(minutes=20)).isoformat(),
        "league": "Czech Liga Pro",
    }

check(b.MOVIODDS_CHAMADAS_DIA == 144, b.MOVIODDS_CHAMADAS_DIA)

caminho = b.Path(D) / "entradas_v5.json"
livro = b.LivroEntradas(caminho)
ini = [
    K(2026, 11, 19, 9, 0),
    K(2026, 11, 19, 11, 30),
    K(2026, 11, 19, 14, 0),
    K(2026, 11, 19, 16, 30),
    K(2026, 11, 19, 18, 0),
]
odds = [1.50, 1.40, 1.80, 1.62, 1.55]
pares = [
    ("Petr", "Jan"),
    ("Milos", "Adam"),
    ("Ivan", "Karel"),
    ("Ana", "Bia"),
    ("Duda", "Ema"),
]
for (home, away), hora, odd in zip(pares, ini, odds):
    check(livro.registrar(home, away, home, hora, odd), (home, odd))
check(livro.registrar("Petr", "Jan", "Petr", ini[0], 1.50) is False, "não duplica")
check(len(livro.itens) == 5 and all(e["status"] == "pendente" for e in livro.itens), livro.itens)
check(livro.itens[0]["hora"] == "09:00" and livro.itens[0]["adversario"] == "Jan", livro.itens[0])
check(livro.itens[0]["odd"] == 1.50, livro.itens[0]["odd"])

forma = b.FormaDia(b.Path(D) / "forma.json")
# 3-1, 3-0, 3-2 do alvo; o quarto perde 1-3; o quinto ainda não tem placar
forma.jogos = [
    jogo_forma("Petr", "Jan", 3, 1, ini[0]),
    jogo_forma("Adam", "Milos", 0, 3, ini[1]),  # Milos (alvo, fora) ganha 3-0
    jogo_forma("Ivan", "Karel", 3, 2, ini[2]),
    jogo_forma("Ana", "Bia", 1, 3, ini[3]),
]
agora = K(2026, 11, 20, 0, 5)
check(b.liquidar_livro(livro, forma, None, agora) == 4, [e["status"] for e in livro.itens])
check([e["status"] for e in livro.itens] == ["green", "green", "green", "red", "pendente"],
      [e["status"] for e in livro.itens])
check(livro.itens[1]["placar"] == "0-3", livro.itens[1])

# um jogo antigo do mesmo par, fora da janela de 45 min, não liquida o pendente
forma.jogos.append(jogo_forma("Duda", "Ema", 3, 0, ini[4] - timedelta(hours=3)))
check(b.liquidar_livro(livro, forma, None, agora) == 0, livro.itens[-1])
check(livro.itens[-1]["status"] == "pendente", livro.itens[-1])

tg = TG()
check(b.enviar_resumo_diario(tg, livro, forma, None, K(2026, 11, 20, 0, 4)) is False, "antes das 00:05")
check(tg.sent == [], tg.sent)
check(b.enviar_resumo_diario(tg, livro, forma, None, agora) is True, "00:05 envia")
texto = tg.sent[0]
check(texto == (
    "Resumo 19/11\n"
    "Entradas: 5 | Green: 3 | Red: 1 | Pendentes: 1\n"
    "Saldo: +0.70 un (stake 1 un)"
), texto)
check(b.enviar_resumo_diario(tg, livro, forma, None, K(2026, 11, 20, 0, 10)) is False, "não repete")
check(len(tg.sent) == 1, tg.sent)
outro = b.LivroEntradas(caminho)
check(outro.ultimo_resumo == "2026-11-19", outro.ultimo_resumo)
check(b.enviar_resumo_diario(tg, outro, forma, None, K(2026, 11, 20, 0, 12)) is False, "restart não reenvia")
check(len(tg.sent) == 1, tg.sent)
check(b.enviar_resumo_diario(tg, outro, forma, None, K(2026, 11, 20, 0, 21)) is False, "fora da janela")

# o pendente fecha pelo histórico (sobrenome + inicial) e sai no resumo seguinte
check(b.nomes_compativeis("Duda Silva", "Silva D."), "nome da API")
livro.itens[-1]["home"] = "Duda Silva"
livro.itens[-1]["alvo"] = "Duda Silva"
livro.itens[-1]["away"] = "Ema Costa"
livro.itens[-1]["adversario"] = "Ema Costa"
hist = type("H", (), {})()
hist.jogos = [{
    "ts": int(ini[4].timestamp()),
    "home": "Silva D.",
    "away": "Costa E.",
    "sh": 3,
    "sa": 1,
}]
check(b.liquidar_livro(livro, b.FormaDia(b.Path(D) / "vazia.json"), hist, K(2026, 11, 20, 12, 0)) == 1,
      livro.itens[-1])
check(livro.itens[-1]["status"] == "green", livro.itens[-1])

tg2 = TG()
amanha = K(2026, 11, 21, 0, 6)
check(b.enviar_resumo_diario(tg2, livro, None, hist, amanha) is True, "dia seguinte")
check(tg2.sent[0] == (
    "Resumo 20/11 — nenhuma entrada\n"
    "Pendentes anteriores: 1 green, 0 red (+0.55 un)"
), tg2.sent[0])
check(b.enviar_resumo_diario(tg2, livro, None, hist, K(2026, 11, 21, 0, 8)) is False, "o seguinte também não repete")

# dia vazio, sem pendência antiga
vazio = b.LivroEntradas(b.Path(D) / "vazio.json")
tg3 = TG()
check(b.enviar_resumo_diario(tg3, vazio, None, None, K(2026, 11, 22, 0, 5)) is True, "sem entradas")
check(tg3.sent == ["Resumo 21/11 — nenhuma entrada"], tg3.sent)

# falha de envio não marca o dia
falha = b.LivroEntradas(b.Path(D) / "falha.json")
falha.registrar("A", "B", "A", K(2026, 11, 21, 15, 0), 1.70)
check(b.enviar_resumo_diario(TGFalha(), falha, None, None, K(2026, 11, 22, 0, 5)) is False, "falha")
check(falha.ultimo_resumo == "", falha.ultimo_resumo)
check(b.enviar_resumo_diario(TG(), falha, None, None, K(2026, 11, 22, 0, 7)) is True, "tenta de novo")

# exemplo fechado: 4 greens e 1 red, saldo +1.32
exemplo = b.LivroEntradas(b.Path(D) / "exemplo.json")
ex_odds = [1.50, 1.40, 1.80, 1.62, 2.00]
for i, odd in enumerate(ex_odds):
    exemplo.registrar(f"Casa{i}", f"Fora{i}", f"Casa{i}", K(2026, 11, 19, 10 + i, 0), odd)
for i, entrada in enumerate(exemplo.itens):
    entrada["status"] = "red" if i == 4 else "green"
texto_ex = b.texto_resumo_entradas(datetime(2026, 11, 19).date(), exemplo.itens, [])
check(texto_ex == (
    "Resumo 19/11\n"
    "Entradas: 5 | Green: 4 | Red: 1 | Pendentes: 0\n"
    "Saldo: +1.32 un (stake 1 un)"
), texto_ex)

print("RESUMO OK", N, "checks")
