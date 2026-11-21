#!/usr/bin/env python3
"""
═══════════════════════════════════════════════════════════════════════════════
  BOT TELEGRAM — FILTRO BLINDADO v5 (interativo)
  ScoreMondo (placar, confrontos e resultados — grátis, sem chave)
  + MoviOdds (odds bet365, OPCIONAL) + Telegram
═══════════════════════════════════════════════════════════════════════════════

Horários CET (Europe/Madrid = Europe/Prague no inverno e no horário de verão da UE;
somente Czech Liga Pro — 24 h, madrugada inclusive):
  ENTRADA (pré-jogo): às :25 (bloco das :30) e às :55 (bloco das :00).
      O ciclo pode acordar até 4 min depois e ainda manda a mensagem uma vez.
      Uma linha por jogo: "HH:MM — A vs B | Entrada: Alvo @ Odd".
      Sem sinal, ou sem jogo na grade: "HH:MM — Sem entrada".
      Score, gap e Histórico/H2H ficam no log.

Filtro rígido por FORMA NA JANELA (últimas 4 h; o alvo é quem tem o melhor
  score_forma, não o favorito da casa):
  score 3-0=+3, 3-1=+2, 3-2=+0.5, 2-3=-0.5, 1-3=-2, 0-3=-3, nos últimos 2–3
  jogos finalizados. jogos_hoje = finalizados nas últimas 3 h. Entra só se os
  dois têm pelo menos 1 jogo nessa janela de 3 h, a odd do alvo está em
  [1.25, 1.85], o alvo não perdeu o último, tem 2 vitórias limpas seguidas
  (3-0/3-1), não vem de 5 sets há menos de 45 min, não jogou nos 45 min
  anteriores ao apito, o adversário tem score <= 0, o gap (com bônus de
  adversário comum) é >= 5 e os dois não estão com score >= 3. Sem odds, ou
  cache de odds com mais de 20 min, não há . H2H 14d é só informação.

MoviOdds (odds + resultados) — 144 consultas/dia na grade (4.464 em 31 dias, abaixo de 5.000).
  Uma consulta de odds traz todos os jogos futuros, então a grade pede odds a cada
  15 min (:00, :15, :30, :45) nas 24 h. No alerta (:25 e :55) o cache tem 10 min,
  abaixo dos 20. Resultados em :23 e :53, logo antes do alerta. A primeira consulta
  do dia é 00:00. Se uma consulta volta vazia por erro,
  o mesmo slot é tentado de novo depois de ~60 s (no máximo 2 vezes).
  O cache de odds fica em DATA_DIR. No reinício, odds com menos de 20 min são
  reaproveitadas. Sem odds frescas e com jogo começando em até 30 min, há uma
  consulta imediata (no máximo uma por dia, além da grade: o teste aceita ≤161).

Interativo (v5) — tudo vai para o GRUPO (TELEGRAM_GROUP_ID):
  • GREEN ✅ / RED ❌ de cada  assim que o jogo termina + placar do dia
    ( sem resultado após 3 h = anulada, não conta)
  • Resumo do dia às 22:30 (por rodada + acumulado do mês) com aviso +18
  • Resumo das s às 00:05 Europe/Prague (dia anterior, stake 1 un)
  • Saudações 07:50 (bom dia), 12:40 (boa tarde), 22:35 (boa noite) com frase motivacional
  • Responde bom dia/boa tarde/boa noite/oi/obrigado e menções ao bot (com limite por pessoa)
  • Comandos de todos: /placar /semana /mes /s /ajuda /id
    Comandos de admin (só o dono, TELEGRAM_OWNER_ID ou TELEGRAM_CHAT_ID):
    /status /lista /zerar /limpo /desgaste /derrota
  Para ler mensagens normais do grupo: desative o "Group Privacy" no BotFather
  (/setprivacy → Disable) ou deixe o bot como administrador do grupo.

Configuração (variáveis de ambiente):
  Obrigatórias: TELEGRAM_TOKEN, TELEGRAM_CHAT_ID (chat privado do dono/admin)
  Recomendada:  TELEGRAM_GROUP_ID (grupo; sem ela tudo vai para TELEGRAM_CHAT_ID)
  Opcional:     TELEGRAM_OWNER_ID (id do usuário admin; padrão = TELEGRAM_CHAT_ID)
                TELEGRAM_DISCUSSION_ID (grupo de discussão ligado ao canal: lá o bot
                conversa, dá boas-vindas e responde /placar /semana /mes /s /ajuda;
                as s, green/red, resumo e saudações continuam no TELEGRAM_GROUP_ID)
  Opcionais:    MOVIODDS_KEY (odds; sem chave não há  — falta odds de mercado)
                MOVIODDS_KEY_2 (reserva do MoviOdds, opcional: entra por 30 min se a
                principal falhar com 401, 403, 429, 5xx ou erro de rede)
                SPORTSAPI365_KEY (resultados anteriores, RapidAPI; sem ela o bot segue
                igual, sem as linhas de Histórico 7d e H2H 14d)
                DATA_DIR     (pasta dos arquivos .json; padrão = pasta do script)

Resultados anteriores (SportsAPI365, opcional): uma vez por dia, depois das 00:30
Europe/Prague, baixa os finalizados de ontem (no primeiro arranque, até 7 dias) e
guarda 14 dias em DATA_DIR. No máximo 40 chamadas por dia, abaixo do teto de 50.
A forma de 7 dias e o H2H de 14 são lidos só do cache e vão para o log, não para
o Telegram. O H2H não bloqueia . As 144 consultas do MoviOdds não mudam.
"""

from __future__ import annotations
import os
import re
import sys
import csv
import json
import html
import random
import time
import logging
from datetime import datetime, timedelta, time as dtime
from pathlib import Path
from typing import Dict, List, Optional, Tuple
from dataclasses import dataclass

import requests
from bs4 import BeautifulSoup
import pytz

from historico_sportsapi365 import HistoricoSportsAPI365, TZ_PRAGA, nomes_compativeis

# ══════════════════════════════════════════════════════════════════════════════
# CONFIGURAÇÃO
# ══════════════════════════════════════════════════════════════════════════════

TELEGRAM_TOKEN = os.getenv("TELEGRAM_TOKEN", "").strip()
CHAT_ID = os.getenv("TELEGRAM_CHAT_ID", "").strip()
MOVIODDS_KEY = os.getenv("MOVIODDS_KEY", "").strip()
MOVIODDS_KEY_2 = os.getenv("MOVIODDS_KEY_2", "").strip()
SPORTSAPI365_KEY = os.getenv("SPORTSAPI365_KEY", "").strip()
GROUP_ID = os.getenv("TELEGRAM_GROUP_ID", "").strip() or CHAT_ID
OWNER_ID = os.getenv("TELEGRAM_OWNER_ID", "").strip() or CHAT_ID
# Grupo de discussão ligado ao canal (opcional): onde o bot conversa e responde comandos
DISCUSSION_ID = os.getenv("TELEGRAM_DISCUSSION_ID", "").strip()

INTERVALO_SCRAPE = 35
DATA_DIR = Path(os.getenv("DATA_DIR", "").strip() or Path(__file__).resolve().parent)
HISTORY_FILE = DATA_DIR / "historico_v4.json"
ENVIADOS_FILE = DATA_DIR / "sinais_enviados_v4.json"
FINISHED_FILE = DATA_DIR / "finished_cache_v4.json"
ENTRADAS_FILE = DATA_DIR / "entradas_enviadas_v4.json"
APOSTAS_FILE = DATA_DIR / "apostas_v5.json"      # entradas + green/red
ENTRADAS_SALDO_FILE = DATA_DIR / "entradas_v5.json"  # entradas aprovadas e o resumo das 00:05
AUDITORIA_FILE = DATA_DIR / "auditoria_v5.csv"       # data, horario, jogo, alvo, odd, gap, resultado, gemini
LICOES_FILE = DATA_DIR / "licoes_v5.txt"
AUDITORIA_CAMPOS = ["data", "horario", "jogo", "alvo", "odd", "gap", "resultado", "gemini"]
AUDITORIA_APOS_MIN = 35
EVENTOS_FILE = DATA_DIR / "eventos_v5.json"      # resumo/saudações já enviados
FORMA_FILE = DATA_DIR / "forma_dia_v5.json"      # jogos finalizados do dia (MoviOdds)
ODDS_CACHE_FILE = DATA_DIR / "odds_cache_v5.json"  # última consulta de odds (sobrevive a reinício)
ODDS_BOOT_FILE = DATA_DIR / "odds_boot_v5.json"    # consulta imediata já gasta neste dia

TZ = pytz.timezone("Europe/Madrid")

# Odd do alvo (melhor score_forma). Os limites são inclusivos.
ODD_MIN_ALVO = 1.25
ODD_MAX_ALVO = 1.85
# Cache do MoviOdds mais velho que isto é tratado como odds ausentes.
ODDS_CACHE_TTL_S = 20 * 60
# Forma: últimos 2–3 jogos em 4 h. jogos_hoje e triangulação usam 3 h.
JANELA_SCORE_H = 4
JANELA_JOGOS_H = 3
JANELA_TRIANG_H = 3
MAX_JOGOS_SCORE = 3
DESGASTE_MIN = 45
GAP_MIN = 5.0
SCORE_AMBOS_VITORIAS = 3.0
# Jogo cujo início cai nesta antecedência do apito = horário anterior.
SLOT_ANTERIOR_MIN = 45
# forma_dia_v5.json guarda um pouco mais que a janela de 4 h, inclusive depois da meia-noite.
RETENCAO_FORMA_H = 8
# Sem fim na API: início + estes minutos. Sem início: fim − estes minutos.
# 3 sets = 15 min, 4 sets = 20 min, 5 sets = 25 min.
DURACAO_ESTIMADA_MIN = {3: 15, 4: 20, 5: 25}
PESOS_FORMA = {
    (3, 0): 3.0,
    (3, 1): 2.0,
    (3, 2): 0.5,
    (2, 3): -0.5,
    (1, 3): -2.0,
    (0, 3): -3.0,
}

def duracao_estimada_min(sets_a: int, sets_b: int) -> int:
    return DURACAO_ESTIMADA_MIN.get(int(sets_a) + int(sets_b), 20)

def estimar_fim(inicio: datetime, sets_a: int, sets_b: int) -> datetime:
    return inicio + timedelta(minutes=duracao_estimada_min(sets_a, sets_b))

def estimar_inicio(fim: datetime, sets_a: int, sets_b: int) -> datetime:
    return fim - timedelta(minutes=duracao_estimada_min(sets_a, sets_b))

def peso_sets(sets_favor: int, sets_contra: int) -> float:
    return float(PESOS_FORMA.get((int(sets_favor), int(sets_contra)), 0.0))
# O alerta é :25 (bloco :30) e :55 (bloco :00). A folga cobre um ciclo de ~40 s
# que acorde depois do minuto exato. _ANTES_* só descreve essa folga.
ALERTA_FOLGA_MIN = 4
ENTRADA_ANTES_MAX_S = 5 * 60
ENTRADA_ANTES_MIN_S = 60
# Horário anterior: "rigido" bloqueia sempre; "sets" só se o jogo anterior teve 4 ou 5 sets.
HORARIO_ANTERIOR = "rigido"

def modo_horario_anterior() -> str:
    bruto = os.getenv("HORARIO_ANTERIOR", HORARIO_ANTERIOR).strip().lower()
    return bruto if bruto in ("rigido", "sets") else "rigido"
# No reinício, sem odds frescas, consulta já se o jogo começa neste prazo.
REINICIO_ODDS_S = 30 * 60

logging.basicConfig(level=logging.INFO, format="%(asctime)s | %(levelname)s | %(message)s", datefmt="%H:%M:%S")
log = logging.getLogger("FiltroV5")

# Gravação ao vivo da 1ª hora dos ciclos antigos (o filtro em si usa o dia inteiro).
JANELAS_R1 = [
    (8, 0, 8, 54),
    (12, 0, 12, 54),
    (16, 0, 16, 54),
    (20, 0, 20, 54),
]

# A entrada não depende mais do minuto :55: vale em qualquer hora, por bloco de início.
# HORAS_ENTRADA segue as 24 h para saudações e para o texto de ajuda não colidir com um envio fixo.
HORAS_ENTRADA = tuple(range(24))
JANELAS_ENTRADA = [(h, 55, h, 59) for h in HORAS_ENTRADA]

def _agenda_moviodds():
    """144 consultas/dia: 96 de odds e 48 de resultados.

    Odds às :00, :15, :30 e :45. Resultados (FT) às :23 e :53, imediatamente
    antes do alerta das :25 (bloco :30) e das :55 (bloco :00). No alerta a odd
    tem 10 minutos, abaixo do teto de 20.
    """
    odds, resultados = [], []
    for h in range(24):
        for m in (0, 15, 30, 45):
            odds.append((h, m))
        resultados.append((h, 23))
        resultados.append((h, 53))
    return tuple(odds), tuple(resultados)

MOVIODDS_MINUTOS_ODDS, MOVIODDS_MINUTOS_RESULTADOS = _agenda_moviodds()
# Um minuto = uma chamada (odds ou resultados). 144/dia × 31 = 4.464, abaixo de 5.000.
MOVIODDS_MINUTOS = tuple(sorted(set(MOVIODDS_MINUTOS_ODDS + MOVIODDS_MINUTOS_RESULTADOS)))
MOVIODDS_CHAMADAS_DIA = len(MOVIODDS_MINUTOS_ODDS) + len(MOVIODDS_MINUTOS_RESULTADOS)
MOVIODDS_CHAMADAS_MES_31 = MOVIODDS_CHAMADAS_DIA * 31
MOVIODDS_MAX_TENTATIVAS = 2
MOVIODDS_RETRY_S = 60

def agenda_moviodds():
    """(hora, minuto, 'odds'|'resultados') em ordem cronológica. Uma chamada cada."""
    itens = [(h, m, "odds") for h, m in MOVIODDS_MINUTOS_ODDS]
    itens += [(h, m, "resultados") for h, m in MOVIODDS_MINUTOS_RESULTADOS]
    itens.sort()
    return tuple(itens)

# Fallback ao vivo, qualquer hora: jogos das hh:00 .. hh:50 ainda não avaliados no :55.
JANELAS_R2 = [(h, 0, h, 50) for h in range(24)]

def agora_cet() -> datetime:
    return datetime.now(TZ)

def _na_janela(t: dtime, janelas) -> bool:
    return any(dtime(h1, m1) <= t <= dtime(h2, m2, 59) for h1, m1, h2, m2 in janelas)

def esta_em_janela(janelas) -> bool:
    return _na_janela(agora_cet().time(), janelas)

def modo_atual() -> str:
    t = agora_cet().time()
    if _na_janela(t, JANELAS_ENTRADA):
        return "ENTRADA"
    if _na_janela(t, JANELAS_R2):
        return "R2"
    if _na_janela(t, JANELAS_R1):
        return "R1"
    return "FORA"

def slot_entrada_atual() -> Optional[str]:
    """Retorna a chave do slot de ENTRADA se agora está em hh:55–hh:59, ex: '2026-11-20|08:55'."""
    now = agora_cet()
    if now.hour in HORAS_ENTRADA and 55 <= now.minute <= 59:
        return f"{now.strftime('%Y-%m-%d')}|{now.hour:02d}:55"
    return None

def _slot_na_grade(grade, now: Optional[datetime] = None) -> Optional[str]:
    now = now or agora_cet()
    if (now.hour, now.minute) in grade:
        return f"{now.strftime('%Y-%m-%d')}|{now.hour:02d}:{now.minute:02d}"
    return None

def slot_moviodds_atual(now: Optional[datetime] = None) -> Optional[str]:
    """Chave 'YYYY-MM-DD|HH:MM' se este minuto consulta ODDS; senão None."""
    return _slot_na_grade(MOVIODDS_MINUTOS_ODDS, now)

def slot_resultados_atual(now: Optional[datetime] = None) -> Optional[str]:
    """Chave 'YYYY-MM-DD|HH:MM' se este minuto consulta RESULTADOS; senão None."""
    return _slot_na_grade(MOVIODDS_MINUTOS_RESULTADOS, now)

class CacheOdds:
    """Última lista de odds e o instante (time.time) da consulta que a gravou.

    persistir=True grava em DATA_DIR. Um reinício com odds de menos de 20 min
    reaproveita a lista sem nova chamada.
    """
    def __init__(self, persistir: bool = False):
        self.lista: List[OddsMatch] = []
        self.quando: Optional[float] = None
        self.tentativas: Dict[str, int] = {}
        self.ultima_tentativa: Dict[str, float] = {}
        self.falhou: Dict[str, bool] = {}
        self.persistir = persistir
        if persistir:
            self.carregar()

    def carregar(self):
        if not ODDS_CACHE_FILE.exists():
            return
        try:
            raw = json.loads(ODDS_CACHE_FILE.read_text(encoding="utf-8"))
        except Exception:
            return
        quando = raw.get("quando")
        if isinstance(quando, (int, float)):
            self.quando = float(quando)
        lista = []
        for item in raw.get("lista") or []:
            if isinstance(item, dict):
                lista.append(_odds_de_dict(item))
        self.lista = lista

    def salvar(self):
        if not self.persistir:
            return
        ODDS_CACHE_FILE.parent.mkdir(parents=True, exist_ok=True)
        payload = {
            "quando": self.quando,
            "lista": [_odds_para_dict(o) for o in self.lista],
        }
        tmp = ODDS_CACHE_FILE.with_suffix(".tmp")
        tmp.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")
        tmp.replace(ODDS_CACHE_FILE)

def _chamar_anotando_erro(fn) -> Tuple[list, bool]:
    """erro=True só se a lista veio vazia por falha da API (aviso 'MoviOdds erro')."""
    falhas: List[str] = []

    class _Aviso(logging.Handler):
        def emit(self, record: logging.LogRecord):
            if record.levelno >= logging.WARNING and record.getMessage().startswith("MoviOdds erro"):
                falhas.append(record.getMessage())

    aviso = _Aviso()
    log.addHandler(aviso)
    try:
        lista = fn() or []
    finally:
        log.removeHandler(aviso)
    return lista, (not lista) and bool(falhas)

def _fetch_anotando_erro(moviodds: "MoviOdds") -> Tuple[List[OddsMatch], bool]:
    """fetch_czech sem mexer na classe. erro=True só se a lista veio vazia por falha."""
    return _chamar_anotando_erro(moviodds.fetch_czech)

def _pode_tentar_slot(cache: CacheOdds, slot: str, ts: float) -> bool:
    feitas = cache.tentativas.get(slot, 0)
    if feitas >= MOVIODDS_MAX_TENTATIVAS:
        return False
    if feitas == 0:
        return True
    if not cache.falhou.get(slot):
        return False
    return ts - cache.ultima_tentativa.get(slot, 0) >= MOVIODDS_RETRY_S

def _slot_para_consultar(cache: CacheOdds, now: datetime, ts: float,
                         slot_fn=None) -> Optional[str]:
    """Slot a consultar agora, ou None para reutilizar o cache.

    No minuto agendado, no máximo uma consulta (segunda tentativa ~60 s depois
    se a primeira voltou vazia por erro). Essa segunda tentativa ainda vale
    para o mesmo slot quando o relógio já saiu daquele minuto.
    """
    atual = (slot_fn or slot_moviodds_atual)(now)
    if atual is not None and _pode_tentar_slot(cache, atual, ts):
        return atual
    if not cache.ultima_tentativa:
        return None
    ultimo = max(cache.ultima_tentativa, key=cache.ultima_tentativa.get)
    if atual not in (None, ultimo):
        return None
    if cache.tentativas.get(ultimo, 0) > 0 and _pode_tentar_slot(cache, ultimo, ts):
        return ultimo
    return None

def _lista_cache_vigente(cache: CacheOdds, ts: float) -> List[OddsMatch]:
    """Lista em cache, ou [] se nunca houve consulta ou se ela tem mais de 20 min."""
    if cache.quando is None or ts - cache.quando > ODDS_CACHE_TTL_S:
        return []
    return cache.lista

def _rotulo_slot(slot: str) -> str:
    """'YYYY-MM-DD|HH:MM' ou '...|HH:MM|inicio' vira HH:MM."""
    parte = slot.split("|", 1)[1]
    return parte[:5]

def _gravar_consulta(cache: CacheOdds, slot: str, ts: float, lista: list, erro: bool):
    cache.tentativas[slot] = cache.tentativas.get(slot, 0) + 1
    cache.ultima_tentativa[slot] = ts
    cache.falhou[slot] = erro
    if not erro:
        cache.lista = lista
        cache.quando = ts
        cache.salvar()

def _boot_ja_feito(now: datetime) -> bool:
    dia = now.astimezone(TZ).strftime("%Y-%m-%d")
    if not ODDS_BOOT_FILE.exists():
        return False
    try:
        raw = json.loads(ODDS_BOOT_FILE.read_text(encoding="utf-8"))
    except Exception:
        return False
    return raw.get("dia") == dia and int(raw.get("n") or 0) >= 1

def _marcar_boot(now: datetime):
    dia = now.astimezone(TZ).strftime("%Y-%m-%d")
    ODDS_BOOT_FILE.parent.mkdir(parents=True, exist_ok=True)
    tmp = ODDS_BOOT_FILE.with_suffix(".tmp")
    tmp.write_text(json.dumps({"dia": dia, "n": 1}), encoding="utf-8")
    tmp.replace(ODDS_BOOT_FILE)

def obter_odds(moviodds: "MoviOdds", cache: CacheOdds,
               now: Optional[datetime] = None, agora_ts: Optional[float] = None) -> List[OddsMatch]:
    """Odds em cache. Consulta o MoviOdds só no slot agendado (no máximo 2 tentativas).

    Cache com mais de 20 minutos conta como odds ausentes: a lista antiga fica
    guardada, mas quem chama recebe [].
    """
    now = now or agora_cet()
    ts = time.time() if agora_ts is None else agora_ts
    slot = _slot_para_consultar(cache, now, ts)
    if slot is None:
        return _lista_cache_vigente(cache, ts)
    lista, erro = _fetch_anotando_erro(moviodds)
    _gravar_consulta(cache, slot, ts, lista, erro)
    log.info("[ODDS] consulta %s -> %s jogos", _rotulo_slot(slot), len(lista))
    return _lista_cache_vigente(cache, ts)

def talvez_odds_imediatas(moviodds: "MoviOdds", cache: CacheOdds, jogos: List["OddsMatch"],
                          now: Optional[datetime] = None, agora_ts: Optional[float] = None) -> List["OddsMatch"]:
    """No reinício (cache velho): se há jogo em até 30 min, uma consulta fora da grade.

    No máximo uma por dia. O minuto que já é slot de odds fica com a grade.
    """
    now = now or agora_cet()
    ts = time.time() if agora_ts is None else agora_ts
    vigente = _lista_cache_vigente(cache, ts)
    if vigente or slot_moviodds_atual(now) or _boot_ja_feito(now):
        return vigente
    if not jogos_comecando_em(jogos, now, REINICIO_ODDS_S):
        return vigente
    slot = f"{now.astimezone(TZ).strftime('%Y-%m-%d|%H:%M')}|inicio"
    if not _pode_tentar_slot(cache, slot, ts):
        return vigente
    lista, erro = _fetch_anotando_erro(moviodds)
    _gravar_consulta(cache, slot, ts, lista, erro)
    if not erro:
        _marcar_boot(now)
    log.info("[ODDS] consulta %s -> %s jogos", _rotulo_slot(slot), len(lista))
    return _lista_cache_vigente(cache, ts)

def obter_resultados(moviodds: "MoviOdds", forma: "FormaDia", cache: CacheOdds,
                     now: Optional[datetime] = None, agora_ts: Optional[float] = None) -> "FormaDia":
    """Atualiza a forma do dia no slot de resultados. Fora do slot, não chama a rede.

    A lista fica em DATA_DIR. Uma resposta vazia sem erro não apaga o que já foi
    gravado; erro de API também não. O mesmo slot só repete depois de ~60 s.
    """
    now = now or agora_cet()
    ts = time.time() if agora_ts is None else agora_ts
    slot = _slot_para_consultar(cache, now, ts, slot_resultados_atual)
    if slot is None:
        return forma
    dia_utc = now.astimezone(pytz.utc).strftime("%Y-%m-%d")
    lista, erro = _chamar_anotando_erro(lambda: moviodds.fetch_results(dia_utc))
    cache.tentativas[slot] = cache.tentativas.get(slot, 0) + 1
    cache.ultima_tentativa[slot] = ts
    cache.falhou[slot] = erro
    if not erro:
        forma.mesclar_movi(lista, now)
    log.info("[RESULTADOS] consulta %s -> %s jogos", slot.split("|", 1)[1], len(lista))
    return forma

def janela_rodada2(slot_key: str) -> Tuple[datetime, datetime]:
    """Para o slot 'YYYY-MM-DD|hh:55' retorna (início, fim) da 2ª rodada: hh+1:00 .. hh+1:50 CET."""
    dia, hm = slot_key.split("|")
    h = int(hm.split(":")[0])
    base = TZ.localize(datetime.strptime(dia, "%Y-%m-%d").replace(hour=h, minute=0))
    return base + timedelta(hours=1), base + timedelta(hours=1, minutes=50)

def proxima_entrada() -> str:
    """Não há mais um único hh:55. A mensagem sai cerca de 5 min antes de cada bloco."""
    return "≈5 min antes de cada início"

def chave_par(p1: str, p2: str) -> str:
    """Chave independente da ordem casa/fora."""
    a, b = sorted([p1.strip().lower(), p2.strip().lower()])
    return f"{a}|{b}"

def chave_sinal(p1: str, p2: str, dia: Optional[str] = None) -> str:
    dia = dia or agora_cet().strftime("%Y-%m-%d")
    return f"{dia}|{chave_par(p1, p2)}"

_SUFIXOS = {"jnr", "junior", "jr", "snr", "senior", "sr", "st", "ml"}
_WO_RE = re.compile(
    r"\b(w\s*\.?\s*o\.?|walk\s*over|walkover|retired|retirement|awarded|"
    r"cancel\w*|abandon\w*|desist\w*|incomplete|wo)\b",
    re.IGNORECASE,
)

def _sem_etiqueta(nome: str) -> str:
    """Tira {1964}, [ids] e parênteses numéricos antes de comparar o nome."""
    s = nome or ""
    s = re.sub(r"\{[^{}]*\}|\[[^\[\]]*\]|\(\s*\d[\d\s./-]*\)", " ", s)
    return re.sub(r"\s+", " ", s).strip()

def nome_exibicao(nome: str) -> str:
    """'Novak, Jan', 'NOVAK Jan' e '{1964} Bílek, Zdeněk' viram 'Jan Novak' / 'Zdenek Bilek'."""
    import unicodedata
    s = unicodedata.normalize("NFKD", _sem_etiqueta(nome)).encode("ascii", "ignore").decode()
    s = re.sub(r"\s+", " ", s).strip(" ,")
    if "," in s:
        sur, _, resto = s.partition(",")
        s = f"{resto.strip()} {sur.strip()}".strip()
    partes = [p for p in s.split() if p]
    if len(partes) >= 2 and partes[0].isalpha() and partes[0].isupper() and any(
            p.isalpha() and not p.isupper() for p in partes[1:]):
        partes = partes[1:] + partes[:1]
    saida = []
    for p in partes:
        saida.append(p.capitalize() if p.isalpha() else p)
    return " ".join(saida)

def norm_nome(nome: str) -> frozenset:
    """Tokens do nome sem ordem/acentos/sufixos/etiquetas: 'NOVAK, Jan {1964}' == 'Jan Novak'."""
    import unicodedata
    n = unicodedata.normalize("NFKD", _sem_etiqueta(nome)).encode("ascii", "ignore").decode().lower()
    toks = [t for t in re.split(r"[^a-z]+", n) if t and t not in _SUFIXOS]
    return frozenset(toks)

def placar_conta(sets_a, sets_b, texto: str = "", status: str = "") -> bool:
    """W.O., desistência, cancelado e placar incompleto não entram na forma."""
    if _WO_RE.search(f"{texto or ''} {status or ''}"):
        return False
    try:
        a, b = int(sets_a), int(sets_b)
    except (TypeError, ValueError):
        return False
    return max(a, b) == 3 and 0 <= min(a, b) <= 2

def mesmo_jogador(a: str, b: str) -> bool:
    na, nb = norm_nome(a), norm_nome(b)
    if not na or not nb:
        return False
    return na == nb or (min(len(na), len(nb)) >= 2 and (na <= nb or nb <= na))

# ══════════════════════════════════════════════════════════════════════════════
# TELEGRAM
# ══════════════════════════════════════════════════════════════════════════════

class Telegram:
    def __init__(self, token: str, chat_id: str):
        self.token = token
        self.chat_id = str(chat_id)          # destino padrão = grupo
        self.base = f"https://api.telegram.org/bot{token}"

    def send(self, text: str, chat_id: Optional[str] = None, reply_to: Optional[int] = None) -> bool:
        payload = {"chat_id": str(chat_id or self.chat_id), "text": text, "parse_mode": "HTML",
                   "disable_web_page_preview": True}
        if reply_to:
            payload["reply_parameters"] = {"message_id": reply_to, "allow_sending_without_reply": True}
        try:
            r = requests.post(f"{self.base}/sendMessage", json=payload, timeout=15)
            if r.status_code != 200:
                log.error(f"Telegram HTTP {r.status_code}: {r.text[:200]}")
            return r.status_code == 200
        except Exception as e:
            log.error(f"Telegram: {e}")
            return False

    def get_me(self) -> dict:
        try:
            r = requests.get(f"{self.base}/getMe", timeout=15)
            if r.status_code == 200:
                return r.json().get("result", {}) or {}
        except Exception:
            pass
        return {}

    def get_updates(self, offset: int = 0) -> list:
        try:
            r = requests.get(f"{self.base}/getUpdates", params={
                "offset": offset, "timeout": 8,
                "allowed_updates": json.dumps(["message", "channel_post", "my_chat_member"])}, timeout=15)
            if r.status_code == 200:
                self.conflitos_seguidos = 0
                return r.json().get("result", [])
            agora_ts = time.time()
            if r.status_code == 409:
                self.conflitos_seguidos = getattr(self, "conflitos_seguidos", 0) + 1
                if agora_ts - getattr(self, "_ult_log_409", 0) >= 60:
                    self._ult_log_409 = agora_ts
                    log.warning("Telegram 409 Conflict: OUTRO programa está lendo este bot (getUpdates) — "
                                "provavelmente a versão antiga no PC. Feche-a, senão comandos se perdem. "
                                f"{r.text[:150]}")
            elif agora_ts - getattr(self, "_ult_log_err", 0) >= 60:
                self._ult_log_err = agora_ts
                log.warning(f"getUpdates HTTP {r.status_code}: {r.text[:200]}")
        except Exception as e:
            agora_ts = time.time()
            if agora_ts - getattr(self, "_ult_log_exc", 0) >= 60:
                self._ult_log_exc = agora_ts
                log.warning(f"getUpdates erro: {e} — nova tentativa no próximo ciclo")
        return []

# ══════════════════════════════════════════════════════════════════════════════
# HISTÓRICO / CACHE
# ══════════════════════════════════════════════════════════════════════════════

class Historico:
    def __init__(self):
        self.data: Dict[str, dict] = {}
        self.load()

    def load(self):
        if HISTORY_FILE.exists():
            try:
                self.data = json.loads(HISTORY_FILE.read_text(encoding="utf-8"))
            except Exception:
                self.data = {}

    def save(self):
        HISTORY_FILE.write_text(json.dumps(self.data, ensure_ascii=False, indent=2), encoding="utf-8")

    def get(self, nome: str) -> Optional[dict]:
        """Nome exato (caixa ignorada) ou o mesmo jogador normalizado. Sem substring."""
        nome_l = nome.lower().strip()
        for k, v in self.data.items():
            if k.lower() == nome_l:
                return {**v, "_key": k}
        for k, v in self.data.items():
            if mesmo_jogador(k, nome):
                return {**v, "_key": k}
        return None

    def set_resultado(self, nome: str, resultado: str, sets_f: int = None, sets_c: int = None,
                      odd: float = None, inicio: Optional[datetime] = None):
        """Grava o último jogo do jogador (substitui a lista: um cenário de teste não acumula)."""
        self.definir_jogos(nome, [{
            "resultado": resultado,
            "sets_favor": sets_f,
            "sets_contra": sets_c,
            "odd": odd,
            "inicio": inicio,
        }])
        log.info(f"Histórico: {nome} → {resultado}" + (f" (odd {odd})" if odd else ""))

    def definir_jogos(self, nome: str, jogos: List[dict]):
        """Substitui os jogos do dia deste jogador. O último também fica nos campos planos."""
        key = nome
        existing = self.get(nome)
        if existing and existing.get("_key"):
            key = existing["_key"]
        norm = []
        for j in jogos:
            sf, sc = j.get("sets_favor"), j.get("sets_contra")
            res = j.get("resultado")
            if res is None and sf is not None and sc is not None:
                res = classificar(int(sf), int(sc))
            item = {"resultado": res, "sets_favor": sf, "sets_contra": sc}
            if j.get("odd") is not None:
                item["odd"] = j["odd"]
            ini = j.get("inicio")
            if isinstance(ini, datetime):
                item["inicio"] = _iso_inicio(ini)
            elif isinstance(ini, str) and ini:
                item["inicio"] = ini
            norm.append(item)
        last = norm[-1] if norm else {}
        entry = {
            "resultado": last.get("resultado"),
            "sets_favor": last.get("sets_favor"),
            "sets_contra": last.get("sets_contra"),
            "atualizado": agora_cet().strftime("%Y-%m-%d %H:%M:%S"),
            "jogos": norm,
        }
        if last.get("odd") is not None:
            entry["odd"] = last["odd"]
        if last.get("inicio"):
            entry["inicio"] = last["inicio"]
        self.data[key] = entry
        self.save()

    def limpar_antigo(self):
        agora = agora_cet()
        novos = {}
        for k, v in self.data.items():
            try:
                at = TZ.localize(datetime.strptime(v.get("atualizado", ""), "%Y-%m-%d %H:%M:%S"))
                if (agora - at).total_seconds() < 3 * 3600:
                    novos[k] = v
            except Exception:
                pass
        if len(novos) != len(self.data):
            self.data = novos
            self.save()

def _dt_de(valor) -> Optional[datetime]:
    if isinstance(valor, datetime):
        if valor.tzinfo is None:
            return TZ.localize(valor)
        return valor.astimezone(TZ)
    if not valor:
        return None
    return _ler_inicio({"inicio": valor})

def _normalizar_gravado(j: dict) -> Optional[dict]:
    """Garante início e fim. Registro antigo só com `quando`: esse campo é o início."""
    try:
        sh, sa = int(j["sets_home"]), int(j["sets_away"])
    except (KeyError, TypeError, ValueError):
        return None
    fim = _dt_de(j.get("fim"))
    inicio = _dt_de(j.get("inicio"))
    fim_estimado = bool(j.get("fim_estimado"))
    inicio_estimado = bool(j.get("inicio_estimado"))
    if fim is None and inicio is None:
        quando = _dt_de(j.get("quando"))
        if quando is None:
            return None
        inicio = quando
        fim = estimar_fim(inicio, sh, sa)
        fim_estimado = True
    elif fim is None:
        fim = estimar_fim(inicio, sh, sa)
        fim_estimado = True
    elif inicio is None:
        inicio = estimar_inicio(fim, sh, sa)
        inicio_estimado = True
    novo = dict(j)
    novo["sets_home"], novo["sets_away"] = sh, sa
    novo["inicio"] = inicio.isoformat()
    novo["fim"] = fim.isoformat()
    novo["quando"] = fim.isoformat()
    novo["fim_estimado"] = fim_estimado
    novo["inicio_estimado"] = inicio_estimado
    return novo

class FormaDia:
    """Jogos finalizados da Czech Liga Pro, com início e fim, em DATA_DIR.

    Cada consulta MoviOdds de resultados funde aqui. Sem `finished_at`, o fim é
    o início mais 15/20/25 min (3/4/5 sets). Sem início, o início é o fim menos
    essa duração. Arquivo antigo só com `quando` trata esse campo como início.
    A lista não zera à meia-noite: fica quem terminou nas últimas 8 h.
    Resposta vazia não apaga o que já foi gravado.
    """
    def __init__(self, path: Optional[Path] = None):
        self.path = path or FORMA_FILE
        self.dia = ""
        self.jogos: List[dict] = []
        self.load()

    def load(self):
        if self.path.exists():
            try:
                raw = json.loads(self.path.read_text(encoding="utf-8"))
                self.dia = raw.get("dia") or ""
                self.jogos = list(raw.get("jogos") or [])
            except Exception:
                self.dia = ""
                self.jogos = []

    def save(self):
        self.path.parent.mkdir(parents=True, exist_ok=True)
        tmp = self.path.with_suffix(".tmp")
        tmp.write_text(json.dumps({"dia": self.dia, "jogos": self.jogos}, ensure_ascii=False, indent=1),
                       encoding="utf-8")
        tmp.replace(self.path)

    def _podar(self, agora: datetime):
        limite = agora.astimezone(TZ) - timedelta(hours=RETENCAO_FORMA_H)
        novos = []
        for j in self.jogos:
            fim = _dt_de(j.get("fim") or j.get("quando"))
            if fim is None or fim >= limite:
                novos.append(j)
        if len(novos) != len(self.jogos):
            self.jogos = novos
            self.save()

    def _fundir(self, novos: List[dict]):
        idx = {j.get("id"): i for i, j in enumerate(self.jogos)}
        mudou = False
        for j in novos:
            i = idx.get(j.get("id"))
            if i is None:
                self.jogos.append(j)
                idx[j.get("id")] = len(self.jogos) - 1
                mudou = True
            elif self.jogos[i] != j:
                self.jogos[i] = j
                mudou = True
        if mudou:
            self.jogos.sort(key=lambda j: j.get("quando") or "")
            self.save()

    def _registro(self, bruto: dict, agora: datetime) -> Optional[dict]:
        norm = _normalizar_gravado(bruto)
        if norm is None:
            return None
        fim = _dt_de(norm.get("fim"))
        if fim is None or fim < agora.astimezone(TZ) - timedelta(hours=RETENCAO_FORMA_H):
            return None
        return norm

    def mesclar_movi(self, jogos: List[dict], agora: datetime):
        dia = agora.astimezone(TZ).strftime("%Y-%m-%d")
        dia_mudou = self.dia != dia
        self.dia = dia
        novos = []
        for j in jogos or []:
            if j.get("league") != "Czech Liga Pro":
                continue
            rec = self._registro({
                "id": j.get("id"),
                "home": j.get("home") or "",
                "away": j.get("away") or "",
                "sets_home": j.get("sets_home"),
                "sets_away": j.get("sets_away"),
                "inicio": j.get("inicio"),
                "fim": j.get("fim") or j.get("quando"),
                "quando": j.get("quando"),
                "fim_estimado": j.get("fim_estimado"),
                "inicio_estimado": j.get("inicio_estimado"),
                "league": "Czech Liga Pro",
            }, agora)
            if rec is None:
                continue
            if not rec.get("id"):
                rec["id"] = f"{rec['home']}|{rec['away']}|{rec['inicio']}"
            novos.append(rec)
        self._podar(agora)
        self._fundir(novos)
        if dia_mudou:
            self.save()

    def ingerir_resultados(self, resultados: List["Resultado"], agora: Optional[datetime] = None):
        """Aproveita resultados que o ScoreMondo já trouxe, sem chamada MoviOdds extra.

        A página só tem o horário de início. O fim é estimado pela quantidade de sets.
        """
        agora = agora or agora_cet()
        dia = agora.astimezone(TZ).strftime("%Y-%m-%d")
        dia_mudou = self.dia != dia
        self.dia = dia
        novos = []
        for r in resultados or []:
            if not r.kickoff or max(r.sets_home, r.sets_away) < 3:
                continue
            quando = r.kickoff if r.kickoff.tzinfo else TZ.localize(r.kickoff)
            rec = self._registro({
                "id": r.match_id or f"{r.home}|{r.away}|{quando.isoformat()}",
                "home": r.home, "away": r.away,
                "sets_home": r.sets_home, "sets_away": r.sets_away,
                "inicio": quando, "fim_estimado": True,
                "league": "Czech Liga Pro",
            }, agora)
            if rec:
                novos.append(rec)
        self._podar(agora)
        self._fundir(novos)
        if dia_mudou:
            self.save()

    def partidas_de(self, nome: str) -> List[dict]:
        """Partidas deste jogador ainda no arquivo, com fim, início e adversário."""
        out = []
        for j in self.jogos:
            if j.get("league") not in (None, "", "Czech Liga Pro"):
                continue
            norm = _normalizar_gravado(j)
            if norm is None:
                continue
            if mesmo_jogador(norm.get("home") or "", nome):
                sf, sc = norm["sets_home"], norm["sets_away"]
                adv = norm.get("away") or ""
            elif mesmo_jogador(norm.get("away") or "", nome):
                sf, sc = norm["sets_away"], norm["sets_home"]
                adv = norm.get("home") or ""
            else:
                continue
            inicio, fim = _dt_de(norm.get("inicio")), _dt_de(norm.get("fim"))
            if fim is None:
                continue
            sf, sc = int(sf), int(sc)
            if not placar_conta(sf, sc, j.get("texto") or "", j.get("status") or ""):
                continue
            out.append({
                "resultado": classificar(sf, sc),
                "sets_favor": sf,
                "sets_contra": sc,
                "inicio": inicio or fim,
                "fim": fim,
                "adversario": adv,
                "fim_estimado": bool(norm.get("fim_estimado")),
            })
        out.sort(key=lambda x: x["fim"])
        return out

    def do_jogador(self, nome: str, dia: str) -> List[dict]:
        out = []
        for p in self.partidas_de(nome):
            ref = p.get("fim") or p.get("inicio")
            if dia and ref is not None and _dia_local(ref) != dia:
                ini = p.get("inicio")
                if ini is None or _dia_local(ini) != dia:
                    continue
            out.append(p)
        return out

class CacheSet:
    """Conjunto persistido em JSON que mantém a ordem de inserção (descarta os mais antigos)."""
    def __init__(self, path: Path, limite: int = 500):
        self.path = path
        self.limite = limite
        self.ids: Dict[str, None] = {}
        if path.exists():
            try:
                self.ids = dict.fromkeys(json.loads(path.read_text()))
            except Exception:
                pass

    def has(self, key: str) -> bool:
        return key in self.ids

    def add(self, key: str):
        self.ids[key] = None
        if len(self.ids) > self.limite:
            self.ids = dict.fromkeys(list(self.ids)[-(self.limite * 2 // 3):])
        self.path.write_text(json.dumps(list(self.ids)))

# ══════════════════════════════════════════════════════════════════════════════
# MOVIODDS (odds bet365)
# ══════════════════════════════════════════════════════════════════════════════

@dataclass
class OddsMatch:
    home: str
    away: str
    odd_home: Optional[float]
    odd_away: Optional[float]
    in_play: bool
    score: Optional[str] = None
    kickoff: Optional[datetime] = None   # horário de início (CET), se a API informar

    # compatibilidade com avaliar()
    @property
    def player1(self) -> str:
        return self.home

    @property
    def player2(self) -> str:
        return self.away

def _odds_para_dict(o: "OddsMatch") -> dict:
    ko = None
    if o.kickoff is not None:
        local = o.kickoff if o.kickoff.tzinfo else TZ.localize(o.kickoff)
        ko = local.astimezone(TZ).isoformat()
    return {
        "home": o.home, "away": o.away,
        "odd_home": o.odd_home, "odd_away": o.odd_away,
        "in_play": bool(o.in_play), "score": o.score, "kickoff": ko,
    }

def _odds_de_dict(d: dict) -> "OddsMatch":
    return OddsMatch(
        d.get("home") or "", d.get("away") or "",
        d.get("odd_home"), d.get("odd_away"),
        bool(d.get("in_play")), d.get("score"),
        _parse_kickoff(d.get("kickoff")),
    )

def _sets_de_placar(texto: str) -> Optional[Tuple[int, int]]:
    """'3-1' são sets. '11-7,11-9,11-5' são games e viram sets ganhos."""
    s = (texto or "").strip()
    if not s:
        return None
    if "," in s:
        hw = aw = 0
        for part in s.split(","):
            m = re.match(r"^\s*(\d+)\s*-\s*(\d+)\s*$", part)
            if not m:
                return None
            a, b = int(m.group(1)), int(m.group(2))
            if a > b:
                hw += 1
            elif b > a:
                aw += 1
        return hw, aw
    m = re.match(r"^\s*(\d+)\s*-\s*(\d+)\s*$", s)
    if not m:
        return None
    return int(m.group(1)), int(m.group(2))

def _parse_kickoff(v) -> Optional[datetime]:
    if not v:
        return None
    try:
        dt = datetime.fromisoformat(str(v).replace("Z", "+00:00"))
        if dt.tzinfo is None:
            dt = pytz.utc.localize(dt)
        return dt.astimezone(TZ)
    except Exception:
        return None

class MoviOdds:
    """Odds bet365. keys é [MOVIODDS_KEY, MOVIODDS_KEY_2]; vazias são ignoradas.

    A primeira chave é a principal. Se a requisição falhar com HTTP 401, 403,
    429, 5xx ou erro de rede, a mesma chamada é repetida uma vez com a próxima
    chave. A reserva segue em uso por 30 minutos; depois a principal é tentada
    de novo. Sem chave, fetch_czech devolve [].
    """

    URL = "https://moviodds.com/odds"
    RESULTS_URL = "https://moviodds.com/results"
    BACKUP_HOLD_SECONDS = 30 * 60
    _FAILOVER_HTTP = frozenset({401, 403, 429})
    _NETWORK_ERRORS = (
        requests.ConnectionError,
        requests.Timeout,
        requests.exceptions.ChunkedEncodingError,
    )

    def __init__(self, keys: str | List[str] | None):
        if keys is None:
            raw: List = []
        elif isinstance(keys, str):
            raw = [keys]
        else:
            raw = list(keys)
        self.keys: List[str] = []
        for key in raw:
            if not isinstance(key, str):
                continue
            cleaned = key.strip()
            if cleaned:
                self.keys.append(cleaned)
        self._backup_until: Optional[float] = None

    def fetch_czech(self) -> List[OddsMatch]:
        return self._run(self.URL, {"sport": "table_tennis"}, self.parse)

    def fetch_results(self, date_utc: str) -> List[dict]:
        """Jogos finalizados. date_utc é o dia UTC da consulta (uma chamada)."""
        return self._run(
            self.RESULTS_URL,
            {"sport": "table_tennis", "date": date_utc},
            self.parse_results,
        )

    def _run(self, url: str, params: dict, parse):
        if not self.keys:
            return []   # MoviOdds é opcional
        use_backup = self._backup_active()
        key = self.keys[1] if use_backup else self.keys[0]
        try:
            found = parse(self._fetch_json(key, url, params))
        except Exception as e:
            if (not use_backup) and len(self.keys) > 1 and self._should_failover(e):
                self._backup_until = time.monotonic() + self.BACKUP_HOLD_SECONDS
                log.warning(
                    "MoviOdds: chave reserva em uso por %s min (falha da principal: %s)",
                    self.BACKUP_HOLD_SECONDS // 60,
                    self._fail_reason(e),
                )
                try:
                    return parse(self._fetch_json(self.keys[1], url, params))
                except Exception as backup_error:
                    log.warning(f"MoviOdds erro: {self._safe_error(backup_error)}")
                    return []
            log.warning(f"MoviOdds erro: {self._safe_error(e)}")
            return []
        if not use_backup:
            self._backup_until = None
        return found

    def _backup_active(self) -> bool:
        return (
            len(self.keys) > 1
            and self._backup_until is not None
            and time.monotonic() < self._backup_until
        )

    def _fetch_json(self, key: str, url: str, params: dict) -> dict:
        r = requests.get(url, params=params, headers={"x-api-key": key}, timeout=20)
        r.raise_for_status()
        return r.json()

    def _should_failover(self, exc: BaseException) -> bool:
        if isinstance(exc, requests.HTTPError):
            code = getattr(getattr(exc, "response", None), "status_code", None)
            return code in self._FAILOVER_HTTP or (isinstance(code, int) and 500 <= code <= 599)
        return isinstance(exc, self._NETWORK_ERRORS)

    @staticmethod
    def _fail_reason(exc: BaseException) -> str:
        if isinstance(exc, requests.HTTPError):
            code = getattr(getattr(exc, "response", None), "status_code", None)
            if isinstance(code, int):
                return f"HTTP {code}"
        return "erro de rede"

    def _safe_error(self, exc: BaseException) -> str:
        text = str(exc)
        for key in sorted(self.keys, key=len, reverse=True):
            if key:
                text = text.replace(key, "***")
        return text

    @staticmethod
    def parse(data: dict) -> List[OddsMatch]:
        out = []
        for m in data.get("matches", []):
            if not eh_czech_liga_pro(m.get("league")):
                continue
            home, away = m.get("home", ""), m.get("away", "")
            odd_h = odd_a = None
            for q in m.get("quotes") or []:
                if not _e_mercado_vencedor(q):
                    continue
                side = (q.get("side") or "").lower()
                if side == home.lower() or (side and home.lower() in side):
                    odd_h = float(q["odds_dec"])
                elif side == away.lower() or (side and away.lower() in side):
                    odd_a = float(q["odds_dec"])
            if odd_h is None or odd_a is None:
                for q in m.get("quotes") or []:
                    if not _e_mercado_vencedor(q):
                        continue
                    label = (q.get("label") or q.get("side") or "").lower()
                    if home.lower() in label:
                        odd_h = float(q["odds_dec"])
                    elif away.lower() in label:
                        odd_a = float(q["odds_dec"])
            out.append(OddsMatch(home, away, odd_h, odd_a, bool(m.get("in_play")), m.get("score"),
                                 _parse_kickoff(m.get("kickoff_utc"))))
        return out

    @staticmethod
    def parse_results(data: dict) -> List[dict]:
        """Só Czech Liga Pro, status finished, placar de sets (3-0, 3-1, 3-2 e o inverso)."""
        out = []
        for m in data.get("results") or []:
            if not eh_czech_liga_pro(m.get("league")) or m.get("status") != "finished":
                continue
            texto_placar = m.get("final_score") or ""
            extra = " ".join(str(m.get(k) or "") for k in ("status", "note", "comment", "info"))
            sets = _sets_de_placar(texto_placar)
            if not sets:
                continue
            sh, sa = sets
            if not placar_conta(sh, sa, texto_placar, extra):
                continue
            inicio = _parse_kickoff(m.get("kickoff_utc"))
            fim = _parse_kickoff(m.get("finished_at"))
            fim_estimado = False
            inicio_estimado = False
            if fim is None and inicio is None:
                continue
            if fim is None:
                # A API não mandou o fim: início + duração estimada pelo número de sets.
                fim = estimar_fim(inicio, sh, sa)
                fim_estimado = True
            elif inicio is None:
                inicio = estimar_inicio(fim, sh, sa)
                inicio_estimado = True
            out.append({
                "id": str(m.get("fixture_id") or "") or None,
                "home": m.get("home") or "",
                "away": m.get("away") or "",
                "sets_home": sh,
                "sets_away": sa,
                "quando": fim,
                "inicio": inicio,
                "fim": fim,
                "fim_estimado": fim_estimado,
                "inicio_estimado": inicio_estimado,
                "league": "Czech Liga Pro",
            })
        return out

def eh_czech_liga_pro(nome: Optional[str]) -> bool:
    """Czech Liga Pro e os nomes que a mesma liga usa nas fontes (não outras ligas)."""
    n = re.sub(r"[^a-z0-9]+", " ", (nome or "").lower()).strip()
    if any(p in n.split() for p in ("women", "woman", "feminino", "feminina")):
        return False
    if n in {
        "czech liga pro",
        "czechia liga pro",
        "czech republic liga pro",
        "czechia czech liga pro",
    }:
        return True
    return "czech" in n.split() and "liga pro" in n

def _e_mercado_vencedor(q: dict) -> bool:
    """To Win Match / Match, ou o mercado de tênis de mesa Game + line To Win."""
    odd = q.get("odds_dec")
    if not odd or not odd > 1:
        return False
    nome = (q.get("group_name") or "").strip()
    if nome in ("To Win Match", "Match"):
        return True
    linha = (q.get("line") or "").strip().lower()
    return nome == "Game" and linha in ("to win", "to win match")

def achar_odds(p1: str, p2: str, odds_list: List[OddsMatch]) -> Optional[OddsMatch]:
    for o in odds_list:
        if (mesmo_jogador(o.home, p1) and mesmo_jogador(o.away, p2)) or \
           (mesmo_jogador(o.home, p2) and mesmo_jogador(o.away, p1)):
            return o
    return None

def com_odds(fixtures: List[OddsMatch], odds_list: List[OddsMatch]) -> List[OddsMatch]:
    """Copia as odds do MoviOdds (se houver) para os confrontos do ScoreMondo."""
    out = []
    for f in fixtures:
        o = achar_odds(f.home, f.away, [x for x in odds_list if not x.in_play])
        oh = oa = None
        if o:
            if mesmo_jogador(o.home, f.home):
                oh, oa = o.odd_home, o.odd_away
            else:
                oh, oa = o.odd_away, o.odd_home
        out.append(OddsMatch(f.home, f.away, oh, oa, f.in_play, f.score, f.kickoff))
    return out

def _kickoff_local(dt: Optional[datetime]) -> Optional[datetime]:
    if dt is None:
        return None
    if dt.tzinfo is None:
        return TZ.localize(dt)
    return dt.astimezone(TZ)

def chave_bloco(kickoff: datetime) -> str:
    return _kickoff_local(kickoff).strftime("%Y-%m-%d|%H:%M")

def _delta_inicio(kickoff: datetime, now: datetime) -> float:
    return (_kickoff_local(kickoff) - now.astimezone(TZ)).total_seconds()

def slot_alerta_atual(now: Optional[datetime] = None) -> Optional[str]:
    """Bloco a avisar agora, em horário de Praga.

    :25–:29 avisa o apito das :30. :55–:59 avisa o das :00 da hora seguinte.
    A folga existe porque o ciclo acorda a cada ~40 s e pode passar do minuto exato.
    """
    agora = (now or agora_cet()).astimezone(TZ)
    if 25 <= agora.minute <= 25 + ALERTA_FOLGA_MIN:
        alvo = agora.replace(minute=30, second=0, microsecond=0)
    elif 55 <= agora.minute <= 55 + ALERTA_FOLGA_MIN:
        alvo = (agora.replace(minute=0, second=0, microsecond=0) + timedelta(hours=1))
    else:
        return None
    return alvo.strftime("%Y-%m-%d|%H:%M")

def dentro_da_antecedencia(kickoff: datetime, now: datetime) -> bool:
    """O apito das :00/:30 está na janela do alerta (:55–:59 ou :25–:29)."""
    slot = slot_alerta_atual(now)
    if not slot or kickoff is None:
        return False
    ko = _kickoff_local(kickoff)
    if ko.minute not in (0, 30):
        return False
    return chave_bloco(kickoff) == slot

def dentro_do_fallback(kickoff: datetime, now: datetime) -> bool:
    """O alerta não sai fora da janela das :25 e :55."""
    return False

def _jogo_ainda_vai_comecar(o: "OddsMatch", now: Optional[datetime] = None) -> bool:
    """Apito ainda à frente. Um in_play adiantado não esconde o jogo do bloco."""
    if o is None or o.kickoff is None:
        return False
    agora = (now or agora_cet()).astimezone(TZ)
    return _kickoff_local(o.kickoff) > agora

def jogos_comecando_em(jogos: List[OddsMatch], now: datetime, segundos: float) -> bool:
    for o in jogos or []:
        if o.in_play or o.kickoff is None:
            continue
        delta = _delta_inicio(o.kickoff, now)
        if 0 < delta <= segundos:
            return True
    return False

def coletar_agenda(jogos: List[OddsMatch], agora: datetime,
                   vistos: Optional[List[OddsMatch]] = None) -> List[OddsMatch]:
    """Grade recente, pré-jogo e ao vivo, mais inícios já vistos nas últimas 4 h.

    O bloqueio de horário anterior usa esta lista quando o resultado do jogo
    anterior ainda não foi gravado. O próprio confronto em avaliação não entra
    duas vezes: a chave é o par e o minuto de início.
    """
    agora = agora.astimezone(TZ)
    limite = agora - timedelta(hours=JANELA_SCORE_H)
    por: Dict[Tuple[str, str], OddsMatch] = {}
    for o in list(vistos or []) + list(jogos or []):
        if o is None or o.kickoff is None:
            continue
        ko = _kickoff_local(o.kickoff)
        if ko < limite:
            continue
        chave = (chave_par(o.home, o.away), ko.strftime("%Y-%m-%d|%H:%M"))
        por[chave] = OddsMatch(o.home, o.away, o.odd_home, o.odd_away, bool(o.in_play), o.score, ko)
    return list(por.values())

def fonte_entrada(fixtures: List[OddsMatch], odds_list: List[OddsMatch]) -> List[OddsMatch]:
    """Une fixtures do ScoreMondo e jogos do MoviOdds.

    O horário fica com quem o tiver. A odd vem do MoviOdds. Um jogo que só está
    nas odds não some porque a página de fixtures listou outros horários.
    """
    por_par: Dict[str, OddsMatch] = {}
    for o in odds_list or []:
        if o.in_play and not _jogo_ainda_vai_comecar(o):
            continue
        por_par[chave_par(o.home, o.away)] = o
    out: List[OddsMatch] = []
    vistos = set()
    for f in fixtures or []:
        if f.in_play and not _jogo_ainda_vai_comecar(f):
            continue
        k = chave_par(f.home, f.away)
        o = por_par.get(k)
        ko = f.kickoff or (o.kickoff if o else None)
        oh = oa = None
        if o:
            if mesmo_jogador(o.home, f.home):
                oh, oa = o.odd_home, o.odd_away
            else:
                oh, oa = o.odd_away, o.odd_home
        out.append(OddsMatch(f.home, f.away, oh, oa, False, f.score, ko))
        vistos.add(k)
    for k, o in por_par.items():
        if k not in vistos:
            out.append(o)
    return out

def _dedupe_pre(jogos: List[OddsMatch], now: Optional[datetime] = None) -> List[OddsMatch]:
    out, vistos = [], set()
    for o in jogos:
        if o.kickoff is None or not _jogo_ainda_vai_comecar(o, now):
            continue
        k = chave_par(o.home, o.away)
        if k in vistos:
            continue
        vistos.add(k)
        out.append(o)
    return out

def _alvo_bloco(slot_key: str) -> str:
    partes = slot_key.split("|")
    return f"{partes[0]}|{partes[1][:5]}"

def instante_bloco(slot_key: str) -> datetime:
    dia, hm = _alvo_bloco(slot_key).split("|")
    hh, mm = hm.split(":")
    return TZ.localize(datetime.strptime(dia, "%Y-%m-%d").replace(hour=int(hh), minute=int(mm)))

def confrontos_do_bloco(odds_list: List[OddsMatch], slot_key: str,
                        incluir_ao_vivo: bool = False) -> List[OddsMatch]:
    """Jogos do apito do slot que ainda não começaram. Sem horário, ficam de fora.

    No alerta, incluir_ao_vivo=True: a casa às vezes marca in_play minutos antes do apito.
    """
    alvo = _alvo_bloco(slot_key)
    agora = agora_cet()
    escolhidos = []
    for o in odds_list or []:
        if not _jogo_ainda_vai_comecar(o, agora) or chave_bloco(o.kickoff) != alvo:
            continue
        if o.in_play and not incluir_ao_vivo:
            continue
        escolhidos.append(o)
    return _dedupe_pre(escolhidos, agora)

def confrontos_rodada2(odds_list: List[OddsMatch], slot_key: str) -> List[OddsMatch]:
    """O slot é o minuto de início do bloco, não mais a hora cheia seguinte."""
    return confrontos_do_bloco(odds_list, slot_key)

def blocos_devidos(jogos: List[OddsMatch], now: Optional[datetime] = None) -> List[Tuple[str, List[OddsMatch]]]:
    """Bloco das :00 ou :30 que está na janela do alerta. Independente do modo."""
    now = now or agora_cet()
    grupos: Dict[str, List[OddsMatch]] = {}
    for o in jogos or []:
        if not _jogo_ainda_vai_comecar(o, now) or not dentro_da_antecedencia(o.kickoff, now):
            continue
        grupos.setdefault(chave_bloco(o.kickoff), []).append(o)
    return [(k, _dedupe_pre(v, now)) for k, v in sorted(grupos.items())]

# ══════════════════════════════════════════════════════════════════════════════
# SCOREMONDO (placar)
# ══════════════════════════════════════════════════════════════════════════════

@dataclass
class LiveMatch:
    player1: str
    player2: str
    score1: Optional[int] = None
    score2: Optional[int] = None
    current_set: Optional[str] = None
    finished: bool = False
    kickoff: Optional[datetime] = None

@dataclass
class Resultado:
    home: str
    away: str
    sets_home: int
    sets_away: int
    kickoff: Optional[datetime]
    match_id: str

class ScoreMondo:
    URL = "https://scoremondo.com/en/table-tennis/live"
    # Páginas públicas da liga (robots.txt permite; só /api/ é bloqueado)
    LIGA_URL = "https://scoremondo.com/en/competition/czechia-czech-liga-pro-18275895"
    HEADERS = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"}
    STOPS = ["TT Star Series", "Masters League", "Setka Cup", "TT Elite", "Next matches", "All of today’s"]

    def fetch(self) -> List[LiveMatch]:
        try:
            r = requests.get(self.URL, headers=self.HEADERS, timeout=12)
            r.raise_for_status()
            return self._parse(r.text)
        except Exception as e:
            log.warning(f"ScoreMondo: {e}")
            return []

    def _get(self, url: str) -> Optional[str]:
        try:
            r = requests.get(url, headers=self.HEADERS, timeout=15)
            r.raise_for_status()
            return r.text
        except Exception as e:
            log.warning(f"ScoreMondo {url.rsplit('/', 1)[-1]}: {e}")
            return None

    def fetch_fixtures(self) -> List[OddsMatch]:
        """Próximos jogos da Czech Liga Pro (≈ 14 h à frente), com horário. Sem odds."""
        html = self._get(self.LIGA_URL + "/fixtures")
        return self.parse_fixtures(html) if html else []

    def fetch_results(self) -> List[Resultado]:
        """Últimos ~40 resultados da Czech Liga Pro (placar em sets + horário de início)."""
        html = self._get(self.LIGA_URL + "/results")
        return self.parse_results(html) if html else []

    @staticmethod
    def parse_fixtures(html: str) -> List[OddsMatch]:
        soup = BeautifulSoup(html, "html.parser")
        out, vistos = [], set()
        for d in soup.select("div.m[data-id]"):
            nomes = [n.get_text(strip=True) for n in d.select(".nm")]
            if len(nomes) < 2 or d["data-id"] in vistos:
                continue
            vistos.add(d["data-id"])
            ko = None
            try:
                ko = datetime.fromtimestamp(int(d.get("data-t")), TZ)
            except Exception:
                t = d.find("time")
                ko = _parse_kickoff(t.get("datetime")) if t else None
            em_jogo = "st-pre" not in (d.get("class") or [])
            out.append(OddsMatch(nomes[0], nomes[1], None, None, em_jogo, None, ko))
        return out

    @staticmethod
    def parse_results(html: str) -> List[Resultado]:
        soup = BeautifulSoup(html, "html.parser")
        out = []
        for a in soup.select("a.rr"):
            nomes = [n.get_text(strip=True) for n in a.select(".rr-t .nm")]
            sc = a.select_one(".rr-s")
            m = re.match(r"^\s*(\d+)\s*-\s*(\d+)\s*$", sc.get_text() if sc else "")
            if len(nomes) < 2 or not m:
                continue
            t = a.find("time")
            ko = _parse_kickoff(t.get("datetime")) if t else None
            mid = (a.get("href") or "").rsplit("-", 1)[-1]
            out.append(Resultado(nomes[0], nomes[1], int(m.group(1)), int(m.group(2)), ko, mid))
        return out

    def _parse(self, html: str) -> List[LiveMatch]:
        soup = BeautifulSoup(html, "html.parser")
        text = soup.get_text(separator="\n")
        if "Czech Liga Pro" not in text:
            return []
        after = text.split("Czech Liga Pro", 1)[1]
        # corta no PRIMEIRO marcador encontrado (v3 cortava no primeiro da lista)
        cortes = [after.find(s) for s in self.STOPS if s in after]
        if cortes:
            after = after[:min(cortes)]
        lines = [l.strip() for l in after.split("\n") if l.strip()]
        # corta também no próximo cabeçalho de liga: País / Liga / nº de jogos / S#
        for k in range(len(lines) - 3):
            if (not re.match(r"^(\d+|S\d+)$", lines[k]) and not re.match(r"^(\d+|S\d+)$", lines[k+1])
                    and re.match(r"^\d+$", lines[k+2]) and re.match(r"^S\d+$", lines[k+3])):
                lines = lines[:k]
                break
        matches = []
        i = 0
        while i < len(lines):
            if re.match(r"^S\d+$", lines[i]):
                cs = lines[i]
                if i + 2 < len(lines):
                    p1, p2 = lines[i+1], lines[i+2]
                    nums, j = [], i + 3
                    while j < len(lines) and re.match(r"^\d+$", lines[j]):
                        nums.append(int(lines[j]))
                        j += 1
                    s1 = s2 = None
                    finished = False
                    if len(nums) >= 2:
                        s1, s2 = nums[-2], nums[-1]
                        if s1 >= 3 or s2 >= 3:
                            finished = True
                    matches.append(LiveMatch(p1, p2, s1, s2, cs, finished))
                    i = j
                    continue
            i += 1
        return matches

# ══════════════════════════════════════════════════════════════════════════════
# FILTRO
# ══════════════════════════════════════════════════════════════════════════════

def _iso_inicio(inicio: datetime) -> str:
    if inicio.tzinfo is None:
        inicio = TZ.localize(inicio)
    return inicio.astimezone(TZ).isoformat()

def _ler_inicio(entry: dict) -> Optional[datetime]:
    raw = entry.get("inicio")
    if isinstance(raw, datetime):
        dt = raw
    elif isinstance(raw, str) and raw:
        try:
            dt = datetime.fromisoformat(raw)
        except ValueError:
            return None
    else:
        return None
    if dt.tzinfo is None:
        dt = TZ.localize(dt)
    return dt.astimezone(TZ)

def _no_dia(ref: datetime, hour: int, minute: int) -> datetime:
    local = ref.astimezone(TZ)
    return TZ.localize(datetime(local.year, local.month, local.day, hour, minute))

def _janela_r1_inicio(agora: datetime) -> Optional[Tuple[datetime, datetime]]:
    """Se agora está na janela de gravar a 1ª rodada, devolve hh:00 .. hh:50 desse ciclo."""
    local = agora.astimezone(TZ)
    t = local.time()
    for h1, m1, h2, m2 in JANELAS_R1:
        if dtime(h1, m1) <= t <= dtime(h2, m2, 59):
            return _no_dia(local, h1, 0), _no_dia(local, h1, 50)
    return None

def _janela_r2_inicio(agora: datetime) -> Optional[Tuple[datetime, datetime]]:
    """Se agora está na 2ª rodada, devolve o intervalo hh+1:00 .. hh+1:50 desse ciclo."""
    local = agora.astimezone(TZ)
    t = local.time()
    for h1, m1, h2, m2 in JANELAS_R2:
        if dtime(h1, m1) <= t <= dtime(h2, m2, 59):
            return _no_dia(local, h1, m1), _no_dia(local, h2, m2)
    return None

def _kickoff_conhecido(m, odds_list: List[OddsMatch]) -> Optional[datetime]:
    ko = getattr(m, "kickoff", None)
    if ko is not None:
        return ko
    o = achar_odds(m.player1, m.player2, odds_list)
    return o.kickoff if o else None

def _tem_odd_ao_vivo(p1: str, p2: str, odds_list: List[OddsMatch]) -> bool:
    for o in odds_list:
        if not o.in_play:
            continue
        if (mesmo_jogador(o.home, p1) and mesmo_jogador(o.away, p2)) or \
           (mesmo_jogador(o.home, p2) and mesmo_jogador(o.away, p1)):
            return True
    return False

def _odd_do_jogador(player: str, o: Optional[OddsMatch]) -> Optional[float]:
    if not o:
        return None
    if mesmo_jogador(o.home, player):
        return o.odd_home
    if mesmo_jogador(o.away, player):
        return o.odd_away
    return None

def classificar(sf: int, sc: int) -> str:
    if sf == 3 and sc <= 1:
        return "limpo"
    if sf == 3 and sc == 2:
        return "desgaste"
    if sc == 3:
        return "derrota"
    return "nao"

def _html(nome: str) -> str:
    """Escapa nome de jogador para o parse_mode HTML do Telegram."""
    return html.escape(" ".join(str(nome or "").split()), quote=False)

def _dia_local(ref: Optional[datetime]) -> str:
    base = ref or agora_cet()
    if base.tzinfo is None:
        base = TZ.localize(base)
    return base.astimezone(TZ).strftime("%Y-%m-%d")

@dataclass
class FormaJogador:
    nome: str
    score_forma: float
    jogos_hoje: int
    vitorias_limpas_seguidas: int
    desgaste_ultimo_jogo: bool
    perdeu_ultimo_jogo: bool
    partidas: List[dict]

@dataclass
class Decisao:
    status: str
    motivos: List[str]
    alvo: Optional[str] = None
    gap: Optional[float] = None
    odd: Optional[float] = None
    score_alvo: Optional[float] = None
    score_adv: Optional[float] = None
    bonus: float = 0.0

def _fmt_score(n: float) -> str:
    return f"{n:.1f}"

def _partida_duplicada(novo: dict, existentes: List[dict]) -> bool:
    for e in existentes:
        if novo["sets_favor"] != e["sets_favor"] or novo["sets_contra"] != e["sets_contra"]:
            continue
        ini_n, ini_e = novo.get("inicio"), e.get("inicio")
        if ini_n and ini_e and abs((ini_n - ini_e).total_seconds()) <= 3 * 60:
            return True
        adv_n, adv_e = novo.get("adversario") or "", e.get("adversario") or ""
        if adv_n and adv_e and mesmo_jogador(adv_n, adv_e):
            fn, fe = novo.get("fim"), e.get("fim")
            if fn and fe and abs((fn - fe).total_seconds()) <= 2 * 3600:
                return True
        if not adv_n:
            fn, fe = novo.get("fim"), e.get("fim")
            if fn and fe and abs((fn - fe).total_seconds()) <= 15 * 60:
                return True
    return False

def _partidas_historico(entry: Optional[dict]) -> List[dict]:
    """Jogos do histórico local. Sem fim gravado, estima a partir do início."""
    if not entry:
        return []
    itens = entry.get("jogos") or [entry]
    out = []
    for j in itens:
        if not isinstance(j, dict):
            continue
        sf, sc = j.get("sets_favor"), j.get("sets_contra")
        if sf is None or sc is None:
            continue
        sf, sc = int(sf), int(sc)
        if not placar_conta(sf, sc, j.get("texto") or "", j.get("status") or ""):
            continue
        ini = _ler_inicio(j) or _ler_inicio(entry)
        if ini is None:
            continue
        fim = _dt_de(j.get("fim"))
        estimado = fim is None
        if fim is None:
            fim = estimar_fim(ini, sf, sc)
        out.append({
            "resultado": j.get("resultado") or classificar(sf, sc),
            "sets_favor": sf,
            "sets_contra": sc,
            "inicio": ini,
            "fim": fim,
            "adversario": j.get("adversario") or "",
            "fim_estimado": estimado,
        })
    return out

def partidas_do_jogador(nome: str, hist: Optional[Historico],
                        forma: Optional[FormaDia]) -> List[dict]:
    """Forma do MoviOdds primeiro (tem adversário e fim). O histórico só completa."""
    jogos = forma.partidas_de(nome) if forma is not None else []
    entry = hist.get(nome) if hist is not None else None
    for j in _partidas_historico(entry):
        if not _partida_duplicada(j, jogos):
            jogos.append(j)
    jogos.sort(key=lambda j: j.get("fim") or j.get("inicio"))
    return jogos

def metricas_forma(nome: str, partidas: List[dict], agora: datetime) -> FormaJogador:
    """score nos últimos 2–3 jogos de 4 h; jogos_hoje conta os finalizados em 3 h."""
    agora = _kickoff_local(agora)
    limite_4h = agora - timedelta(hours=JANELA_SCORE_H)
    dentro = []
    for p in partidas or []:
        fim = p.get("fim")
        if fim is None and p.get("inicio") is not None:
            fim = estimar_fim(p["inicio"], p["sets_favor"], p["sets_contra"])
        if fim is None:
            continue
        fim = _kickoff_local(fim)
        if fim > agora or fim < limite_4h:
            continue
        if not placar_conta(p.get("sets_favor"), p.get("sets_contra"),
                            p.get("texto") or "", p.get("status") or ""):
            continue
        q = dict(p)
        q["fim"] = fim
        if q.get("inicio") is not None:
            q["inicio"] = _kickoff_local(q["inicio"])
        dentro.append(q)
    dentro.sort(key=lambda p: p["fim"])
    recentes = dentro[-MAX_JOGOS_SCORE:]
    score = sum(peso_sets(p["sets_favor"], p["sets_contra"]) for p in recentes)
    limite_3h = agora - timedelta(hours=JANELA_JOGOS_H)
    jogos_hoje = sum(1 for p in dentro if p["fim"] >= limite_3h)
    streak = 0
    for p in reversed(recentes):
        if int(p["sets_favor"]) == 3 and int(p["sets_contra"]) in (0, 1):
            streak += 1
        else:
            break
    desgaste = False
    perdeu = False
    if recentes:
        ult = recentes[-1]
        perdeu = int(ult["sets_contra"]) == 3
        cinco = int(ult["sets_favor"]) + int(ult["sets_contra"]) == 5
        minutos = (agora - ult["fim"]).total_seconds() / 60.0
        desgaste = bool(cinco and minutos < DESGASTE_MIN)
    return FormaJogador(nome, score, jogos_hoje, streak, desgaste, perdeu, dentro)

def _mapa_adversarios(partidas: List[dict], agora: datetime) -> Dict[tuple, dict]:
    limite = _kickoff_local(agora) - timedelta(hours=JANELA_TRIANG_H)
    out: Dict[tuple, dict] = {}
    for p in partidas or []:
        nome = p.get("adversario") or ""
        fim = p.get("fim")
        if not nome or fim is None or _kickoff_local(fim) < limite:
            continue
        chave = tuple(sorted(norm_nome(nome)))
        if not chave:
            continue
        atual = out.get(chave)
        if atual is None or _kickoff_local(fim) >= _kickoff_local(atual["fim"]):
            out[chave] = p
    return out

def bonus_triangulacao(alvo: FormaJogador, adv: FormaJogador, agora: datetime) -> float:
    """Adversário comum nas últimas 3 h. +2.0 ou +1.0 por C, sem somar os dois no mesmo C."""
    ma = _mapa_adversarios(alvo.partidas, agora)
    mb = _mapa_adversarios(adv.partidas, agora)
    total = 0.0
    for chave in ma.keys() & mb.keys():
        pa, pb = ma[chave], mb[chave]
        a_sf, a_sc = int(pa["sets_favor"]), int(pa["sets_contra"])
        b_sf, b_sc = int(pb["sets_favor"]), int(pb["sets_contra"])
        if (a_sf, a_sc) in ((3, 0), (3, 1)) and (b_sf, b_sc) in ((0, 3), (1, 3)):
            total += 2.0
        elif (a_sf, a_sc) == (3, 0) and b_sf + b_sc == 5:
            total += 1.0
    return total

def _na_janela_anterior(inicio: Optional[datetime], kickoff: datetime) -> bool:
    if inicio is None:
        return False
    ini = _kickoff_local(inicio)
    ko = _kickoff_local(kickoff)
    return ko - timedelta(minutes=SLOT_ANTERIOR_MIN) <= ini < ko

def _eh_este_confronto(o: OddsMatch, nome: str, adversario: str, kickoff: datetime) -> bool:
    if not adversario or o.kickoff is None:
        return False
    mesmo_par = (
        (mesmo_jogador(o.home, nome) and mesmo_jogador(o.away, adversario))
        or (mesmo_jogador(o.home, adversario) and mesmo_jogador(o.away, nome))
    )
    if not mesmo_par:
        return False
    # Até 10 min de diferença no mesmo par é o próprio jogo (fontes divergem o apito).
    return abs((_kickoff_local(o.kickoff) - _kickoff_local(kickoff)).total_seconds()) <= 10 * 60

def _sets_partida(p: dict) -> Optional[int]:
    try:
        return int(p["sets_favor"]) + int(p["sets_contra"])
    except (KeyError, TypeError, ValueError):
        return None

def _bloqueia_sets_anteriores(nsets: Optional[int]) -> bool:
    """rigido: qualquer jogo anterior. sets: só 4 ou 5 sets (sem placar, não bloqueia)."""
    if modo_horario_anterior() != "sets":
        return True
    return nsets in (4, 5)

def jogou_no_horario_anterior(nome: str, kickoff: Optional[datetime],
                              partidas: List[dict],
                              agenda: Optional[List[OddsMatch]] = None,
                              adversario: str = "") -> bool:
    """True se o jogador começou outro jogo nos 45 min anteriores a este apito.

    Vale o início gravado no resultado e também a grade (odds/fixtures), para
    o caso em que o jogo anterior ainda não tem placar. Com HORARIO_ANTERIOR=sets,
    só bloqueia se esse jogo teve 4 ou 5 sets.
    """
    if kickoff is None or not nome:
        return False
    for p in partidas or []:
        if _na_janela_anterior(p.get("inicio"), kickoff) and _bloqueia_sets_anteriores(_sets_partida(p)):
            return True
    for o in agenda or []:
        if o is None or o.kickoff is None:
            continue
        if not (mesmo_jogador(o.home, nome) or mesmo_jogador(o.away, nome)):
            continue
        if _eh_este_confronto(o, nome, adversario, kickoff):
            continue
        if _na_janela_anterior(o.kickoff, kickoff) and _bloqueia_sets_anteriores(None):
            return True
    return False

def _motivos_verde(alvo: FormaJogador, adv: FormaJogador, odd: float,
                   gap: float, bonus: float) -> List[str]:
    return [
        f"✓ Alvo: <b>{_html(alvo.nome)}</b> (odd {odd:.2f}) — score_forma {_fmt_score(alvo.score_forma)}",
        f"✓ Adversário: <b>{_html(adv.nome)}</b> — score_forma {_fmt_score(adv.score_forma)}",
        f"✓ Gap: {_fmt_score(gap)} (bônus triangulação +{_fmt_score(bonus)})",
    ]

def decidir_entrada(a: FormaJogador, b: FormaJogador,
                    odd_a: Optional[float], odd_b: Optional[float],
                    agora: datetime,
                    anterior_a: bool = False,
                    anterior_b: bool = False) -> Decisao:
    """Pseudocódigo do filtro. Empate de score_forma escolhe o jogador B."""
    if a.jogos_hoje < 1 or b.jogos_hoje < 1:
        return Decisao("indefinido", ["PASSAR (Sem dados do dia)"])
    if a.score_forma > b.score_forma:
        alvo, adv, odd, anterior = a, b, odd_a, anterior_a
    else:
        alvo, adv, odd, anterior = b, a, odd_b, anterior_b
    if odd is None or not (odd > 1):
        return Decisao("bloqueado", ["PASSAR (Sem odds de mercado)"])
    if odd < ODD_MIN_ALVO or odd > ODD_MAX_ALVO:
        return Decisao("bloqueado", [f"PASSAR (Odd fora da faixa: {odd:.2f})"])
    if alvo.perdeu_ultimo_jogo or alvo.vitorias_limpas_seguidas < 2:
        return Decisao("bloqueado", ["PASSAR (Sem domínio comprovado)"])
    if alvo.desgaste_ultimo_jogo:
        return Decisao("bloqueado", ["PASSAR (Alvo vem de 5 sets)"])
    if anterior:
        return Decisao("bloqueado", ["PASSAR (jogou no horário anterior)"])
    if a.score_forma >= SCORE_AMBOS_VITORIAS and b.score_forma >= SCORE_AMBOS_VITORIAS:
        return Decisao("bloqueado", ["PASSAR (Ambos vêm de vitórias)"])
    bonus = bonus_triangulacao(alvo, adv, agora)
    gap = (alvo.score_forma - adv.score_forma) + bonus
    if gap >= GAP_MIN and adv.score_forma <= 0:
        return Decisao(
            "verde", _motivos_verde(alvo, adv, odd, gap, bonus),
            alvo.nome, gap, odd, alvo.score_forma, adv.score_forma, bonus,
        )
    return Decisao("bloqueado", ["PASSAR (Desnível insuficiente)"])

def _odds_do_par(player1: str, player2: str, odds_map: Dict[str, OddsMatch]):
    om = achar_odds(player1, player2, [o for o in odds_map.values() if not o.in_play])
    if om and mesmo_jogador(om.home, player1):
        return om.odd_home, om.odd_away
    if om and mesmo_jogador(om.away, player1):
        return om.odd_away, om.odd_home
    return None, None

def analisar_confronto(player1: str, player2: str, hist: Historico,
                       odds_map: Dict[str, OddsMatch],
                       kickoff: Optional[datetime] = None,
                       forma: Optional[FormaDia] = None,
                       agenda: Optional[List[OddsMatch]] = None,
                       agora: Optional[datetime] = None) -> Decisao:
    agora = agora or agora_cet()
    if agenda is None:
        agenda = list(odds_map.values()) if odds_map else []
    p1 = partidas_do_jogador(player1, hist, forma)
    p2 = partidas_do_jogador(player2, hist, forma)
    a = metricas_forma(player1, p1, agora)
    b = metricas_forma(player2, p2, agora)
    odd1, odd2 = _odds_do_par(player1, player2, odds_map or {})
    ant1 = jogou_no_horario_anterior(player1, kickoff, p1, agenda, player2)
    ant2 = jogou_no_horario_anterior(player2, kickoff, p2, agenda, player1)
    return decidir_entrada(a, b, odd1, odd2, agora, ant1, ant2)

def avaliar(m, hist: Historico, odds_map: Dict[str, OddsMatch],
            forma: Optional[FormaDia] = None,
            agenda: Optional[List[OddsMatch]] = None,
            agora: Optional[datetime] = None) -> Tuple[str, List[str], Optional[str]]:
    """Aplica as regras a qualquer objeto com .player1 e .player2 (LiveMatch ou OddsMatch)."""
    return avaliar_par(m.player1, m.player2, hist, odds_map,
                       kickoff=getattr(m, "kickoff", None), forma=forma,
                       agenda=agenda, agora=agora)

def avaliar_par(player1: str, player2: str, hist: Historico,
                odds_map: Dict[str, OddsMatch],
                kickoff: Optional[datetime] = None,
                forma: Optional[FormaDia] = None,
                agenda: Optional[List[OddsMatch]] = None,
                agora: Optional[datetime] = None) -> Tuple[str, List[str], Optional[str]]:
    """Filtro por score_forma. O alvo é quem tem a melhor forma, não a odd menor."""
    d = analisar_confronto(player1, player2, hist, odds_map, kickoff, forma, agenda, agora)
    return d.status, d.motivos, d.alvo

def montar_odds_map(odds_list: List[OddsMatch]) -> Dict[str, OddsMatch]:
    return {f"{o.home}|{o.away}".lower(): o for o in odds_list}

# ══════════════════════════════════════════════════════════════════════════════
# ENTRADA hh:55 (pré-jogo, 2ª rodada)
# ══════════════════════════════════════════════════════════════════════════════

# sendMessage do Telegram recusa texto acima de 4096 unidades UTF-16.
TG_LIMITE = 4096

def _tamanho_tg(texto: str) -> int:
    return len(texto.encode("utf-16-le")) // 2

def _unir_partes(cab: str, secoes: List[str], rodape: str) -> str:
    pedacos = [cab.rstrip("\n")]
    pedacos.extend(s for s in secoes if s)
    if rodape:
        pedacos.append(rodape)
    return "\n\n".join(pedacos)

def _montar_miolo(blocos: List[str], total: int, aviso: str, linhas: List[str], omitidos: int,
                  cab: str, rodape: str) -> str:
    secoes = []
    if blocos:
        secoes.append(f"<b>SINAL VERDE</b> — {total} entrada(s):\n\n" + "\n\n".join(blocos))
    if aviso:
        secoes.append(aviso)
    if linhas or omitidos:
        total_sem = len(linhas) + omitidos
        corpo = list(linhas)
        if omitidos:
            corpo.append(f"… e mais {omitidos} jogos")
        rotulo = "1 jogo" if total_sem == 1 else f"{total_sem} jogos"
        secoes.append(f"<b>Sem entrada</b> — {rotulo}:\n" + "\n".join(corpo))
    return _unir_partes(cab, secoes, rodape)

def _max_linhas(blocos: List[str], total: int, aviso: str, linhas: List[str],
                cab: str, rodape: str, limite: int) -> int:
    """Quantas linhas de fora cabem. -1 se nem o aviso de corte cabe."""
    def montado(qtd: int) -> str:
        return _montar_miolo(blocos, total, aviso, linhas[:qtd], len(linhas) - qtd, cab, rodape)

    if _tamanho_tg(montado(len(linhas))) <= limite:
        return len(linhas)
    if not linhas or _tamanho_tg(montado(0)) > limite:
        return -1
    lo, hi, melhor = 0, len(linhas) - 1, 0
    while lo <= hi:
        mid = (lo + hi) // 2
        if _tamanho_tg(montado(mid)) <= limite:
            melhor = mid
            lo = mid + 1
        else:
            hi = mid - 1
    return melhor

def _cortar_para(texto: str, limite: int) -> str:
    if limite <= 0:
        return ""
    if _tamanho_tg(texto) <= limite:
        return texto
    nota = "…"
    orcamento = limite - _tamanho_tg(nota)
    if orcamento <= 0:
        return nota if _tamanho_tg(nota) <= limite else ""
    chars: List[str] = []
    usado = 0
    ultimo_seguro = 0
    for ch in texto:
        t = _tamanho_tg(ch)
        if usado + t > orcamento:
            break
        chars.append(ch)
        usado += t
        if ch in " \n;>":
            ultimo_seguro = len(chars)
    if ultimo_seguro:
        chars = chars[:ultimo_seguro]
    base = "".join(chars).rstrip()
    amp = base.rfind("&")
    if amp != -1 and ";" not in base[amp:]:
        base = base[:amp].rstrip()
    if base.count("<b>") > base.count("</b>"):
        base = base[:base.rfind("<b>")].rstrip()
    if base.count("<") > base.count(">"):
        base = base[:base.rfind("<")].rstrip()
    return base + nota

def _partir_telegram(texto: str, limite: int = TG_LIMITE) -> List[str]:
    """Divide em envios de no máximo `limite` unidades UTF-16, sem cortar no meio de uma tag."""
    if not texto:
        return []
    if _tamanho_tg(texto) <= limite:
        return [texto]
    partes: List[str] = []
    atual = ""
    for linha in texto.split("\n"):
        candidato = linha if not atual else atual + "\n" + linha
        if _tamanho_tg(candidato) <= limite:
            atual = candidato
            continue
        if atual:
            partes.append(atual)
            atual = ""
        if _tamanho_tg(linha) <= limite:
            atual = linha
        else:
            partes.append(_cortar_para(linha, limite))
    if atual:
        partes.append(atual)
    return partes

def _garantir_limite(texto: str, limite: int = TG_LIMITE) -> List[str]:
    if _tamanho_tg(texto) <= limite:
        return [texto] if texto else []
    return _partir_telegram(texto, limite)

def _empacotar_entrada(cab: str, blocos: List[str], aviso: str, linhas: List[str],
                       rodape: str, limite: int = TG_LIMITE) -> List[str]:
    """Uma mensagem se couber. Senão corta a lista de fora; se os verdes não cabem, divide."""
    total = len(blocos)
    grupos: List[List[str]] = []
    atual: List[str] = []
    for bloco in blocos:
        tentativa = atual + [bloco]
        texto = _montar_miolo(tentativa, total, "", [], 0, cab, rodape)
        if atual and _tamanho_tg(texto) > limite:
            grupos.append(atual)
            atual = [bloco]
        else:
            atual = tentativa
    if atual:
        grupos.append(atual)

    if not grupos:
        qtd = _max_linhas([], 0, aviso, linhas, cab, rodape, limite)
        if qtd < 0:
            return _partir_telegram(_montar_miolo([], 0, aviso, linhas, 0, cab, rodape), limite)
        return [_montar_miolo([], 0, aviso, linhas[:max(qtd, 0)], len(linhas) - max(qtd, 0), cab, rodape)]

    mensagens: List[str] = []
    for i, grupo in enumerate(grupos):
        ultimo = i == len(grupos) - 1
        if not ultimo:
            mensagens.extend(_garantir_limite(_montar_miolo(grupo, total, "", [], 0, cab, ""), limite))
            continue
        qtd = _max_linhas(grupo, total, "", linhas, cab, rodape, limite)
        if qtd >= 0:
            texto = _montar_miolo(grupo, total, "", linhas[:qtd], len(linhas) - qtd, cab, rodape)
            mensagens.extend(_garantir_limite(texto, limite))
        else:
            texto = _montar_miolo(grupo, total, "", [], 0, cab, "" if linhas else rodape)
            mensagens.extend(_garantir_limite(texto, limite))
            if linhas:
                qtd2 = _max_linhas([], 0, "", linhas, cab, rodape, limite)
                if qtd2 < 0:
                    mensagens.extend(_partir_telegram(
                        _montar_miolo([], 0, "", linhas, 0, cab, rodape), limite))
                else:
                    mensagens.append(
                        _montar_miolo([], 0, "", linhas[:qtd2], len(linhas) - qtd2, cab, rodape))
    return [m for m in mensagens if m.strip()]

def _hora_jogo(o: OddsMatch) -> str:
    return o.kickoff.strftime("%H:%M") if o.kickoff else "—"

def _adversario_do_alvo(alvo: str, home: str, away: str) -> str:
    return away if mesmo_jogador(alvo or "", home) else home

GEMINI_MODELO_PADRAO = "gemini-2.5-flash"
GEMINI_MODELO_FALLBACK = "gemini-2.0-flash"
GEMINI_TIMEOUT_S = 8
GEMINI_MAX_CHARS = 200

def _modelos_gemini() -> Tuple[str, ...]:
    """Principal em GEMINI_MODEL (padrão gemini-2.5-flash) e, se for outro, o fallback."""
    principal = os.environ.get("GEMINI_MODEL", "").strip() or GEMINI_MODELO_PADRAO
    if principal == GEMINI_MODELO_FALLBACK:
        return (principal,)
    return (principal, GEMINI_MODELO_FALLBACK)

def _chave_gemini() -> str:
    return os.environ.get("GEMINI_API_KEY", "").strip()

def _limpar_veredito(texto: str) -> str:
    s = " ".join((texto or "").replace("🤖", " ").split())
    s = re.sub(r"^\d+[\.\)\-]\s*", "", s).strip()
    if len(s) > GEMINI_MAX_CHARS:
        s = s[:GEMINI_MAX_CHARS].rstrip()
    return s

def _chamar_gemini(modelo: str, chave: str, prompt: str, timeout: float) -> str:
    url = f"https://generativelanguage.googleapis.com/v1beta/models/{modelo}:generateContent"
    resp = requests.post(
        url,
        headers={"x-goog-api-key": chave, "Content-Type": "application/json"},
        json={
            "contents": [{"parts": [{"text": prompt}]}],
            "generationConfig": {"temperature": 0.2, "maxOutputTokens": 256},
        },
        timeout=max(0.5, timeout),
    )
    resp.raise_for_status()
    data = resp.json()
    cands = data.get("candidates") or []
    parts = ((cands[0].get("content") or {}).get("parts") if cands else None) or []
    return "".join(p.get("text") or "" for p in parts if isinstance(p, dict))

def consultar_gemini(prompt: str) -> str:
    """Uma chamada por bloco. Sem chave, timeout ou erro: texto vazio, sem exceção.

    A chave não entra no log. O tempo total das tentativas fica em 8 s.
    """
    chave = _chave_gemini()
    if not chave or not (prompt or "").strip():
        return ""
    prazo = time.monotonic() + GEMINI_TIMEOUT_S
    falha = ""
    for modelo in _modelos_gemini():
        resta = prazo - time.monotonic()
        if resta < 0.4:
            break
        try:
            texto = (_chamar_gemini(modelo, chave, prompt, resta) or "").strip()
            if texto:
                log.info("[GEMINI] veredito via %s (%s caracteres)", modelo, len(texto))
                return texto
        except Exception as exc:
            falha = type(exc).__name__
            continue
    if falha:
        log.info("[GEMINI] sem análise (%s)", falha)
    return ""

def _sets_recentes(nome: str, hist: Optional[Historico], forma: Optional[FormaDia],
                   agora: datetime) -> str:
    jogos = metricas_forma(nome, partidas_do_jogador(nome, hist, forma), agora).partidas
    if not jogos:
        return "sem sets"
    partes = []
    for p in jogos[-3:]:
        sf, sc = int(p["sets_favor"]), int(p["sets_contra"])
        partes.append(f"{sf}-{sc} ({sf + sc} sets)")
    return ", ".join(partes)

def _h2h_txt(extras: List[str]) -> str:
    for ex in extras or []:
        limpo = re.sub(r"<[^>]+>", "", ex)
        if "H2H" in limpo:
            return " ".join(limpo.split())
    return "sem H2H"

def ler_licoes() -> str:
    if not LICOES_FILE.exists():
        return ""
    try:
        return LICOES_FILE.read_text(encoding="utf-8").strip()
    except Exception:
        return ""

def historico_alvo_bot(alvo: str) -> str:
    """Conta quantos GREEN/RED este jogador já deu nas entradas do bot."""
    _campos, linhas = _ler_auditoria()
    g = r = 0
    for row in linhas:
        res = (row.get("resultado") or "").strip().upper()
        if res not in ("GREEN", "RED"):
            continue
        if mesmo_jogador(row.get("alvo") or "", alvo):
            if res == "GREEN":
                g += 1
            else:
                r += 1
    if g + r == 0:
        return "estreante no bot"
    return f"{g} GREEN / {r} RED no bot"

def atualizar_licoes_diarias(tg: "Telegram") -> bool:
    """Lê os últimos 40 resultados da auditoria e pede ao Gemini 5 lições práticas."""
    if not _chave_gemini():
        return False
    _campos, linhas = _ler_auditoria()
    fechadas = [
        r for r in linhas
        if (r.get("resultado") or "").strip().upper() in ("GREEN", "RED")
    ][-40:]
    if len(fechadas) < 5:
        return False

    resumo_csv = "\n".join(
        f"{r.get('data')} {r.get('horario')} | {r.get('alvo')} @ {r.get('odd')} | "
        f"gap {r.get('gap')} | {r.get('resultado')}"
        for r in fechadas
    )
    prompt = (
        "Você é o estrategista do bot Filtro Blindado (Czech Liga Pro).\n"
        "Abaixo estão os últimos resultados reais (GREEN/RED) do bot.\n"
        "Identifique padrões de erro e acerto (faixa de odd, horário, gap, jogadores) "
        "e escreva exatamente 5 lições curtas (máx. 100 caracteres cada, uma por linha, começando com '- ') "
        "para guiar as análises de amanhã. Sem introdução.\n\n"
        + resumo_csv
    )
    texto = consultar_gemini(prompt)
    if not texto:
        return False
    LICOES_FILE.write_text(texto.strip(), encoding="utf-8")
    tg.send(
        "🧠 <b>Aprendizado diário atualizado!</b>\n\n"
        f"{_html(texto.strip())}\n\n"
        "<i>Essas lições já entram automaticamente nas análises de hoje.</i>",
        chat_id=CHAT_ID,
    )
    log.info("[APRENDIZADO] Lições diárias atualizadas (%s jogos analisados)", len(fechadas))
    return True

def _prompt_gemini(itens: list, hist: Historico, forma: Optional[FormaDia],
                   agenda: Optional[List[OddsMatch]]) -> str:
    agora = agora_cet()
    linhas = []
    for i, (o, d, extras) in enumerate(itens, 1):
        alvo = d.alvo or ""
        adv = _adversario_do_alvo(alvo, o.home, o.away)
        fa = metricas_forma(alvo, partidas_do_jogador(alvo, hist, forma), agora)
        fb = metricas_forma(adv, partidas_do_jogador(adv, hist, forma), agora)
        ant = jogou_no_horario_anterior(
            alvo, o.kickoff, partidas_do_jogador(alvo, hist, forma), agenda or [], adv)
        odd = f"{d.odd:.2f}" if isinstance(d.odd, (int, float)) else "—"
        gap = "—" if d.gap is None else f"{d.gap:.1f}"
        ficha = historico_alvo_bot(alvo)
        linhas.append(
            f"{i}. {_hora_jogo(o)} {nome_exibicao(o.home)} vs {nome_exibicao(o.away)} | "
            f"alvo {nome_exibicao(alvo)} @ {odd} ({ficha}) | "
            f"score_forma alvo {fa.score_forma:.1f} sets [{_sets_recentes(alvo, hist, forma, agora)}] | "
            f"score_forma adversário {fb.score_forma:.1f} sets [{_sets_recentes(adv, hist, forma, agora)}] | "
            f"gap {gap} | triangulação +{d.bonus:.1f} | "
            f"fadiga alvo {'sim' if fa.desgaste_ultimo_jogo else 'não'} | "
            f"horário anterior {'sim' if ant else 'não'} | {_h2h_txt(extras)}"
        )
    licoes = ler_licoes()
    bloco_licoes = f"\nLições aprendidas nos últimos dias:\n{licoes}\n" if licoes else ""
    return (
        "Você é um analista rigoroso de tênis de mesa (Czech Liga Pro). "
        "Avalie cada entrada buscando superioridade real de forma e evitando armadilhas:\n"
        "- Priorize domínio limpo (3-0/3-1) contra adversário em queda clara.\n"
        "- Rebaixe para Baixa se o jogador tiver histórico muito ruim no bot (ex: 0 GREEN / 2+ RED), "
        "freguesia pesada no H2H ou odd suspeita.\n"
        f"{bloco_licoes}"
        "Para cada entrada, responda exatamente uma linha, na mesma ordem, sem numerar:\n"
        "Confiança: Alta — motivo curto e direto\n"
        "A confiança só pode ser Alta, Média ou Baixa. Máximo 180 caracteres por linha. "
        "Sem introdução e sem repetir os números brutos.\n\n"
        "Entradas:\n" + "\n".join(linhas)
    )

def _partir_vereditos(texto: str, n: int) -> List[str]:
    bruto = [_limpar_veredito(l) for l in (texto or "").splitlines()]
    linhas = [l for l in bruto if l]
    if n <= 0 or not linhas:
        return []
    if len(linhas) >= n:
        return linhas[:n]
    if len(linhas) == 1:
        return linhas * n
    saida = linhas + [""] * (n - len(linhas))
    return saida[:n]

def vereditos_gemini(itens: list, hist: Historico, forma: Optional[FormaDia],
                     agenda: Optional[List[OddsMatch]]) -> List[str]:
    """No máximo uma chamada por bloco. Lista vazia se não houver o que dizer."""
    if not itens or not _chave_gemini():
        return []
    try:
        texto = consultar_gemini(_prompt_gemini(itens, hist, forma, agenda))
    except Exception as exc:
        log.info("[GEMINI] sem análise (%s)", type(exc).__name__)
        return []
    return _partir_vereditos(texto, len(itens))

def _texto_entrada(hora: str, home: str, away: str, alvo: str, odd: Optional[float],
                   veredito: str = "") -> str:
    odd_txt = f"{odd:.2f}" if isinstance(odd, (int, float)) else "—"
    titulos = [
        "🔥⚡ 𝗢𝗣𝗔! 𝗦𝗜𝗡𝗔𝗟 𝗙𝗥𝗘𝗦𝗤𝗨𝗜𝗡𝗛𝗢 ⚡🔥",
        "🚀🏓 𝗣𝗔𝗦𝗦𝗢𝗨 𝗡𝗢 𝗙𝗜𝗟𝗧𝗥𝗢! 𝗕𝗢𝗥𝗔 🏓🚀",
        "🎯✨ 𝗔𝗟𝗘𝗥𝗧𝗔 𝗗𝗘 𝗩𝗔𝗟𝗢𝗥 𝗡𝗔 𝗔́𝗥𝗘𝗔 ✨🎯",
    ]
    fechamentos = [
        "Respeita a banca e bora buscar esse GREEN! 🍀💸",
        "Tudo na régua, zero emoção e foco no lucro! 🧠🔥",
        "Filtro cravado! Só confia no processo! 🙌⚡",
    ]
    stake = "1.0 un 🔥" if "confiança: alta" in veredito.lower() else "0.5 un 🛡️"
    bloco_gemini = f"🤖 𝗚𝗲𝗺𝗶𝗻𝗶: <i>{_html(veredito)}</i>\n" if veredito else ""
    return (
        f"{random.choice(titulos)}\n"
        f"━━━━━━━━━━━━━━━━━━\n"
        f"⏰ 𝗛𝗼𝗿𝗮́𝗿𝗶𝗼: <code>{hora}</code>\n"
        f"🏓 𝗝𝗼𝗴𝗼: {_html(nome_exibicao(home))} vs {_html(nome_exibicao(away))}\n"
        f"👑 𝗔𝗹𝘃𝗼: <b>{_html(nome_exibicao(alvo))}</b>\n"
        f"💰 𝗢𝗱𝗱: <code>{odd_txt}</code>  |  🎯 𝗦𝘁𝗮𝗸𝗲: <code>{stake}</code>\n"
        f"{bloco_gemini}"
        f"━━━━━━━━━━━━━━━━━━\n"
        f"💬 <i>{_html(frase_dinamica_gemini(f'Entrada em {nome_exibicao(alvo)} @ {odd_txt}. {veredito}', random.choice(fechamentos)))}</i>"
    )

def _texto_sem_entrada(hora: str) -> str:
    frases = [
        f"😴 <code>{hora}</code> — 𝗦𝗲𝗺 𝗲𝗻𝘁𝗿𝗮𝗱𝗮! Só armadilha nessa rodada, bora proteger a banca 🛡️",
        f"☕ <code>{hora}</code> — 𝗡𝗮𝗱𝗮 𝗱𝗲 𝘃𝗮𝗹𝗼𝗿 agora. Hora do café enquanto esperamos a próxima! ✨",
        f"🛑 <code>{hora}</code> — 𝗣𝗮𝘀𝘀𝗼 𝗹𝗼𝗻𝗴𝗲! O filtro travou tudo, seguimos disciplinados ✌️",
    ]
    return random.choice(frases)

def _linhas_historico(hist, home: str, away: str, universo: List[str]) -> List[str]:
    """Forma 7d e H2H 14d lidos do cache. Sem chave, sem casamento único ou sem jogos: nada."""
    if hist is None or not getattr(hist, "ativo", False):
        return []
    try:
        agora = agora_cet()
        linhas = []
        for nome in (home, away):
            info = hist.forma(nome, universo, agora)
            if not info:
                continue
            v, d, pct = info
            linhas.append(f"<b>{_html(nome)}</b> — Histórico 7d: {v} V / {d} D ({pct}% limpas)")
        par = hist.h2h(home, away, universo, agora)
        if par is not None:
            linhas.append(f"H2H 14d: {par[0]} x {par[1]}")
        return linhas
    except Exception as exc:
        log.warning("SportsAPI365: histórico ignorado (%s)", type(exc).__name__)
        return []

def montar_mensagem_entrada(slot_key: str, confrontos: List[OddsMatch], hist: Historico,
                            odds_list: List[OddsMatch],
                            forma: Optional[FormaDia] = None,
                            historico_anterior: Optional[HistoricoSportsAPI365] = None,
                            agenda: Optional[List[OddsMatch]] = None,
                            ) -> Tuple[List[str], list, List[OddsMatch]]:
    """Retorna (textos, verdes, avaliados_definitivos). Cada texto cabe no Telegram.

    O Telegram leva só a entrada (ou "HH:MM — Sem entrada"). Score, gap, bônus
    e Histórico/H2H vão para o log. Verdes saem ordenados pelo maior gap.
    """
    odds_map = montar_odds_map(odds_list)
    grade = odds_list if agenda is None else agenda
    hora = _alvo_bloco(slot_key).split("|", 1)[1]
    rotulo = _alvo_bloco(slot_key)

    if not confrontos:
        return [], [], []

    universo = [n for o in confrontos for n in (o.home, o.away)]
    avaliados = []
    for o in confrontos:
        d = analisar_confronto(o.home, o.away, hist, odds_map, o.kickoff, forma, grade)
        extras = _linhas_historico(historico_anterior, o.home, o.away, universo)
        avaliados.append((o, d, extras))
        log.info("[ENTRADA %s] %s x %s | %s | %s", rotulo, o.home, o.away, d.status,
                 " ; ".join(d.motivos) or d.status)
        if extras:
            log.info("[ENTRADA %s] contexto | %s", rotulo, " ; ".join(extras))
    verdes_raw = [item for item in avaliados if item[1].status == "verde"]
    verdes_raw.sort(key=lambda item: item[1].gap or 0.0, reverse=True)

    verdes, definitivos = [], []
    for o, d, _extras in avaliados:
        if d.status in ("verde", "bloqueado"):
            definitivos.append(o)
    blocos = []
    vereditos = vereditos_gemini(verdes_raw, hist, forma, agenda if agenda is not None else odds_list)
    for i, (o, d, _extras) in enumerate(verdes_raw):
        veredito = vereditos[i] if i < len(vereditos) else ""
        if "confiança: baixa" in veredito.lower():
            log.info("[GEMINI VETO] %s x %s bloqueado | %s", o.home, o.away, veredito)
            continue
        verdes.append((o, d.alvo, d.gap, veredito))
        blocos.append(_texto_entrada(
            _hora_jogo(o), o.home, o.away, d.alvo or "", d.odd, veredito))
    if not blocos:
        return [_texto_sem_entrada(hora)], [], definitivos
    return _partir_telegram("\n".join(blocos)), verdes, definitivos

def processar_entrada(slot_key: str, hist: Historico, sinais: CacheSet, entradas: CacheSet,
                      tg: Telegram, odds_list: List[OddsMatch], apostas: "Apostas" = None,
                      forma: Optional[FormaDia] = None,
                      historico_anterior: Optional[HistoricoSportsAPI365] = None,
                      agenda: Optional[List[OddsMatch]] = None,
                      livro: Optional["LivroEntradas"] = None,
                      odds_frescas: bool = True) -> bool:
    if entradas.has(slot_key):
        return False
    alvo = _alvo_bloco(slot_key)
    confrontos = confrontos_do_bloco(odds_list, slot_key, incluir_ao_vivo=True)
    if not confrontos:
        porque = "sem odds frescas / 0 jogos na grade" if not odds_frescas else "0 jogos na grade"
        log.info("[ENTRADA %s] 0 jogos avaliados, 0 aprovados (%s)", alvo, porque)
        if not tg.send(_texto_sem_entrada(alvo.split("|", 1)[1])):
            log.error(f"[ENTRADA {slot_key}] falha ao enviar — tenta de novo no próximo ciclo")
            return False
        entradas.add(slot_key)
        return True
    textos, verdes, definitivos = montar_mensagem_entrada(
        slot_key, confrontos, hist, odds_list, forma, historico_anterior, agenda)
    extra = "" if odds_frescas else " (sem odds frescas)"
    log.info("[ENTRADA %s] %s jogos avaliados, %s aprovados%s",
             alvo, len(confrontos), len(verdes), extra)
    if not textos:
        log.error(f"[ENTRADA {slot_key}] falha ao enviar — tenta de novo no próximo ciclo")
        return False
    for texto in textos:
        if not tg.send(texto):
            log.error(f"[ENTRADA {slot_key}] falha ao enviar — tenta de novo no próximo ciclo")
            return False
    entradas.add(slot_key)
    bloco_dt = _kickoff_local(confrontos[0].kickoff)
    dia = bloco_dt.strftime("%Y-%m-%d")
    for o in definitivos:   # verdes e bloqueados: o ao vivo não reavalia
        sinais.add(chave_sinal(o.home, o.away, dia))
    if apostas is not None:
        bloco = f"{bloco_dt.hour:02d}"
        for item in verdes:
            o, fav = item[0], item[1]
            apostas.add(o.home, o.away, fav, bloco, f"{bloco_dt.minute:02d}", o.kickoff)
    if livro is not None:
        for item in verdes:
            o, fav = item[0], item[1]
            gap = item[2] if len(item) > 2 else None
            veredito = item[3] if len(item) > 3 else ""
            livro.registrar(o.home, o.away, fav, o.kickoff, _odd_do_jogador(fav, o), gap, veredito)
    return True

def despachar_alerta(agora: datetime, fonte: List[OddsMatch], entradas: CacheSet,
                     tentativas: Dict[str, float], tg: Telegram, hist: Historico,
                     sinais: CacheSet, apostas: "Apostas" = None,
                     forma: Optional[FormaDia] = None,
                     historico_anterior: Optional[HistoricoSportsAPI365] = None,
                     agenda: Optional[List[OddsMatch]] = None,
                     livro: Optional["LivroEntradas"] = None,
                     odds_frescas: bool = True) -> bool:
    """Uma vez por bloco, na janela :25–:29 ou :55–:59. Vale depois de reiniciar."""
    slot = slot_alerta_atual(agora)
    if not slot or entradas.has(slot):
        return False
    if time.time() - tentativas.get(slot, 0.0) < 30:
        return False
    tentativas[slot] = time.time()
    return processar_entrada(
        slot, hist, sinais, entradas, tg, fonte, apostas, forma,
        historico_anterior, agenda, livro, odds_frescas=odds_frescas)

# ══════════════════════════════════════════════════════════════════════════════
# PROCESSAMENTO AO VIVO (R1 grava / R2 fallback)
# ══════════════════════════════════════════════════════════════════════════════

def processar(matches: List[LiveMatch], hist: Historico, finished: CacheSet,
              sinais: CacheSet, tg: Telegram, modo: str, odds_list: List[OddsMatch],
              apostas: "Apostas" = None, forma: Optional[FormaDia] = None,
              historico_anterior: Optional[HistoricoSportsAPI365] = None,
              agenda: Optional[List[OddsMatch]] = None,
              livro: Optional["LivroEntradas"] = None):
    dia = agora_cet().strftime("%Y-%m-%d")

    for m in matches:
        key_m = f"{dia}|{m.player1}|{m.player2}|{m.score1}:{m.score2}"

        if modo == "R1" and m.finished and not finished.has(key_m):
            if m.score1 is not None and m.score2 is not None:
                janela = _janela_r1_inicio(agora_cet())
                kickoff = _kickoff_conhecido(m, odds_list)
                if janela and kickoff is not None and janela[0] <= kickoff <= janela[1]:
                    r1 = classificar(m.score1, m.score2)
                    r2 = classificar(m.score2, m.score1)
                    o = achar_odds(m.player1, m.player2, odds_list)
                    odd1 = _odd_do_jogador(m.player1, o)
                    odd2 = _odd_do_jogador(m.player2, o)
                    hist.set_resultado(m.player1, r1, m.score1, m.score2, odd1, inicio=kickoff)
                    hist.set_resultado(m.player2, r2, m.score2, m.score1, odd2, inicio=kickoff)
                    finished.add(key_m)
                    log.info(f"[R1] {m.player1} ({r1}) vs {m.player2} ({r2})")

        if modo == "R2":
            key_s = chave_sinal(m.player1, m.player2, dia)
            if sinais.has(key_s):
                continue   # o bloco pré-jogo já avaliou este confronto
            # Só pré-jogo: odd ao vivo significa que o confronto já começou.
            if _tem_odd_ao_vivo(m.player1, m.player2, odds_list):
                continue
            agora = agora_cet()
            pre = achar_odds(m.player1, m.player2, [o for o in odds_list if not o.in_play])
            kickoff = getattr(m, "kickoff", None) or (pre.kickoff if pre else None)
            # O bloco (8–2 min antes) é dono do envio. Aqui só o último instante.
            if kickoff is None or not dentro_do_fallback(kickoff, agora):
                continue
            if getattr(m, "kickoff", None) is None:
                m.kickoff = kickoff
            odds_map = montar_odds_map([o for o in odds_list if not o.in_play])
            status, motivos, fav = avaliar(m, hist, odds_map, forma, agenda=agenda or odds_list)
            if status == "verde":
                odd = _odd_do_jogador(fav or "", pre)
                texto = _texto_entrada(kickoff.strftime("%H:%M"), m.player1, m.player2, fav or "", odd)
                partes = _partir_telegram(texto)
                if partes and all(tg.send(p) for p in partes):
                    sinais.add(key_s)
                    if apostas is not None:
                        apostas.add(m.player1, m.player2, fav, f"{agora_cet().hour:02d}", "ao_vivo")
                    if livro is not None:
                        livro.registrar(m.player1, m.player2, fav, kickoff, odd)
                    log.info("SINAL VERDE (ao vivo) → %s vs %s | %s",
                             m.player1, m.player2, " ; ".join(motivos))

def _trazer_resultados(scoremondo: "ScoreMondo", forma: Optional[FormaDia]) -> List[Resultado]:
    """Página de resultados do ScoreMondo, também gravada na forma do dia."""
    res = scoremondo.fetch_results()
    if forma is not None:
        forma.ingerir_resultados(res)
    return res

def registrar_resultados_r1(resultados: List[Resultado], hist: Historico, finished: CacheSet,
                           odds_list: List[OddsMatch], agora: Optional[datetime] = None) -> int:
    """Grava no histórico os jogos da 1ª rodada do bloco atual (início hh:00..hh:50)
    a partir da página de resultados. Em ordem cronológica: o último jogo vale."""
    agora = agora or agora_cet()
    ini = agora.replace(minute=0, second=0, microsecond=0)
    fim = ini.replace(minute=50)
    n = 0
    for r in sorted(resultados, key=lambda r: r.kickoff or agora):
        if not r.kickoff or not (ini <= r.kickoff <= fim):
            continue
        key = f"res|{r.match_id}|{r.kickoff.strftime('%Y-%m-%d %H:%M')}"
        if finished.has(key):
            continue
        o = achar_odds(r.home, r.away, odds_list)
        o1 = o2 = None
        if o:
            o1, o2 = (o.odd_home, o.odd_away) if mesmo_jogador(o.home, r.home) else (o.odd_away, o.odd_home)
        hist.set_resultado(r.home, classificar(r.sets_home, r.sets_away), r.sets_home, r.sets_away, o1, inicio=r.kickoff)
        hist.set_resultado(r.away, classificar(r.sets_away, r.sets_home), r.sets_away, r.sets_home, o2, inicio=r.kickoff)
        finished.add(key)
        n += 1
    if n:
        log.info(f"[R1] {n} resultado(s) gravados da página de resultados")
    return n

# ══════════════════════════════════════════════════════════════════════════════
# REGISTRO DE ENTRADAS (green / red)
# ══════════════════════════════════════════════════════════════════════════════

ANULAR_APOS_H = 3          # sem resultado depois de 3 h → anulada (não conta)
INTERVALO_RESULTADOS = 60  # s entre consultas à página de resultados (só com pendentes)

class Apostas:
    """Lista persistida de entradas enviadas: dia, bloco, confronto, pick, status."""
    def __init__(self, path: Path):
        self.path = path
        self.itens: List[dict] = []
        if path.exists():
            try:
                self.itens = json.loads(path.read_text(encoding="utf-8"))
            except Exception:
                self.itens = []

    def save(self):
        tmp = self.path.with_suffix(".tmp")
        tmp.write_text(json.dumps(self.itens, ensure_ascii=False, indent=1), encoding="utf-8")
        tmp.replace(self.path)

    def get(self, id_: str) -> Optional[dict]:
        return next((a for a in self.itens if a["id"] == id_), None)

    def add(self, home: str, away: str, pick: str, bloco: str, origem: str,
            kickoff: Optional[datetime] = None, agora: Optional[datetime] = None) -> bool:
        agora = agora or agora_cet()
        ref = kickoff.astimezone(TZ) if kickoff is not None and kickoff.tzinfo else (
            TZ.localize(kickoff) if kickoff is not None else agora)
        dia = ref.strftime("%Y-%m-%d")
        id_ = chave_sinal(home, away, dia)
        if self.get(id_):
            return False
        self.itens.append({
            "id": id_, "dia": dia, "bloco": bloco, "origem": origem,
            "home": home, "away": away, "pick": pick,
            "kickoff": kickoff.isoformat() if kickoff else None,
            "enviado": agora.isoformat(timespec="seconds"),
            "status": "pendente", "placar": None, "resolvido": None, "notificado": False,
        })
        self.save()
        return True

    def pendentes(self) -> List[dict]:
        return [a for a in self.itens if a["status"] == "pendente"]

    def periodo(self, d1: str, d2: str) -> List[dict]:
        return [a for a in self.itens if d1 <= a["dia"] <= d2]

def _ref(a: dict) -> datetime:
    return datetime.fromisoformat(a["kickoff"] or a["enviado"])

def resolver_apostas(apostas: Apostas, resultados: List[Resultado], agora: Optional[datetime] = None) -> int:
    """Marca green/red/anulada nas entradas pendentes. Resultado com kickoff=None = jogo
    terminado visto na página ao vivo (aceito se a entrada é das últimas 2 h)."""
    agora = agora or agora_cet()
    n = 0
    for a in apostas.pendentes():
        ref = _ref(a)
        achado = None
        for r in resultados:
            if not ((mesmo_jogador(r.home, a["home"]) and mesmo_jogador(r.away, a["away"])) or
                    (mesmo_jogador(r.home, a["away"]) and mesmo_jogador(r.away, a["home"]))):
                continue
            if max(r.sets_home, r.sets_away) < 3:
                continue
            if r.kickoff is not None:
                if a["kickoff"]:
                    if abs((r.kickoff - ref).total_seconds()) > 20 * 60:
                        continue
                elif not (ref - timedelta(minutes=70) <= r.kickoff <= ref + timedelta(minutes=10)):
                    continue
            elif not (timedelta(0) <= agora - ref <= timedelta(hours=2)):
                continue
            achado = r
            break
        if achado:
            if mesmo_jogador(achado.home, a["pick"]):
                sp, so = achado.sets_home, achado.sets_away
            else:
                sp, so = achado.sets_away, achado.sets_home
            a["status"] = "green" if sp > so else "red"
            a["placar"] = f"{achado.home} {achado.sets_home}-{achado.sets_away} {achado.away}"
            a["resolvido"] = agora.isoformat(timespec="seconds")
            n += 1
        elif agora - ref > timedelta(hours=ANULAR_APOS_H):
            a["status"] = "anulada"
            a["resolvido"] = agora.isoformat(timespec="seconds")
            n += 1
    if n:
        apostas.save()
    return n

def estatisticas(lista: List[dict]) -> dict:
    g = sum(1 for a in lista if a["status"] == "green")
    r = sum(1 for a in lista if a["status"] == "red")
    return {"g": g, "r": r,
            "v": sum(1 for a in lista if a["status"] == "anulada"),
            "p": sum(1 for a in lista if a["status"] == "pendente"),
            "taxa": (100.0 * g / (g + r)) if (g + r) else None}

def fmt_placar(st: dict) -> str:
    taxa = f" — {st['taxa']:.0f}%" if st["taxa"] is not None else ""
    return f"{st['g']} ✅ / {st['r']} ❌{taxa}"

def notificar_resultados(apostas: Apostas, tg: "Telegram") -> int:
    """Envia ao grupo o GREEN/RED/anulada de cada entrada resolvida ainda não avisada."""
    n = 0
    for a in apostas.itens:
        if a.get("notificado") or a.get("status") not in ("green", "red", "void"):
            continue
        hoje = estatisticas(apostas.periodo(agora_cet().strftime("%Y-%m-%d"), agora_cet().strftime("%Y-%m-%d")))
        conf = f"🏓 {nome_exibicao(a['home'])} vs {nome_exibicao(a['away'])}\n👑 Alvo: <b>{nome_exibicao(a['pick'])}</b> @ <code>{a['odd']:.2f}</code>"
        if a["status"] in ("green", "red"):
            cab = "✅🔥 <b>GREEN CONFIRMADO!</b>" if a["status"] == "green" else "❌🛡️ <b>RED NO JOGO</b>"
            corpo = f"{conf}\n📊 Placar: <b>{a['placar']}</b>"
            texto = f"{cab}\n\n{corpo}\n\n📅 Hoje: <b>{fmt_placar(hoje)}</b>"
            ctx_res = (
                f"Deu GREEN em {a['pick']} ({a['placar']})! Placar hoje: {fmt_placar(hoje)}. Comemore com emojis de lucro e fogo."
                if a["status"] == "green" else
                f"Deu RED em {a['pick']} ({a['placar']}). Placar hoje: {fmt_placar(hoje)}. Incentive disciplina e cabeça fria com emojis."
            )
            texto += "\n\n💬 <i>" + _html(frase_dinamica_gemini(ctx_res, "🧠🛡️ " + frase_motivacional() + " 🏓🔥")) + "</i>"
        else:
            cab = "⚪ <b>Entrada anulada</b>"
            corpo = f"{conf}\nResultado não encontrado — não conta no placar."
            texto = f"{cab}\n\n{corpo}\n\n📅 Hoje: <b>{fmt_placar(hoje)}</b>"
        if tg.send(texto):
            a["notificado"] = True
            apostas.save()
            n += 1
        else:
            break  # tenta de novo no próximo ciclo
    return n

# ══════════════════════════════════════════════════════════════════════════════
# RESUMOS E COMANDOS
# ══════════════════════════════════════════════════════════════════════════════

BLOCOS = ["09", "13", "17", "21"]
AVISO_RESPONSAVEL = "🔞 +18 · Aposte com responsabilidade. Nunca aposte o que não pode perder."

def esc(t) -> str:
    return html.escape(str(t or ""), quote=False)

def inicio_semana(d: datetime) -> str:
    return (d - timedelta(days=d.weekday())).strftime("%Y-%m-%d")

PERIODOS_PLACAR = [
    ("madrugada", "🌙 Madrugada (00h–05h)"),
    ("manha", "☀️ Manhã (06h–11h)"),
    ("tarde", "🌤️ Tarde (12h–17h)"),
    ("noite", "🌃 Noite (18h–23h)"),
]

def _periodo_aposta(a: dict) -> str:
    try:
        h = int(str(a.get("bloco") or "0")[:2])
    except ValueError:
        h = 0
    if 0 <= h < 6:
        return "madrugada"
    if 6 <= h < 12:
        return "manha"
    if 12 <= h < 18:
        return "tarde"
    return "noite"

def texto_placar(apostas: Apostas, titulo: str, d1: str, d2: str, por_bloco: bool = False) -> str:
    lista = apostas.periodo(d1, d2)
    st = estatisticas(lista)
    if not lista:
        return (
            f"📊✨ <b>{titulo}</b>\n"
            f"━━━━━━━━━━━━━━━━━━\n"
            f"😴 Nenhuma entrada no período ainda. Seguimos na disciplina!"
        )
    linhas = [
        f"📊🔥 <b>{titulo}</b>",
        "━━━━━━━━━━━━━━━━━━",
        f"🏆 𝗥𝗲𝘀𝘂𝗹𝘁𝗮𝗱𝗼: <b>{fmt_placar(st)}</b>",
    ]
    if st["v"]:
        linhas.append(f"⚪ 𝗔𝗻𝘂𝗹𝗮𝗱𝗮𝘀: <code>{st['v']}</code>")
    if st["p"]:
        linhas.append(f"⏳ 𝗣𝗲𝗻𝗱𝗲𝗻𝘁𝗲𝘀: <code>{st['p']}</code>")
    if por_bloco:
        linhas.append("")
        linhas.append("⏰ 𝗣𝗼𝗿 𝗽𝗲𝗿𝗶́𝗼𝗱𝗼:")
        for chave, rotulo in PERIODOS_PLACAR:
            sb = estatisticas([a for a in lista if _periodo_aposta(a) == chave])
            if sb["g"] or sb["r"] or sb["p"] or sb["v"]:
                linhas.append(f"• {rotulo}: {fmt_placar(sb)}" + (f" · {sb['p']} pend." if sb["p"] else ""))
    return "\n".join(linhas)
  
def texto_resumo_dia(apostas: Apostas, agora: Optional[datetime] = None) -> str:
    agora = agora or agora_cet()
    dia = agora.strftime("%Y-%m-%d")
    mes_ini = agora.strftime("%Y-%m-01")
    corpo = texto_placar(apostas, f"𝗥𝗘𝗦𝗨𝗠𝗢 𝗗𝗢 𝗗𝗜𝗔 {agora.strftime('%d/%m')}", dia, dia, por_bloco=True)
    mes = estatisticas(apostas.periodo(mes_ini, dia))
    return (
        f"{corpo}\n\n"
        f"📅 𝗡𝗼 𝗺𝗲̂𝘀: <b>{fmt_placar(mes)}</b>\n"
        f"━━━━━━━━━━━━━━━━━━\n"
        f"💬 <i>“{frase_motivacional()}”</i>\n\n"
        f"{AVISO_RESPONSAVEL}"
    )

def texto_entradas_hoje(apostas: Apostas) -> str:
    dia = agora_cet().strftime("%Y-%m-%d")
    lista = apostas.periodo(dia, dia)
    if not lista:
        return f"📋😴 𝗡𝗲𝗻𝗵𝘂𝗺𝗮 𝗲𝗻𝘁𝗿𝗮𝗱𝗮 𝗵𝗼𝗷𝗲 𝗮𝗶𝗻𝗱𝗮.\n🎯 Próxima análise: <code>{proxima_entrada()}</code> CET"
    em = {"pendente": "⏳", "green": "✅", "red": "❌", "anulada": "⚪"}
    linhas = ["📋⚡ 𝗘𝗡𝗧𝗥𝗔𝗗𝗔𝗦 𝗗𝗘 𝗛𝗢𝗝𝗘", "━━━━━━━━━━━━━━━━━━"]
    for a in lista:
        hk = datetime.fromisoformat(a["kickoff"]).strftime("%H:%M") if a["kickoff"] else f"{a['bloco']}h ao vivo"
        extra = f" — <code>{esc(a['placar'])}</code>" if a.get("placar") else ""
        linhas.append(
            f"{em.get(a['status'], '•')} <code>{hk}</code> · 👑 <b>{esc(a['pick'])}</b> "
            f"({esc(a['home'])} vs {esc(a['away'])}){extra}"
        )
    linhas += ["━━━━━━━━━━━━━━━━━━", f"📊 𝗣𝗹𝗮𝗰𝗮𝗿: <b>{fmt_placar(estatisticas(lista))}</b>"]
    return "\n".join(linhas)

HORARIOS_TXT = (
    "Somente <b>Czech Liga Pro</b>, 24 h (madrugada inclusive)\n"
    "🎯 ENTRADA: <b>≈5 min antes de cada bloco</b> de início\n"
    "Forma: últimos 2–3 jogos em 4 h · odd do alvo 1.25–1.85"
)

AJUDA_TXT = (
    "🤖 <b>Filtro Blindado</b> — Czech Liga Pro\n\n"
    "Horários (CET):\n" + HORARIOS_TXT + "\n"
    "📊 Resumo do dia: 22:30\n\n"
    "<b>Comandos:</b>\n"
    "/placar — placar de hoje\n"
    "/semana — placar da semana\n"
    "/mes — placar do mês\n"
    "/entradas — entradas de hoje e status\n"
    "/id — ID deste chat\n"
    "/ajuda — esta mensagem\n\n" + AVISO_RESPONSAVEL
)

ADMIN_CMDS = {"/status", "/lista", "/zerar", "/limpo", "/desgaste", "/derrota"}

def processar_comando(text: str, hist: Historico, tg: "Telegram", apostas: Apostas,
                      chat_id: str, user_id: str, msg_id: Optional[int] = None) -> bool:
    """Retorna True se era um comando."""
    text = text.strip()
    partes = text.split(maxsplit=1)
    cmd = partes[0].lower().split("@", 1)[0]
    arg = partes[1].strip() if len(partes) > 1 else ""
    if not cmd.startswith("/"):
        return False
    resp = lambda t: tg.send(t, chat_id=chat_id, reply_to=msg_id)
    agora = agora_cet()
    hoje = agora.strftime("%Y-%m-%d")

    if cmd == "/id":
        resp(f"🆔 ID deste chat: <code>{esc(chat_id)}</code>"
             + (f"\nSeu ID: <code>{esc(user_id)}</code>" if user_id else ""))
        return True
    if cmd in ("/start", "/help", "/ajuda"):
        resp(AJUDA_TXT)
        return True
    if cmd == "/placar":
        resp(texto_placar(apostas, f"Placar de hoje ({agora.strftime('%d/%m')})", hoje, hoje, por_bloco=True))
        return True
    if cmd == "/semana":
        resp(texto_placar(apostas, "Placar da semana", inicio_semana(agora), hoje, por_bloco=True))
        return True
    if cmd in ("/mes", "/mês"):
        resp(texto_placar(apostas, f"Placar do mês ({agora.strftime('%m/%Y')})", agora.strftime("%Y-%m-01"), hoje, por_bloco=True))
        return True
    if cmd == "/entradas":
        resp(texto_entradas_hoje(apostas))
        return True

    if cmd in ADMIN_CMDS:
        if str(user_id) != str(OWNER_ID):
            resp("🔒 Esse comando é só para o admin.")
            return True
        if cmd == "/status":
            resp(f"Modo: <b>{modo_atual()}</b>\nHistórico: {len(hist.data)} jogadores\n"
                 f"Pendentes: {len(apostas.pendentes())}\n"
                 f"Hora CET: {agora.strftime('%H:%M:%S')}\nPróxima entrada: {proxima_entrada()}")
        elif cmd == "/lista":
            if not hist.data:
                resp("Histórico vazio.")
            else:
                linhas = []
                for nome, d in sorted(hist.data.items()):
                    emoji = {"limpo": "✅", "desgaste": "⚠️", "derrota": "❌"}.get(d["resultado"], "•")
                    odd = f" ({d['odd']:.2f})" if d.get("odd") else ""
                    linhas.append(f"{emoji} {esc(nome)}{odd}")
                resp("<b>Histórico</b>\n" + "\n".join(linhas[:40]))
        elif cmd == "/zerar":
            hist.data = {}
            hist.save()
            resp("Histórico zerado.")
        else:
            res = cmd[1:]
            if arg:
                hist.set_resultado(arg, res)
                resp(f"Registrado: <b>{esc(arg)}</b> → {res}")
        return True
    return True   # comando desconhecido: ignora em silêncio

# ══════════════════════════════════════════════════════════════════════════════
# CONVERSA: saudações agendadas, respostas e frases
# ══════════════════════════════════════════════════════════════════════════════

FRASES = [
    "Disciplina é fazer o certo mesmo quando ninguém está olhando.",
    "Paciência também é estratégia: nem todo dia tem entrada boa, e tudo bem.",
    "Gestão de banca não é detalhe, é o que mantém você no jogo.",
    "Quem respeita a stake dorme tranquilo.",
    "Um red não define o seu mês. A constância, sim.",
    "Não corra atrás do prejuízo. Amanhã tem jogo de novo.",
    "Menos impulso, mais método.",
    "O filtro existe para te proteger da pressa.",
    "Saber esperar é tão importante quanto saber entrar.",
    "Valor vem do processo, não da última partida.",
    "Banca organizada, cabeça tranquila.",
    "Emoção fora, critério dentro.",
    "Pequenos passos com consistência vão mais longe que saltos sem plano.",
    "Se bateu a meta, descanse. Se bateu o limite, pare.",
    "Disciplina hoje evita arrependimento amanhã.",
    "Ninguém acerta sempre. Os melhores erram pequeno.",
    "Defina o limite antes de começar, não depois de perder.",
    "Seguir o plano é a vitória que depende só de você.",
    "Respire, confira, e só então decida.",
    "Calma não é lentidão, é precisão.",
    "Aposta é entretenimento, não salário.",
    "Mantenha a stake fixa e o ego no banco.",
    "Dia ruim acontece. Dobrar a aposta para recuperar não é solução.",
    "O mercado sempre vai estar lá. A sua banca precisa estar também.",
    "Foco no longo prazo: uma partida é só uma partida.",
    "Registrar tudo é o primeiro passo para melhorar.",
    "Quem tem método não precisa de sorte para manter a calma.",
    "Uma decisão fria vale mais que dez palpites quentes.",
    "Pausa também faz parte da estratégia.",
    "Sem entrada boa, sem entrada. Simples assim.",
    "Proteja a banca como protege o seu tempo.",
    "Consistência vence empolgação.",
    "O segredo é repetir o básico bem feito, todo dia.",
    "Respeitar o filtro é respeitar o seu próprio plano.",
    "Errar faz parte; insistir no erro, não.",
    "Paciência para esperar, disciplina para seguir, humildade para parar.",
    "Não existe aposta garantida. Existe critério.",
    "A melhor entrada às vezes é a que você não faz.",
    "Organize a banca em unidades e nunca arrisque tudo de uma vez.",
    "Cabeça fria nas vitórias, mais ainda nas derrotas.",
    "Hoje é dia de seguir o processo, não de buscar milagre.",
    "Disciplina é a ponte entre o objetivo e o resultado.",
    "Quem controla a emoção controla a banca.",
    "Jogue com o que sobra, nunca com o que falta.",
    "Ganhar pouco e sempre é melhor que perder muito de uma vez.",
]
_ultimas_frases: List[int] = []

def frase_dinamica_gemini(contexto: str, fallback: str) -> str:
    """Pede ao Gemini uma frase curta, expressiva e cheia de emojis."""
    if not _chave_gemini():
        return fallback
    prompt = (
        "Crie 1 frase curta (máximo 95 caracteres), vibrante e motivacional em português "
        "para um grupo de apostas em tênis de mesa (Czech Liga Pro). "
        "Use 3 a 4 emojis temáticos espalhados pela frase (🏓🔥💸🎯🛡️🚀⚡💪). "
        "Não use aspas nem hashtags. "
        f"Contexto: {contexto}"
    )
    txt = consultar_gemini(prompt)
    if not txt:
        return fallback
    linha = txt.strip().splitlines()[0].strip(" \"'“”")
    return linha[:120] if linha else fallback

def frase_motivacional() -> str:
    opcoes = [i for i in range(len(FRASES)) if i not in _ultimas_frases] or list(range(len(FRASES)))
    i = random.choice(opcoes)
    _ultimas_frases.append(i)
    del _ultimas_frases[:-10]
    return FRASES[i]

# Resumo das entradas do dia anterior, cerca de 00:05 Europe/Prague.
RESUMO_HORA = (0, 5)
RESUMO_JANELA_MIN = 15  # 00:05 até 00:20, para um reinício curto ainda alcançar

class LivroEntradas:
    """Entradas aprovadas que saíram no Telegram, em DATA_DIR/entradas_v5.json.

    Cada item guarda dia, horário do bloco, confronto, alvo, adversário e odd.
    `ultimo_resumo` é o dia (YYYY-MM-DD) que já teve o resumo das 00:05.
    """
    def __init__(self, path: Optional[Path] = None):
        self.path = path or ENTRADAS_SALDO_FILE
        self.itens: List[dict] = []
        self.ultimo_resumo = ""
        self.load()

    def load(self):
        if not self.path.exists():
            return
        try:
            raw = json.loads(self.path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            return
        if not isinstance(raw, dict):
            return
        self.itens = [e for e in (raw.get("itens") or []) if isinstance(e, dict)]
        self.ultimo_resumo = str(raw.get("ultimo_resumo") or "")

    def save(self):
        self.path.parent.mkdir(parents=True, exist_ok=True)
        tmp = self.path.with_suffix(".tmp")
        tmp.write_text(json.dumps({
            "ultimo_resumo": self.ultimo_resumo,
            "itens": self.itens,
        }, ensure_ascii=False, indent=1), encoding="utf-8")
        tmp.replace(self.path)

    def get(self, id_: str) -> Optional[dict]:
        return next((e for e in self.itens if e.get("id") == id_), None)

    def registrar(self, home: str, away: str, alvo: str, kickoff: Optional[datetime],
                  odd: Optional[float], gap: Optional[float] = None, gemini: str = "") -> bool:
        """Grava uma entrada já enviada. Repetir o mesmo confronto no dia não duplica."""
        if kickoff is None or odd is None:
            return False
        ref = kickoff.astimezone(TZ) if kickoff.tzinfo else TZ.localize(kickoff)
        dia = ref.strftime("%Y-%m-%d")
        id_ = chave_sinal(home, away, dia)
        if self.get(id_):
            return False
        adversario = _adversario_do_alvo(alvo, home, away)
        item = {
            "id": id_,
            "dia": dia,
            "hora": ref.strftime("%H:%M"),
            "inicio": ref.isoformat(),
            "home": home,
            "away": away,
            "alvo": alvo,
            "adversario": adversario,
            "odd": round(float(odd), 2),
            "gap": None if gap is None else round(float(gap), 1),
            "gemini": _limpar_veredito(gemini),
            "status": "pendente",
            "placar": None,
            "incluido": False,
            "resultado_avisado": False,
        }
        self.itens.append(item)
        self.save()
        _anexar_auditoria(item)
        log.info("[ENTRADA] registrada %s %s %s x %s alvo=%s odd=%.2f",
                 dia, ref.strftime("%H:%M"), home, away, alvo, float(odd))
        return True

    def pendentes(self) -> List[dict]:
        return [e for e in self.itens if e.get("status") == "pendente"]

    def do_dia(self, dia: str) -> List[dict]:
        return [e for e in self.itens if e.get("dia") == dia]


def _inicio_entrada(entrada: dict) -> Optional[datetime]:
    return _dt_de(entrada.get("inicio")) or _dt_de(f"{entrada.get('dia')}T{entrada.get('hora')}:00")


def _par_da_entrada(entrada: dict, home: str, away: str) -> bool:
    return (
        (mesmo_jogador(home, entrada.get("home") or "") and mesmo_jogador(away, entrada.get("away") or ""))
        or (mesmo_jogador(home, entrada.get("away") or "") and mesmo_jogador(away, entrada.get("home") or ""))
    )


def _perto_do_inicio(inicio: Optional[datetime], referencia: Optional[datetime], minutos: int = 45) -> bool:
    if inicio is None or referencia is None:
        return False
    return abs((inicio - referencia).total_seconds()) <= minutos * 60


def _aplicar_placar(entrada: dict, sets_home: int, sets_away: int, home: str, away: str,
                    agora: datetime) -> bool:
    if max(sets_home, sets_away) != 3:
        return False
    alvo = entrada.get("alvo") or ""
    if mesmo_jogador(alvo, home) or _nome_resultado(alvo, home):
        sa, so = sets_home, sets_away
    elif mesmo_jogador(alvo, away) or _nome_resultado(alvo, away):
        sa, so = sets_away, sets_home
    else:
        return False
    entrada["status"] = "green" if sa > so else "red"
    entrada["placar"] = f"{sets_home}-{sets_away}"
    entrada["resolvido"] = agora.astimezone(TZ).isoformat(timespec="seconds")
    return True


def _nome_resultado(nosso: str, outro: str) -> bool:
    if not nosso or not outro:
        return False
    if mesmo_jogador(nosso, outro):
        return True
    try:
        return bool(nomes_compativeis(nosso, outro))
    except Exception:
        return False


def _liquidar_pela_forma(entrada: dict, forma: Optional[FormaDia], agora: datetime) -> bool:
    if forma is None:
        return False
    ref = _inicio_entrada(entrada)
    melhor = None
    melhor_delta = None
    for jogo in forma.jogos or []:
        home, away = jogo.get("home") or "", jogo.get("away") or ""
        if not _par_da_entrada(entrada, home, away):
            continue
        try:
            sh, sa = int(jogo["sets_home"]), int(jogo["sets_away"])
        except (KeyError, TypeError, ValueError):
            continue
        if max(sh, sa) != 3:
            continue
        inicio = _dt_de(jogo.get("inicio") or jogo.get("quando"))
        if not _perto_do_inicio(inicio, ref):
            continue
        delta = abs((inicio - ref).total_seconds()) if inicio and ref else 0
        if melhor_delta is None or delta < melhor_delta:
            melhor, melhor_delta = (home, away, sh, sa), delta
    if melhor is None:
        return False
    home, away, sh, sa = melhor
    return _aplicar_placar(entrada, sh, sa, home, away, agora)


def _liquidar_pelo_historico(entrada: dict, historico, agora: datetime) -> bool:
    jogos = getattr(historico, "jogos", None) if historico is not None else None
    if not jogos:
        return False
    ref = _inicio_entrada(entrada)
    if ref is None:
        return False
    ref_ts = ref.timestamp()
    melhor = None
    melhor_delta = None
    for jogo in jogos:
        try:
            ts = int(jogo["ts"])
            sh, sa = int(jogo["sh"]), int(jogo["sa"])
        except (KeyError, TypeError, ValueError):
            continue
        if max(sh, sa) != 3 or abs(ts - ref_ts) > 45 * 60:
            continue
        home, away = str(jogo.get("home") or ""), str(jogo.get("away") or "")
        if not (_nome_resultado(entrada.get("home") or "", home) and _nome_resultado(entrada.get("away") or "", away)
                or _nome_resultado(entrada.get("home") or "", away) and _nome_resultado(entrada.get("away") or "", home)):
            continue
        delta = abs(ts - ref_ts)
        if melhor_delta is None or delta < melhor_delta:
            melhor, melhor_delta = (home, away, sh, sa), delta
    if melhor is None:
        return False
    home, away, sh, sa = melhor
    return _aplicar_placar(entrada, sh, sa, home, away, agora)


def _jogo_csv(home: str, away: str) -> str:
    return f"{nome_exibicao(home)} vs {nome_exibicao(away)}"

def _ler_auditoria() -> Tuple[List[str], List[dict]]:
    if not AUDITORIA_FILE.exists() or AUDITORIA_FILE.stat().st_size == 0:
        return [], []
    with AUDITORIA_FILE.open(encoding="utf-8", newline="") as fh:
        reader = csv.DictReader(fh)
        campos = list(reader.fieldnames or [])
        return campos, list(reader)

def _escrever_auditoria(campos: List[str], linhas: List[dict]):
    AUDITORIA_FILE.parent.mkdir(parents=True, exist_ok=True)
    tmp = AUDITORIA_FILE.with_suffix(".tmp")
    with tmp.open("w", encoding="utf-8", newline="") as fh:
        writer = csv.DictWriter(fh, fieldnames=campos, extrasaction="ignore")
        writer.writeheader()
        for row in linhas:
            writer.writerow({c: row.get(c, "") for c in campos})
    tmp.replace(AUDITORIA_FILE)

def _anexar_auditoria(entrada: dict):
    """Uma linha por entrada. O resultado entra depois, quando o placar já existe.

    Arquivo antigo, sem a coluna gemini, ganha a coluna vazia nas linhas que já existiam.
    """
    campos, linhas = _ler_auditoria()
    if not campos:
        campos = list(AUDITORIA_CAMPOS)
    elif "gemini" not in campos:
        campos = list(campos) + ["gemini"]
        _escrever_auditoria(campos, linhas)
    gap = entrada.get("gap")
    row = {
        "data": entrada.get("dia") or "",
        "horario": entrada.get("hora") or "",
        "jogo": _jogo_csv(entrada.get("home") or "", entrada.get("away") or ""),
        "alvo": nome_exibicao(entrada.get("alvo") or ""),
        "odd": f"{float(entrada['odd']):.2f}" if entrada.get("odd") is not None else "",
        "gap": "" if gap is None else f"{float(gap):.1f}",
        "resultado": "",
        "gemini": entrada.get("gemini") or "",
    }
    novo = not AUDITORIA_FILE.exists() or AUDITORIA_FILE.stat().st_size == 0
    with AUDITORIA_FILE.open("a", encoding="utf-8", newline="") as fh:
        writer = csv.DictWriter(fh, fieldnames=campos, extrasaction="ignore")
        if novo:
            writer.writeheader()
        writer.writerow({c: row.get(c, "") for c in campos})

def fechar_auditoria(livro: LivroEntradas, agora: Optional[datetime] = None) -> int:
    """Preenche GREEN/RED ~35 min depois do apito, com o placar já liquidado. Sem rede."""
    if not AUDITORIA_FILE.exists():
        return 0
    agora = agora or agora_cet()
    prontos = {}
    for entrada in livro.itens:
        if entrada.get("status") not in ("green", "red"):
            continue
        inicio = _inicio_entrada(entrada)
        if inicio is None or agora < inicio + timedelta(minutes=AUDITORIA_APOS_MIN):
            continue
        chave = (
            entrada.get("dia") or "",
            entrada.get("hora") or "",
            _jogo_csv(entrada.get("home") or "", entrada.get("away") or ""),
        )
        prontos[chave] = "GREEN" if entrada.get("status") == "green" else "RED"
    if not prontos:
        return 0
    campos, linhas = _ler_auditoria()
    if not campos:
        return 0
    if "gemini" not in campos:
        campos = list(campos) + ["gemini"]
    n = 0
    for row in linhas:
        chave = (row.get("data") or "", row.get("horario") or "", row.get("jogo") or "")
        if not (row.get("resultado") or "").strip() and chave in prontos:
            row["resultado"] = prontos[chave]
            n += 1
    if not n:
        return 0
    _escrever_auditoria(campos, linhas)
    log.info("[AUDITORIA] %s resultado(s) preenchido(s)", n)
    return n

def liquidar_livro(livro: LivroEntradas, forma: Optional[FormaDia] = None,
                   historico=None, agora: Optional[datetime] = None) -> int:
    """Fecha pendentes com resultados já guardados. Não consulta a rede."""
    agora = agora or agora_cet()
    n = 0
    for entrada in livro.pendentes():
        if _liquidar_pela_forma(entrada, forma, agora) or _liquidar_pelo_historico(entrada, historico, agora):
            n += 1
            log.info("[RESUMO] %s %s %s -> %s (%s)", entrada.get("dia"), entrada.get("hora"),
                     entrada.get("alvo"), entrada.get("status"), entrada.get("placar"))
    if n:
        livro.save()
    fechar_auditoria(livro, agora)
    return n


def _saldo_un(itens: List[dict]) -> float:
    total = 0.0
    for entrada in itens:
        if entrada.get("status") == "green" and entrada.get("odd") is not None:
            total += float(entrada["odd"]) - 1.0
        elif entrada.get("status") == "red":
            total -= 1.0
    return round(total, 2)


def _fmt_un(valor: float) -> str:
    return f"{valor:+.2f}"


def _linha_anteriores(itens: List[dict]) -> str:
    if not itens:
        return ""
    g = sum(1 for e in itens if e.get("status") == "green")
    r = sum(1 for e in itens if e.get("status") == "red")
    return f"Pendentes anteriores: {g} green, {r} red ({_fmt_un(_saldo_un(itens))} un)"


def texto_resumo_entradas(dia, do_dia: List[dict], anteriores: List[dict]) -> str:
    rotulo = dia.strftime("%d/%m")
    extra = _linha_anteriores(anteriores)
    if not do_dia:
        base = f"🌙 𝗥𝗘𝗦𝗨𝗠𝗢 {rotulo} — Nenhuma entrada registrada 😴"
        return base if not extra else base + "\n" + extra
    g = sum(1 for e in do_dia if e.get("status") == "green")
    r = sum(1 for e in do_dia if e.get("status") == "red")
    p = sum(1 for e in do_dia if e.get("status") == "pendente")
    saldo = _saldo_un(do_dia)
    emoji_saldo = "🚀💸" if saldo > 0 else ("⚖️" if saldo == 0 else "🛡️")
    linhas = [
        f"🌙📊 𝗙𝗘𝗖𝗛𝗔𝗠𝗘𝗡𝗧𝗢 {rotulo}",
        "━━━━━━━━━━━━━━━━━━",
        f"🎯 𝗘𝗻𝘁𝗿𝗮𝗱𝗮𝘀: <code>{len(do_dia)}</code> | ✅ <code>{g}</code> | ❌ <code>{r}</code> | ⏳ <code>{p}</code>",
        f"{emoji_saldo} 𝗦𝗮𝗹𝗱𝗼: <b>{_fmt_un(saldo)} un</b> <i>(stake 1 un)</i>",
    ]
    if extra:
        linhas.append(f"📌 {extra}")
    return "\n".join(linhas)


def _marcar_resumo(livro: LivroEntradas, ontem: str, do_dia: List[dict], anteriores: List[dict]):
    for entrada in do_dia:
        entrada["incluido"] = True
        if entrada.get("status") in ("green", "red"):
            entrada["resultado_avisado"] = True
    for entrada in anteriores:
        entrada["resultado_avisado"] = True
    livro.ultimo_resumo = ontem
    livro.save()


def enviar_resumo_diario(tg: "Telegram", livro: LivroEntradas,
                         forma: Optional[FormaDia] = None, historico=None,
                         agora: Optional[datetime] = None) -> bool:
    """Uma vez por dia, entre 00:05 e 00:20 Europe/Prague, resume o dia anterior.

    Não consulta o MoviOdds. O dia enviado fica em entradas_v5.json.
    """
    agora = agora or agora_cet()
    local = agora.astimezone(TZ_PRAGA) if agora.tzinfo else TZ_PRAGA.localize(agora)
    if local.hour != 0 or not (RESUMO_HORA[1] <= local.minute <= RESUMO_HORA[1] + RESUMO_JANELA_MIN):
        return False
    ontem_data = local.date() - timedelta(days=1)
    ontem = ontem_data.isoformat()
    if livro.ultimo_resumo == ontem:
        return False
    liquidar_livro(livro, forma, historico, agora)
    do_dia = livro.do_dia(ontem)
    anteriores = [
        e for e in livro.itens
        if (e.get("dia") or "") < ontem and e.get("status") in ("green", "red")
        and not e.get("resultado_avisado")
    ]
    texto = texto_resumo_entradas(ontem_data, do_dia, anteriores)
    if not tg.send(texto):
        log.error("[RESUMO %s] falha ao enviar — tenta de novo na janela", ontem)
        return False
    _marcar_resumo(livro, ontem, do_dia, anteriores)
    g = sum(1 for e in do_dia if e.get("status") == "green")
    r = sum(1 for e in do_dia if e.get("status") == "red")
    p = sum(1 for e in do_dia if e.get("status") == "pendente")
    log.info("[RESUMO %s] entradas=%s green=%s red=%s pendentes=%s saldo=%s",
             ontem, len(do_dia), g, r, p, _fmt_un(_saldo_un(do_dia)))
    return True


# (chave, hora, minuto) — fora dos horários de entrada (hh:55) e depois do resumo (22:30)
AGENDA_SAUDACOES = [("bomdia", 7, 50), ("boatarde", 12, 40), ("boanoite", 22, 35)]
JANELA_SAUDACAO_MIN = 4    # termina antes do hh:55, agora que toda hora tem entrada
HORA_RESUMO = (22, 30)

def periodo_do_dia(h: int) -> str:
    return "manha" if 5 <= h < 12 else ("tarde" if 12 <= h < 19 else "noite")

SAUDACAO_POR_PERIODO = {"manha": ("Bom dia", "☀️"), "tarde": ("Boa tarde", "🌤️"), "noite": ("Boa noite", "🌙")}

def texto_saudacao_agendada(chave: str, apostas: Apostas) -> str:
    frase = frase_motivacional()
    dia = agora_cet().strftime("%Y-%m-%d")
    if chave == "bomdia":
        return ("☀️🔥 𝗕𝗢𝗠 𝗗𝗜𝗔, 𝗚𝗔𝗟𝗘𝗥𝗔! 🔥☀️\n\n"
                f"💬 <i>“{frase}”</i>\n\n"
                "🏓 Filtro ligado 24h na <b>Czech Liga Pro</b>.\n"
                "🎯 Alertas ≈5 min antes de cada bloco. Bora pra cima! 💪✨")
    if chave == "boatarde":
        st = estatisticas(apostas.periodo(dia, dia))
        parcial = f"📊 𝗣𝗮𝗿𝗰𝗶𝗮𝗹 𝗱𝗲 𝗵𝗼𝗷𝗲: <b>{fmt_placar(st)}</b>\n" if (st["g"] or st["r"]) else ""
        return ("🌤️⚡ 𝗕𝗢𝗔 𝗧𝗔𝗥𝗗𝗘, 𝗧𝗜𝗠𝗘! ⚡🌤️\n\n"
                f"💬 <i>“{frase}”</i>\n\n" + parcial +
                "🎯 Seguimos de olho no próximo bloco da Liga Pro! 👀🏓")
    return ("🌙✨ 𝗕𝗢𝗔 𝗡𝗢𝗜𝗧𝗘, 𝗣𝗘𝗦𝗦𝗢𝗔𝗟! ✨🌙\n\n"
            f"💬 <i>“{frase}”</i>\n\n"
            "O bot continua vigiando a madrugada. Descansem bem! 😴🙌")

def tarefas_agendadas(tg: "Telegram", apostas: Apostas, eventos: CacheSet, agora: Optional[datetime] = None,
                      livro: Optional[LivroEntradas] = None, forma: Optional[FormaDia] = None,
                      historico=None) -> List[str]:
    """Resumo das 22:30, resumo das entradas às 00:05 e saudações. Cada um no máximo 1x por dia."""
    agora = agora or agora_cet()
    dia = agora.strftime("%Y-%m-%d")
    feitos = []
    if livro is not None and enviar_resumo_diario(tg, livro, forma, historico, agora):
        feitos.append("resumo_diario")
    k_lic = f"licoes|{dia}"
    if agora.hour == 0 and 10 <= agora.minute <= 25 and not eventos.has(k_lic):
        if atualizar_licoes_diarias(tg):
            eventos.add(k_lic)
            feitos.append("licoes")
    ini_res = agora.replace(hour=HORA_RESUMO[0], minute=HORA_RESUMO[1], second=0, microsecond=0)
    k = f"resumo|{dia}"
    if ini_res <= agora <= agora.replace(hour=23, minute=59, second=59) and not eventos.has(k):
        if tg.send(texto_resumo_dia(apostas, agora)):
            eventos.add(k)
            feitos.append("resumo")
    for chave, h, m in AGENDA_SAUDACOES:
        ini = agora.replace(hour=h, minute=m, second=0, microsecond=0)
        k = f"{chave}|{dia}"
        if ini <= agora <= ini + timedelta(minutes=JANELA_SAUDACAO_MIN) and not eventos.has(k):
            if chave == "boanoite" and not eventos.has(f"resumo|{dia}"):
                continue   # boa noite sempre depois do resumo
            if tg.send(texto_saudacao_agendada(chave, apostas)):
                eventos.add(k)
                feitos.append(chave)
    return feitos

def _sem_acento(t: str) -> str:
    import unicodedata
    return unicodedata.normalize("NFKD", t or "").encode("ascii", "ignore").decode().lower()

RE_SAUDACAO = re.compile(r"\b(bom dia|boa tarde|boa noite|oi+|ola|eae|e ai|salve|opa)\b")
RE_OBRIGADO = re.compile(r"\b(obrigad[oa]s?|obg|valeu|vlw|tmj|gratidao)\b")

RESPOSTAS_EXTRA = [
    "Bora seguir o plano hoje! 💪",
    "Que o dia seja de disciplina e cabeça fria. 🧠",
    "Lembra: gestão de banca sempre em primeiro lugar. 📊",
    "Tamo junto! 🤝",
    "Foco e paciência que o resto vem. 🎯",
]

class Conversa:
    """Respostas naturais no grupo, com limite por pessoa."""
    def __init__(self, bot_username: str = "", bot_id: str = ""):
        self.bot_username = (bot_username or "").lower()
        self.bot_id = str(bot_id or "")
        self.ultimas: Dict[str, float] = {}

    def _pode(self, chave: str, intervalo_s: float, agora_ts: float) -> bool:
        if agora_ts - self.ultimas.get(chave, -1e12) < intervalo_s:
            return False
        self.ultimas[chave] = agora_ts
        return True

    def responder(self, msg: dict, apostas: Apostas, agora: Optional[datetime] = None) -> Optional[str]:
        agora = agora or agora_cet()
        ts = agora.timestamp()
        texto = msg.get("text") or ""
        frm = msg.get("from") or {}
        if frm.get("is_bot"):
            return None
        uid = str(frm.get("id", ""))
        nome = esc((frm.get("first_name") or "amigo").split()[0])
        t = _sem_acento(texto)
        periodo = periodo_do_dia(agora.hour)
        sauda, emoji = SAUDACAO_POR_PERIODO[periodo]
        dia = agora.strftime("%Y-%m-%d")

        mencionado = bool(self.bot_username) and f"@{self.bot_username}" in texto.lower()
        rep = (msg.get("reply_to_message") or {}).get("from") or {}
        if self.bot_id and str(rep.get("id", "")) == self.bot_id:
            mencionado = True

        if RE_OBRIGADO.search(t) and (mencionado or len(t) <= 40):
            if self._pode(f"obg|{uid}", 30 * 60, ts):
                return f"Tamo junto, {nome}! 🤝 {random.choice(RESPOSTAS_EXTRA[:3])}"
            return None
        if RE_SAUDACAO.search(t) and (mencionado or len(t) <= 60):
            if self._pode(f"sauda|{uid}|{dia}|{periodo}", 24 * 3600, ts):
                return f"{sauda}, {nome}! {emoji} {random.choice(RESPOSTAS_EXTRA)}"
            return None
        if mencionado:
            if not self._pode(f"mencao|{uid}", 60, ts):
                return None
            if "placar" in t:
                return texto_placar(apostas, "Placar de hoje", dia, dia, por_bloco=True)
            if "entrada" in t:
                return texto_entradas_hoje(apostas)
            return (f"Opa, {nome}! {emoji} Tô por aqui de olho na Czech Liga Pro.\n"
                    f"Próxima entrada: <b>{proxima_entrada()}</b> CET.\n"
                    f"💬 {frase_motivacional()}\n\nDigite /ajuda para ver os comandos.")
        return None

def boas_vindas(membros: List[dict]) -> Optional[str]:
    nomes = [esc((m.get("first_name") or "").split()[0] or "amigo") for m in membros if not m.get("is_bot")]
    if not nomes:
        return None
    return (f"👋 Bem-vindo(a), {', '.join(nomes)}!\n"
            "Aqui saem as entradas da Czech Liga Pro cerca de 5 min antes de cada bloco (CET), "
            "com green/red de cada jogo e resumo às 22:30.\nDigite /ajuda para ver os comandos.\n\n"
            + AVISO_RESPONSAVEL)

def tratar_update(u: dict, tg: "Telegram", hist: Historico, apostas: Apostas, conversa: Conversa) -> Optional[str]:
    """Processa um update do Telegram. Retorna um rótulo do que foi feito (para log/testes)."""
    mcm = u.get("my_chat_member")
    if mcm:
        chat = mcm.get("chat") or {}
        novo = (mcm.get("new_chat_member") or {}).get("status")
        if chat.get("type") in ("group", "supergroup", "channel") and novo in ("member", "administrator"):
            log.info(f"[GRUPO] Bot adicionado em '{chat.get('title')}' — chat_id={chat.get('id')} (status {novo})")
            tg.send(f"✅ Fui adicionado ao {'canal' if chat.get('type') == 'channel' else 'grupo'} <b>{esc(chat.get('title'))}</b> como {novo}.\n"
                    f"ID do grupo: <code>{chat.get('id')}</code>\n"
                    "Coloque esse número na variável TELEGRAM_GROUP_ID.", chat_id=CHAT_ID)
            return "grupo_adicionado"
        if novo in ("left", "kicked"):
            log.warning(f"[GRUPO] Bot removido de '{chat.get('title')}' ({chat.get('id')})")
            return "grupo_removido"
        return None

    msg = u.get("message") or u.get("channel_post") or {}
    if not msg:
        return None
    chat_id = str((msg.get("chat") or {}).get("id", ""))
    user_id = str((msg.get("from") or {}).get("id", ""))
    text = msg.get("text") or ""
    chats_ok = {str(GROUP_ID), str(CHAT_ID)} | ({str(DISCUSSION_ID)} if DISCUSSION_ID else set())
    permitido = chat_id in chats_ok
    # chats onde o bot conversa/dá boas-vindas: grupo de discussão e o destino principal se for grupo
    eh_canal = "channel_post" in u or (msg.get("chat") or {}).get("type") == "channel"
    conversa_ok = permitido and not eh_canal

    if msg.get("is_automatic_forward"):
        return None   # post do canal repassado automaticamente ao grupo de discussão
    if msg.get("new_chat_members") and conversa_ok and chat_id != str(CHAT_ID):
        t = boas_vindas(msg["new_chat_members"])
        if t:
            tg.send(t, chat_id=chat_id)
            return "boas_vindas"
        return None
    if not text:
        return None
    if text.startswith("/"):
        cmd = text.split()[0].lower().split("@", 1)
        if len(cmd) > 1 and conversa.bot_username and cmd[1] != conversa.bot_username:
            return None   # comando para outro bot
        if cmd[0] == "/id" or permitido:
            processar_comando(text, hist, tg, apostas, chat_id, user_id, msg.get("message_id"))
            return "comando"
        return None
    if not conversa_ok or msg.get("sender_chat"):
        return None   # canal não conversa; mensagens enviadas "como canal" também não
    resposta = conversa.responder(msg, apostas)
    if resposta:
        tg.send(resposta, chat_id=chat_id, reply_to=msg.get("message_id"))
        return "conversa"
    return None

# ══════════════════════════════════════════════════════════════════════════════
# MAIN
# ══════════════════════════════════════════════════════════════════════════════

def checar_config():
    faltando = [n for n, v in (("TELEGRAM_TOKEN", TELEGRAM_TOKEN), ("TELEGRAM_CHAT_ID", CHAT_ID)) if not v]
    if faltando:
        print("=" * 60)
        print("Faltam variáveis de ambiente: " + ", ".join(faltando))
        print("Defina-as no painel do servidor (Railway/Render/Fly) ou num arquivo .env")
        print("=" * 60)
        sys.exit(1)
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    if not MOVIODDS_KEY and not MOVIODDS_KEY_2:
        log.warning("MOVIODDS_KEY não definida: rodando sem odds de mercado (não há entrada).")
    if str(GROUP_ID) == str(CHAT_ID):
        log.warning("TELEGRAM_GROUP_ID não definido: entradas vão para o chat privado (TELEGRAM_CHAT_ID).")

def main():
    checar_config()

    tg = Telegram(TELEGRAM_TOKEN, GROUP_ID)
    hist = Historico()
    scoremondo = ScoreMondo()
    moviodds = MoviOdds([MOVIODDS_KEY, MOVIODDS_KEY_2])
    historico_anterior = HistoricoSportsAPI365(SPORTSAPI365_KEY, DATA_DIR)
    finished = CacheSet(FINISHED_FILE)
    sinais = CacheSet(ENVIADOS_FILE)
    entradas = CacheSet(ENTRADAS_FILE, limite=200)
    eventos = CacheSet(EVENTOS_FILE, limite=300)
    apostas = Apostas(APOSTAS_FILE)
    livro = LivroEntradas(ENTRADAS_SALDO_FILE)
    me = tg.get_me()
    conversa = Conversa(me.get("username", ""), me.get("id", ""))

    if not tg.send(
        "🟢 <b>Filtro Blindado v5 iniciado</b>\n"
        "Somente <b>Czech Liga Pro</b>\n" + HORARIOS_TXT +
        f"\n📊 Resumo: 22:30 · Grupo: <code>{esc(GROUP_ID)}</code>", chat_id=CHAT_ID
    ):
        print("Falha Telegram. Verifique TELEGRAM_TOKEN e TELEGRAM_CHAT_ID.")
        sys.exit(1)

    log.info(f"Bot v5 iniciado | @{conversa.bot_username} | grupo={GROUP_ID} | discussão={DISCUSSION_ID or '-'} | DATA_DIR={DATA_DIR}")
    offset = 0
    ultimo_scrape = 0.0
    ultimo_resultados = 0.0
    ultimo_modo = ""
    tentativas_entrada: Dict[str, float] = {}
    ultimo_aviso_conflito = 0.0
    ultimo_fixtures = 0.0
    fixtures_cache: List[OddsMatch] = []
    agenda_vista: List[OddsMatch] = []
    odds_cache = CacheOdds(persistir=True)
    resultados_cache = CacheOdds()
    forma = FormaDia()

    while True:
        try:
            ups = tg.get_updates(offset)
            if getattr(tg, "conflitos_seguidos", 0) >= 3 and time.time() - ultimo_aviso_conflito >= 3600:
                ultimo_aviso_conflito = time.time()
                tg.send("⚠️ <b>Outro programa está usando este bot ao mesmo tempo</b> (provavelmente a "
                        "versão antiga no seu PC). Feche-a: enquanto as duas rodam, comandos e mensagens "
                        "do grupo podem se perder.", chat_id=CHAT_ID)
            for u in ups:
                offset = u["update_id"] + 1
                _m = u.get("message") or u.get("channel_post") or (u.get("my_chat_member") or {})
                _c = _m.get("chat") or {}
                log.info(f"[UPDATE] chat_id={_c.get('id')} tipo={_c.get('type')} título={_c.get('title') or '-'} "
                         f"de={(_m.get('from') or {}).get('id')} texto={(_m.get('text') or '')[:40]!r}"
                         + (" (my_chat_member)" if "my_chat_member" in u else ""))
                try:
                    tratar_update(u, tg, hist, apostas, conversa)
                except Exception as e:
                    log.error(f"Update: {e}")

            modo = modo_atual()
            if modo != ultimo_modo:
                log.info(f"Modo: {ultimo_modo} → {modo}")
                if modo == "R1":
                    hist.limpar_antigo()
                ultimo_modo = modo

            # MoviOdds só nos minutos da grade (odds ou resultados). O resto reusa o cache.
            odds_now = obter_odds(moviodds, odds_cache)
            obter_resultados(moviodds, forma, resultados_cache)
            # SportsAPI365: no máximo uma coleta por dia, depois das 00:30. Nunca por jogo.
            historico_anterior.atualizar(agora_cet())

            agora_loop = time.time()
            if ultimo_fixtures == 0.0 or agora_loop - ultimo_fixtures >= 20:
                ultimo_fixtures = agora_loop
                fixtures_cache = scoremondo.fetch_fixtures()
            # Entrada por bloco, em qualquer modo. Fixtures + odds: um não esconde o outro.
            previa = fonte_entrada(fixtures_cache, odds_now)
            odds_now = talvez_odds_imediatas(moviodds, odds_cache, previa)
            fonte = fonte_entrada(fixtures_cache, odds_now)
            agora_local = agora_cet()
            # Pré-jogo e ao vivo: o horário anterior vale mesmo sem placar gravado.
            agenda_vista = coletar_agenda(list(fixtures_cache) + list(odds_now or []), agora_local, agenda_vista)
            if blocos_devidos(fonte, agora_local):
                registrar_resultados_r1(_trazer_resultados(scoremondo, forma), hist, finished, odds_now)
            frescas = (odds_cache.quando is not None
                       and time.time() - odds_cache.quando <= ODDS_CACHE_TTL_S)
            despachar_alerta(agora_local, fonte, entradas, tentativas_entrada, tg, hist, sinais,
                             apostas, forma, historico_anterior, agenda_vista, livro, frescas)

            agora_ts = time.time()
            vivos_terminados: List[Resultado] = []
            if modo in ("R1", "R2") and agora_ts - ultimo_scrape >= INTERVALO_SCRAPE:
                ultimo_scrape = agora_ts
                matches = scoremondo.fetch()
                odds_list = odds_now
                if modo == "R1":
                    registrar_resultados_r1(_trazer_resultados(scoremondo, forma), hist, finished, odds_list)
                log.info(f"[{modo}] partidas={len(matches)} | odds={len(odds_list)}")
                if matches:
                    processar(matches, hist, finished, sinais, tg, modo, odds_list, apostas, forma,
                              historico_anterior, agenda_vista, livro)
                vivos_terminados = [Resultado(m.player1, m.player2, m.score1, m.score2, None, "live")
                                    for m in matches if m.finished]

            # GREEN / RED das entradas pendentes
            pend = [a for a in apostas.pendentes() if agora_cet() >= _ref(a) + timedelta(minutes=15)]
            if vivos_terminados and apostas.pendentes():
                resolver_apostas(apostas, vivos_terminados)
            if pend and agora_ts - ultimo_resultados >= INTERVALO_RESULTADOS:
                ultimo_resultados = agora_ts
                resolver_apostas(apostas, _trazer_resultados(scoremondo, forma))
            notificar_resultados(apostas, tg)

            liquidar_livro(livro, forma, historico_anterior, agora_cet())
            tarefas_agendadas(tg, apostas, eventos, livro=livro, forma=forma,
                              historico=historico_anterior)

            time.sleep(4)
        except KeyboardInterrupt:
            tg.send("🔴 Bot encerrado.", chat_id=CHAT_ID)
            break
        except Exception as e:
            log.error(f"Loop: {e}")
            time.sleep(15)

if __name__ == "__main__":
    main()
