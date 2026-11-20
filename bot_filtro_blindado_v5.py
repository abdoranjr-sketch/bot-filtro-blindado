#!/usr/bin/env python3
"""
═══════════════════════════════════════════════════════════════════════════════
  BOT TELEGRAM — FILTRO BLINDADO v5 (interativo)
  ScoreMondo (placar, confrontos e resultados — grátis, sem chave)
  + MoviOdds (odds bet365, OPCIONAL) + Telegram
═══════════════════════════════════════════════════════════════════════════════

Horários CET (Europe/Madrid, somente Czech Liga Pro):
  1ª Rodada (grava):   08:00 / 08:30 → 12:00 / 12:30 → 16:00 / 16:30 → 20:00 / 20:30
  ENTRADA (pré-jogo):  08:55 → 12:55 → 16:55 → 20:55
      Às hh:55 o bot pega na página de jogos (fixtures) do ScoreMondo os confrontos
      da 2ª rodada (jogos que começam entre hh+1:00 e hh+1:50), confirma os
      resultados da 1ª rodada na página de resultados do ScoreMondo, aplica o filtro
      (histórico da 1ª rodada + odds, se houver chave do MoviOdds) e envia UMA mensagem
      com todas as entradas verdes da rodada.
  2ª Rodada (fallback ao vivo): 09:00 / 09:30 → 13:00 / 13:30 → 17:00 / 17:30 → 21:00 / 21:30
      Só sinaliza confrontos que não foram avaliados às hh:55 (sem duplicar).

MoviOdds (odds, opcional) — 92 consultas/dia (~2.760/mês), não a cada scrape.
  A 1ª rodada começa em hh:00 (08, 12, 16, 20). A grade começa 12 min antes:
  (hh-1):48, (hh-1):54, depois hh:00/:06/:12/:18/:20/:24/:30/:36/:42/:48,
  hh:55 (entrada) e (hh+1):00/:06/:12/:18/:20/:24/:30/:36/:42/:48.
  Entre esses minutos o cache vale. Se uma consulta volta vazia por erro, o
  mesmo slot é tentado de novo depois de ~60 s (no máximo 2 vezes).

Interativo (v5) — tudo vai para o GRUPO (TELEGRAM_GROUP_ID):
  • GREEN ✅ / RED ❌ de cada entrada assim que o jogo termina + placar do dia
    (entrada sem resultado após 3 h = anulada, não conta)
  • Resumo do dia às 22:30 (por rodada + acumulado do mês) com aviso +18
  • Saudações 07:50 (bom dia), 12:40 (boa tarde), 22:35 (boa noite) com frase motivacional
  • Responde bom dia/boa tarde/boa noite/oi/obrigado e menções ao bot (com limite por pessoa)
  • Comandos de todos: /placar /semana /mes /entradas /ajuda /id
    Comandos de admin (só o dono, TELEGRAM_OWNER_ID ou TELEGRAM_CHAT_ID):
    /status /lista /zerar /limpo /desgaste /derrota
  Para ler mensagens normais do grupo: desative o "Group Privacy" no BotFather
  (/setprivacy → Disable) ou deixe o bot como administrador do grupo.

Configuração (variáveis de ambiente):
  Obrigatórias: TELEGRAM_TOKEN, TELEGRAM_CHAT_ID (chat privado do dono/admin)
  Recomendada:  TELEGRAM_GROUP_ID (grupo; sem ela tudo vai para TELEGRAM_CHAT_ID)
  Opcional:     TELEGRAM_OWNER_ID (id do usuário admin; padrão = TELEGRAM_CHAT_ID)
                TELEGRAM_DISCUSSION_ID (grupo de discussão ligado ao canal: lá o bot
                conversa, dá boas-vindas e responde /placar /semana /mes /entradas /ajuda;
                as entradas, green/red, resumo e saudações continuam no TELEGRAM_GROUP_ID)
  Opcionais:    MOVIODDS_KEY (odds; sem chave o filtro usa só "limpo vs derrota")
                MOVIODDS_KEY_2 (reserva do MoviOdds, opcional: entra por 30 min se a
                principal falhar com 401, 403, 429, 5xx ou erro de rede)
                DATA_DIR     (pasta dos arquivos .json; padrão = pasta do script)
"""

from __future__ import annotations
import os
import re
import sys
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

# ══════════════════════════════════════════════════════════════════════════════
# CONFIGURAÇÃO
# ══════════════════════════════════════════════════════════════════════════════

TELEGRAM_TOKEN = os.getenv("TELEGRAM_TOKEN", "").strip()
CHAT_ID = os.getenv("TELEGRAM_CHAT_ID", "").strip()
MOVIODDS_KEY = os.getenv("MOVIODDS_KEY", "").strip()
MOVIODDS_KEY_2 = os.getenv("MOVIODDS_KEY_2", "").strip()
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
EVENTOS_FILE = DATA_DIR / "eventos_v5.json"      # resumo/saudações já enviados

TZ = pytz.timezone("Europe/Madrid")

logging.basicConfig(level=logging.INFO, format="%(asctime)s | %(levelname)s | %(message)s", datefmt="%H:%M:%S")
log = logging.getLogger("FiltroV5")

# 1ª Rodada (grava resultados): 08:00, 08:30 | 12:00, 12:30 | 16:00, 16:30 | 20:00, 20:30
# Vai até hh:54 para gravar jogos das hh:30 que terminam tarde, sempre antes da ENTRADA (hh:55).
JANELAS_R1 = [
    (8, 0, 8, 54),
    (12, 0, 12, 54),
    (16, 0, 16, 54),
    (20, 0, 20, 54),
]

# ENTRADA pré-jogo: hh:55 (janela até hh:59 para não perder o horário se o bot reiniciar)
HORAS_ENTRADA = (8, 12, 16, 20)
JANELAS_ENTRADA = [(h, 55, h, 59) for h in HORAS_ENTRADA]

# Consultas ao MoviOdds: (deslocamento de hora a partir de cada hora de HORAS_ENTRADA, minuto).
# A 1ª rodada começa em hh:00. A grade começa 12 min antes, (hh-1):48, e segue de 6 em 6 min
# nas duas rodadas. Fora da grade: (hh):20, (hh+1):20 (cai em :18 e :24) e hh:55 (entrada).
# 23 slots × 4 ciclos = 92 consultas/dia.
MOVIODDS_MINUTOS = tuple(sorted(
    [(-1, 48), (-1, 54)]
    + [(0, m) for m in range(0, 49, 6)]
    + [(0, 20), (0, 55)]
    + [(1, m) for m in range(0, 49, 6)]
    + [(1, 20)]
))
MOVIODDS_MAX_TENTATIVAS = 2
MOVIODDS_RETRY_S = 60

# 2ª Rodada (fallback ao vivo): 09:00, 09:30 | 13:00, 13:30 | 17:00, 17:30 | 21:00, 21:30
JANELAS_R2 = [
    (9, 0, 9, 50),
    (13, 0, 13, 50),
    (17, 0, 17, 50),
    (21, 0, 21, 50),
]

def agora_cet() -> datetime:
    return datetime.now(TZ)

def _na_janela(t: dtime, janelas) -> bool:
    return any(dtime(h1, m1) <= t <= dtime(h2, m2, 59) for h1, m1, h2, m2 in janelas)

def esta_em_janela(janelas) -> bool:
    return _na_janela(agora_cet().time(), janelas)

def modo_atual() -> str:
    t = agora_cet().time()
    if _na_janela(t, JANELAS_R1):
        return "R1"
    if _na_janela(t, JANELAS_ENTRADA):
        return "ENTRADA"
    if _na_janela(t, JANELAS_R2):
        return "R2"
    return "FORA"

def slot_entrada_atual() -> Optional[str]:
    """Retorna a chave do slot de ENTRADA se agora está em hh:55–hh:59, ex: '2026-11-20|08:55'."""
    now = agora_cet()
    if now.hour in HORAS_ENTRADA and 55 <= now.minute <= 59:
        return f"{now.strftime('%Y-%m-%d')}|{now.hour:02d}:55"
    return None

def slot_moviodds_atual(now: Optional[datetime] = None) -> Optional[str]:
    """Chave 'YYYY-MM-DD|HH:MM' se este minuto é um slot de MOVIODDS_MINUTOS; senão None.

    O deslocamento pode ser negativo ((hh-1):48) ou cruzar a meia-noite.
    """
    now = now or agora_cet()
    alvo_min = now.hour * 60 + now.minute
    for dias_depois in (-1, 0, 1):
        for h in HORAS_ENTRADA:
            for off, minute in MOVIODDS_MINUTOS:
                extra, minuto = divmod((h + off) * 60 + minute, 24 * 60)
                if extra == dias_depois and minuto == alvo_min:
                    return f"{now.strftime('%Y-%m-%d')}|{now.hour:02d}:{now.minute:02d}"
    return None

class CacheOdds:
    """Última lista de odds e o instante (time.time) da consulta que a gravou."""
    def __init__(self):
        self.lista: List[OddsMatch] = []
        self.quando: Optional[float] = None
        self.tentativas: Dict[str, int] = {}
        self.ultima_tentativa: Dict[str, float] = {}
        self.falhou: Dict[str, bool] = {}

def _fetch_anotando_erro(moviodds: "MoviOdds") -> Tuple[List[OddsMatch], bool]:
    """fetch_czech sem mexer na classe. erro=True só se a lista veio vazia por falha."""
    falhas: List[str] = []

    class _Aviso(logging.Handler):
        def emit(self, record: logging.LogRecord):
            if record.levelno >= logging.WARNING and record.getMessage().startswith("MoviOdds erro"):
                falhas.append(record.getMessage())

    aviso = _Aviso()
    log.addHandler(aviso)
    try:
        lista = moviodds.fetch_czech()
    finally:
        log.removeHandler(aviso)
    return lista, (not lista) and bool(falhas)

def _pode_tentar_slot(cache: CacheOdds, slot: str, ts: float) -> bool:
    feitas = cache.tentativas.get(slot, 0)
    if feitas >= MOVIODDS_MAX_TENTATIVAS:
        return False
    if feitas == 0:
        return True
    if not cache.falhou.get(slot):
        return False
    return ts - cache.ultima_tentativa.get(slot, 0) >= MOVIODDS_RETRY_S

def _slot_para_consultar(cache: CacheOdds, now: datetime, ts: float) -> Optional[str]:
    """Slot a consultar agora, ou None para reutilizar o cache.

    No minuto agendado, no máximo uma consulta (segunda tentativa ~60 s depois
    se a primeira voltou vazia por erro). Essa segunda tentativa ainda vale
    para o mesmo slot quando o relógio já saiu daquele minuto.
    """
    atual = slot_moviodds_atual(now)
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

def obter_odds(moviodds: "MoviOdds", cache: CacheOdds,
               now: Optional[datetime] = None, agora_ts: Optional[float] = None) -> List[OddsMatch]:
    """Odds em cache. Consulta o MoviOdds só no slot agendado (no máximo 2 tentativas)."""
    now = now or agora_cet()
    ts = time.time() if agora_ts is None else agora_ts
    slot = _slot_para_consultar(cache, now, ts)
    if slot is None:
        return cache.lista
    lista, erro = _fetch_anotando_erro(moviodds)
    cache.tentativas[slot] = cache.tentativas.get(slot, 0) + 1
    cache.ultima_tentativa[slot] = ts
    cache.falhou[slot] = erro
    if not erro:
        cache.lista = lista
        cache.quando = ts
    log.info("[ODDS] consulta %s -> %s jogos", slot.split("|", 1)[1], len(lista))
    return cache.lista

def janela_rodada2(slot_key: str) -> Tuple[datetime, datetime]:
    """Para o slot 'YYYY-MM-DD|hh:55' retorna (início, fim) da 2ª rodada: hh+1:00 .. hh+1:50 CET."""
    dia, hm = slot_key.split("|")
    h = int(hm.split(":")[0])
    base = TZ.localize(datetime.strptime(dia, "%Y-%m-%d").replace(hour=h, minute=0))
    return base + timedelta(hours=1), base + timedelta(hours=1, minutes=50)

def proxima_entrada() -> str:
    now = agora_cet()
    for d in range(2):
        dia = (now + timedelta(days=d)).date()
        for h in HORAS_ENTRADA:
            alvo = TZ.localize(datetime(dia.year, dia.month, dia.day, h, 55))
            if alvo + timedelta(minutes=4, seconds=59) >= now:
                return alvo.strftime("%d/%m %H:%M")
    return "—"

def chave_par(p1: str, p2: str) -> str:
    """Chave independente da ordem casa/fora."""
    a, b = sorted([p1.strip().lower(), p2.strip().lower()])
    return f"{a}|{b}"

def chave_sinal(p1: str, p2: str, dia: Optional[str] = None) -> str:
    dia = dia or agora_cet().strftime("%Y-%m-%d")
    return f"{dia}|{chave_par(p1, p2)}"

_SUFIXOS = {"jnr", "junior", "jr", "snr", "senior", "sr", "st", "ml"}

def norm_nome(nome: str) -> frozenset:
    """Tokens do nome sem ordem/acentos/sufixos: 'Hejl Petr junior' == 'Petr Hejl Jnr'."""
    import unicodedata
    n = unicodedata.normalize("NFKD", nome or "").encode("ascii", "ignore").decode().lower()
    toks = [t for t in re.split(r"[^a-z]+", n) if t and t not in _SUFIXOS]
    return frozenset(toks)

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
                log.warning(f"getUpdates erro: {e}")
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
        nome_l = nome.lower().strip()
        for k, v in self.data.items():
            if k.lower() == nome_l:
                return {**v, "_key": k}
        for k, v in self.data.items():
            if mesmo_jogador(k, nome):
                return {**v, "_key": k}
        for k, v in self.data.items():
            if nome_l in k.lower() or k.lower() in nome_l:
                return {**v, "_key": k}
        return None

    def set_resultado(self, nome: str, resultado: str, sets_f: int = None, sets_c: int = None, odd: float = None):
        key = nome
        existing = self.get(nome)
        if existing and existing.get("_key"):
            key = existing["_key"]
        entry = self.data.get(key, {})
        entry.update({
            "resultado": resultado,
            "sets_favor": sets_f,
            "sets_contra": sets_c,
            "atualizado": agora_cet().strftime("%Y-%m-%d %H:%M:%S"),
        })
        if odd is not None:
            entry["odd"] = odd
        self.data[key] = entry
        self.save()
        log.info(f"Histórico: {nome} → {resultado}" + (f" (odd {odd})" if odd else ""))

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
        if not self.keys:
            return []   # MoviOdds é opcional
        use_backup = self._backup_active()
        key = self.keys[1] if use_backup else self.keys[0]
        try:
            found = self._fetch(key)
        except Exception as e:
            if (not use_backup) and len(self.keys) > 1 and self._should_failover(e):
                self._backup_until = time.monotonic() + self.BACKUP_HOLD_SECONDS
                log.warning(
                    "MoviOdds: chave reserva em uso por %s min (falha da principal: %s)",
                    self.BACKUP_HOLD_SECONDS // 60,
                    self._fail_reason(e),
                )
                try:
                    return self._fetch(self.keys[1])
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

    def _fetch(self, key: str) -> List[OddsMatch]:
        r = requests.get(self.URL, params={"sport": "table_tennis"},
                         headers={"x-api-key": key}, timeout=20)
        r.raise_for_status()
        return self.parse(r.json())

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
            if m.get("league") != "Czech Liga Pro":
                continue
            home, away = m.get("home", ""), m.get("away", "")
            odd_h = odd_a = None
            for q in m.get("quotes") or []:
                if q.get("group_name") in ("To Win Match", "Match") and q.get("odds_dec") and q.get("odds_dec") > 1:
                    side = (q.get("side") or "").lower()
                    if side == home.lower() or (side and home.lower() in side):
                        odd_h = float(q["odds_dec"])
                    elif side == away.lower() or (side and away.lower() in side):
                        odd_a = float(q["odds_dec"])
            if odd_h is None or odd_a is None:
                for q in m.get("quotes") or []:
                    if q.get("group_name") == "To Win Match" and q.get("odds_dec") and q.get("odds_dec") > 1:
                        label = (q.get("label") or q.get("side") or "").lower()
                        if home.lower() in label:
                            odd_h = float(q["odds_dec"])
                        elif away.lower() in label:
                            odd_a = float(q["odds_dec"])
            out.append(OddsMatch(home, away, odd_h, odd_a, bool(m.get("in_play")), m.get("score"),
                                 _parse_kickoff(m.get("kickoff_utc"))))
        return out

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

def confrontos_rodada2(odds_list: List[OddsMatch], slot_key: str) -> List[OddsMatch]:
    """Jogos ainda não iniciados que começam na 2ª rodada do slot (hh+1:00 .. hh+1:50 CET).
    Se a API não trouxer horário, usa todos os jogos não iniciados sem horário."""
    ini, fim = janela_rodada2(slot_key)
    out, vistos = [], set()
    for o in odds_list:
        if o.in_play:
            continue
        if o.kickoff is not None and not (ini <= o.kickoff <= fim):
            continue
        k = chave_par(o.home, o.away)
        if k in vistos:
            continue
        vistos.add(k)
        out.append(o)
    out.sort(key=lambda o: (o.kickoff or ini, o.home))
    return out

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

def classificar(sf: int, sc: int) -> str:
    if sf == 3 and sc <= 1:
        return "limpo"
    if sf == 3 and sc == 2:
        return "desgaste"
    if sc == 3:
        return "derrota"
    return "nao"

def avaliar(m, hist: Historico, odds_map: Dict[str, OddsMatch]) -> Tuple[str, List[str], Optional[str]]:
    """Aplica as regras a qualquer objeto com .player1 e .player2 (LiveMatch ou OddsMatch)."""
    return avaliar_par(m.player1, m.player2, hist, odds_map)

def avaliar_par(player1: str, player2: str, hist: Historico,
                odds_map: Dict[str, OddsMatch]) -> Tuple[str, List[str], Optional[str]]:
    p1l, p2l = player1.lower(), player2.lower()
    h1 = hist.get(player1)
    h2 = hist.get(player2)
    if not h1 or not h2:
        return "indefinido", ["Histórico incompleto"], None

    motivos = ["✓ Histórico 1ª rodada presente"]

    v1 = h1["resultado"] in ("limpo", "desgaste")
    v2 = h2["resultado"] in ("limpo", "desgaste")
    if v1 and v2:
        return "bloqueado", ["Duelo de Vencedores (Regra 2)"], None
    if h1["resultado"] == "derrota" and h2["resultado"] == "derrota":
        return "bloqueado", ["Duelo de Perdedores (Regra 3)"], None

    # Odds
    om = odds_map.get(f"{p1l}|{p2l}") or odds_map.get(f"{p2l}|{p1l}")
    if not om:
        om = achar_odds(player1, player2, list(odds_map.values()))
    if not om:
        for key, om_ in odds_map.items():
            if (p1l in key or key in p1l) and (p2l in key or key in p2l):
                om = om_
                break
    if not om:
        for om_ in odds_map.values():
            names = {om_.home.lower(), om_.away.lower()}
            if p1l in names or any(p1l in n or n in p1l for n in names):
                if p2l in names or any(p2l in n or n in p2l for n in names):
                    om = om_
                    break

    odd1 = odd2 = None
    if om:
        if om.home.lower() == p1l or p1l in om.home.lower() or mesmo_jogador(om.home, player1):
            odd1, odd2 = om.odd_home, om.odd_away
        else:
            odd1, odd2 = om.odd_away, om.odd_home

    # Prefer stored odds from R1 if available
    if h1.get("odd"):
        odd1 = h1["odd"]
    if h2.get("odd"):
        odd2 = h2["odd"]

    if odd1 and odd2:
        if abs(odd1 - odd2) < 0.15:
            return "bloqueado", ["Odds ≈ 50/50 (Regra 5)"], None
        if odd1 < odd2:
            fav_nome, und_nome, fav, und = player1, player2, h1, h2
            odd_fav = odd1
        else:
            fav_nome, und_nome, fav, und = player2, player1, h2, h1
            odd_fav = odd2
    else:
        if h1["resultado"] == "limpo" and h2["resultado"] == "derrota":
            fav_nome, und_nome, fav, und = player1, player2, h1, h2
            odd_fav = None
        elif h2["resultado"] == "limpo" and h1["resultado"] == "derrota":
            fav_nome, und_nome, fav, und = player2, player1, h2, h1
            odd_fav = None
        else:
            return "bloqueado", ["Sem odds + não é limpo vs derrota"], None

    if fav["resultado"] == "derrota":
        return "bloqueado", [f"Inversão: favorito ({fav_nome}) perdeu na 1ª (Regra 4)"], None
    if fav["resultado"] == "desgaste":
        return "bloqueado", [f"Favorito ({fav_nome}) veio de 3-2 (Regra 5)"], None
    if fav["resultado"] != "limpo":
        return "bloqueado", [f"Favorito ({fav_nome}) não veio de vitória limpa"], None
    if und["resultado"] != "derrota":
        return "bloqueado", [f"Adversário ({und_nome}) não veio de derrota"], None

    motivos.extend([
        f"✓ Favorito: <b>{fav_nome}</b>" + (f" (odd {odd_fav:.2f})" if odd_fav else ""),
        "✓ Vitória limpa na 1ª rodada",
        f"✓ Adversário veio de derrota ({und_nome})",
        "✓ Sem 50/50 e sem 3-2"
    ])
    return "verde", motivos, fav_nome

def montar_odds_map(odds_list: List[OddsMatch]) -> Dict[str, OddsMatch]:
    return {f"{o.home}|{o.away}".lower(): o for o in odds_list}

# ══════════════════════════════════════════════════════════════════════════════
# ENTRADA hh:55 (pré-jogo, 2ª rodada)
# ══════════════════════════════════════════════════════════════════════════════

def montar_mensagem_entrada(slot_key: str, confrontos: List[OddsMatch], hist: Historico,
                            odds_list: List[OddsMatch]) -> Tuple[str, List[OddsMatch], List[OddsMatch]]:
    """Retorna (texto, verdes, avaliados_definitivos)."""
    odds_map = montar_odds_map(odds_list)
    ini, fim = janela_rodada2(slot_key)
    hora = slot_key.split("|")[1]
    cab = f"🎯 <b>ENTRADA {hora}</b> — 2ª Rodada {ini.strftime('%H:%M')}/{(ini + timedelta(minutes=30)).strftime('%H:%M')} CET\n"

    if not confrontos:
        return (cab + "\nNenhuma entrada: confrontos da 2ª rodada ainda não disponíveis.\n"
                "O filtro ao vivo continua ativo durante a 2ª rodada."), [], []

    verdes, definitivos, blocos = [], [], []
    for o in confrontos:
        status, motivos, fav = avaliar(o, hist, odds_map)
        if status in ("verde", "bloqueado"):
            definitivos.append(o)
        if status != "verde":
            continue
        verdes.append((o, fav))
        odds_txt = ""
        if o.odd_home and o.odd_away:
            odds_txt = f"\nOdds: {o.home} {o.odd_home:.2f} · {o.away} {o.odd_away:.2f}"
        hk = o.kickoff.strftime("%H:%M") if o.kickoff else "—"
        blocos.append(
            f"🚨 <b>{o.home}</b> vs <b>{o.away}</b> ({hk})\n"
            f"👉 Entrada: <b>{fav}</b>{odds_txt}\n" + "\n".join(motivos)
        )

    if not verdes:
        return cab + f"\nNenhuma entrada verde ({len(confrontos)} confrontos avaliados).", [], definitivos
    texto = (cab + f"\n<b>SINAL VERDE</b> — {len(verdes)} entrada(s):\n\n" + "\n\n".join(blocos)
             + f"\n\n⏰ {agora_cet().strftime('%H:%M:%S')} CET")
    return texto, verdes, definitivos

def processar_entrada(slot_key: str, hist: Historico, sinais: CacheSet, entradas: CacheSet,
                      tg: Telegram, odds_list: List[OddsMatch], apostas: "Apostas" = None) -> bool:
    if entradas.has(slot_key):
        return False
    confrontos = confrontos_rodada2(odds_list, slot_key)
    texto, verdes, definitivos = montar_mensagem_entrada(slot_key, confrontos, hist, odds_list)
    if not tg.send(texto):
        log.error(f"[ENTRADA {slot_key}] falha ao enviar — tenta de novo no próximo ciclo")
        return False
    entradas.add(slot_key)
    dia = slot_key.split("|")[0]
    for o in definitivos:   # verdes e bloqueados: o ao vivo não reavalia
        sinais.add(chave_sinal(o.home, o.away, dia))
    if apostas is not None:
        bloco = f"{int(slot_key.split('|')[1][:2]) + 1:02d}"
        for o, fav in verdes:
            apostas.add(o.home, o.away, fav, bloco, "55", o.kickoff)
    log.info(f"[ENTRADA {slot_key}] confrontos={len(confrontos)} verdes={len(verdes)}")
    return True

# ══════════════════════════════════════════════════════════════════════════════
# PROCESSAMENTO AO VIVO (R1 grava / R2 fallback)
# ══════════════════════════════════════════════════════════════════════════════

def processar(matches: List[LiveMatch], hist: Historico, finished: CacheSet,
              sinais: CacheSet, tg: Telegram, modo: str, odds_list: List[OddsMatch],
              apostas: "Apostas" = None):
    odds_map = montar_odds_map(odds_list)
    dia = agora_cet().strftime("%Y-%m-%d")

    for m in matches:
        key_m = f"{dia}|{m.player1}|{m.player2}|{m.score1}:{m.score2}"

        if modo == "R1" and m.finished and not finished.has(key_m):
            if m.score1 is not None and m.score2 is not None:
                r1 = classificar(m.score1, m.score2)
                r2 = classificar(m.score2, m.score1)
                odd1 = odd2 = None
                for o in odds_list:
                    if (m.player1.lower() in o.home.lower() or o.home.lower() in m.player1.lower()) and \
                       (m.player2.lower() in o.away.lower() or o.away.lower() in m.player2.lower()):
                        odd1, odd2 = o.odd_home, o.odd_away
                        break
                    if (m.player1.lower() in o.away.lower() or o.away.lower() in m.player1.lower()) and \
                       (m.player2.lower() in o.home.lower() or o.home.lower() in m.player2.lower()):
                        odd1, odd2 = o.odd_away, o.odd_home
                        break
                hist.set_resultado(m.player1, r1, m.score1, m.score2, odd1)
                hist.set_resultado(m.player2, r2, m.score2, m.score1, odd2)
                finished.add(key_m)
                log.info(f"[R1] {m.player1} ({r1}) vs {m.player2} ({r2})")

        if modo == "R2":
            key_s = chave_sinal(m.player1, m.player2, dia)
            if sinais.has(key_s):
                continue   # já enviado/avaliado às hh:55
            status, motivos, fav = avaliar(m, hist, odds_map)
            if status == "verde":
                texto = (
                    f"🚨 <b>SINAL VERDE</b> (ao vivo)\n\n"
                    f"<b>{m.player1}</b> vs <b>{m.player2}</b>\n"
                    f"👉 Entrada: <b>{fav}</b>\n"
                    f"Placar: {m.score1 if m.score1 is not None else '-'} : {m.score2 if m.score2 is not None else '-'} ({m.current_set or '—'})\n\n"
                    + "\n".join(motivos) +
                    f"\n\n⏰ {agora_cet().strftime('%H:%M:%S')} CET"
                )
                if tg.send(texto):
                    sinais.add(key_s)
                    if apostas is not None:
                        apostas.add(m.player1, m.player2, fav, f"{agora_cet().hour:02d}", "ao_vivo")
                    log.info(f"SINAL VERDE (ao vivo) → {m.player1} vs {m.player2}")

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
        hist.set_resultado(r.home, classificar(r.sets_home, r.sets_away), r.sets_home, r.sets_away, o1)
        hist.set_resultado(r.away, classificar(r.sets_away, r.sets_home), r.sets_away, r.sets_home, o2)
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
        dia = agora.strftime("%Y-%m-%d")
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
        if a["status"] == "pendente" or a.get("notificado"):
            continue
        # placar corrente: só o que já foi anunciado + esta entrada
        hoje = estatisticas([x for x in apostas.periodo(a["dia"], a["dia"])
                             if x is a or (x["status"] != "pendente" and x.get("notificado"))])
        conf = f"{esc(a['home'])} vs {esc(a['away'])}"
        if a["status"] == "green":
            cab = "✅ <b>GREEN!</b>"
            corpo = f"{esc(a['placar'])}\n👉 Entrada: <b>{esc(a['pick'])}</b>"
        elif a["status"] == "red":
            cab = "❌ <b>RED</b>"
            corpo = f"{esc(a['placar'])}\n👉 Entrada: <b>{esc(a['pick'])}</b>"
        else:
            cab = "⚪ <b>Entrada anulada</b>"
            corpo = f"{conf}\nResultado não encontrado — não conta no placar."
        texto = f"{cab}\n\n{corpo}\n\n📊 Hoje: {fmt_placar(hoje)}"
        if a["status"] == "red":
            texto += "\n\n💬 " + frase_motivacional()
        if tg.send(texto):
            a["notificado"] = True
            apostas.save()
            n += 1
        else:
            break   # tenta de novo no próximo ciclo
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

def texto_placar(apostas: Apostas, titulo: str, d1: str, d2: str, por_bloco: bool = False) -> str:
    lista = apostas.periodo(d1, d2)
    st = estatisticas(lista)
    linhas = [f"📊 <b>{titulo}</b>", "", f"Resultado: <b>{fmt_placar(st)}</b>"]
    if st["v"]:
        linhas.append(f"Anuladas: {st['v']}")
    if st["p"]:
        linhas.append(f"Pendentes: {st['p']}")
    if not lista:
        linhas = [f"📊 <b>{titulo}</b>", "", "Nenhuma entrada no período."]
    if por_bloco and lista:
        linhas.append("")
        linhas.append("<b>Por rodada:</b>")
        for b in BLOCOS:
            sb = estatisticas([a for a in lista if a["bloco"] == b])
            if sb["g"] or sb["r"] or sb["p"] or sb["v"]:
                linhas.append(f"• {b}h: {fmt_placar(sb)}" + (f" · {sb['p']} pend." if sb["p"] else ""))
    return "\n".join(linhas)

def texto_resumo_dia(apostas: Apostas, agora: Optional[datetime] = None) -> str:
    agora = agora or agora_cet()
    dia = agora.strftime("%Y-%m-%d")
    mes_ini = agora.strftime("%Y-%m-01")
    corpo = texto_placar(apostas, f"Resumo do dia {agora.strftime('%d/%m')}", dia, dia, por_bloco=True)
    mes = estatisticas(apostas.periodo(mes_ini, dia))
    return (corpo + f"\n\n📅 <b>No mês:</b> {fmt_placar(mes)}"
            + f"\n\n💬 {frase_motivacional()}\n\n{AVISO_RESPONSAVEL}")

def texto_entradas_hoje(apostas: Apostas) -> str:
    dia = agora_cet().strftime("%Y-%m-%d")
    lista = apostas.periodo(dia, dia)
    if not lista:
        return f"📋 Nenhuma entrada hoje ainda.\nPróxima: {proxima_entrada()} CET"
    em = {"pendente": "⏳", "green": "✅", "red": "❌", "anulada": "⚪"}
    linhas = ["📋 <b>Entradas de hoje</b>", ""]
    for a in lista:
        hk = datetime.fromisoformat(a["kickoff"]).strftime("%H:%M") if a["kickoff"] else f"{a['bloco']}h ao vivo"
        extra = f" — {esc(a['placar'])}" if a.get("placar") else ""
        linhas.append(f"{em.get(a['status'], '•')} {hk} · <b>{esc(a['pick'])}</b> "
                      f"({esc(a['home'])} vs {esc(a['away'])}){extra}")
    linhas += ["", f"📊 {fmt_placar(estatisticas(lista))}"]
    return "\n".join(linhas)

HORARIOS_TXT = (
    "1ª Rodada: 08:00/08:30 · 12:00/12:30 · 16:00/16:30 · 20:00/20:30\n"
    "🎯 ENTRADA: <b>08:55 · 12:55 · 16:55 · 20:55</b>\n"
    "2ª Rodada: 09:00/09:30 · 13:00/13:30 · 17:00/17:30 · 21:00/21:30"
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

def frase_motivacional() -> str:
    opcoes = [i for i in range(len(FRASES)) if i not in _ultimas_frases] or list(range(len(FRASES)))
    i = random.choice(opcoes)
    _ultimas_frases.append(i)
    del _ultimas_frases[:-10]
    return FRASES[i]

# (chave, hora, minuto) — fora dos horários de entrada (hh:55) e depois do resumo (22:30)
AGENDA_SAUDACOES = [("bomdia", 7, 50), ("boatarde", 12, 40), ("boanoite", 22, 35)]
JANELA_SAUDACAO_MIN = 10   # termina antes das entradas hh:55
HORA_RESUMO = (22, 30)

def periodo_do_dia(h: int) -> str:
    return "manha" if 5 <= h < 12 else ("tarde" if 12 <= h < 19 else "noite")

SAUDACAO_POR_PERIODO = {"manha": ("Bom dia", "☀️"), "tarde": ("Boa tarde", "🌤️"), "noite": ("Boa noite", "🌙")}

def texto_saudacao_agendada(chave: str, apostas: Apostas) -> str:
    frase = frase_motivacional()
    dia = agora_cet().strftime("%Y-%m-%d")
    if chave == "bomdia":
        return ("☀️ <b>Bom dia, galera!</b>\n\n"
                f"💬 “{frase}”\n\n"
                "🎯 Entradas de hoje: 08:55 · 12:55 · 16:55 · 20:55 (CET)\n"
                "Bora com disciplina! 💪")
    if chave == "boatarde":
        st = estatisticas(apostas.periodo(dia, dia))
        parcial = f"📊 Parcial de hoje: {fmt_placar(st)}\n" if (st["g"] or st["r"]) else ""
        return ("🌤️ <b>Boa tarde, time!</b>\n\n"
                f"💬 “{frase}”\n\n" + parcial +
                "🎯 Próxima entrada: 12:55 (CET)")
    return ("🌙 <b>Boa noite, pessoal!</b>\n\n"
            f"💬 “{frase}”\n\n"
            "Amanhã a primeira entrada sai às 08:55. Descansem! 😴")

def tarefas_agendadas(tg: "Telegram", apostas: Apostas, eventos: CacheSet, agora: Optional[datetime] = None) -> List[str]:
    """Resumo diário (22:30) e saudações. Cada uma no máximo 1x por dia (persistido)."""
    agora = agora or agora_cet()
    dia = agora.strftime("%Y-%m-%d")
    feitos = []
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
            "Aqui saem as entradas da Czech Liga Pro às 08:55 · 12:55 · 16:55 · 20:55 (CET), "
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
        log.warning("MOVIODDS_KEY não definida: rodando sem odds (só regra 'limpo vs derrota').")
    if str(GROUP_ID) == str(CHAT_ID):
        log.warning("TELEGRAM_GROUP_ID não definido: entradas vão para o chat privado (TELEGRAM_CHAT_ID).")

def main():
    checar_config()

    tg = Telegram(TELEGRAM_TOKEN, GROUP_ID)
    hist = Historico()
    scoremondo = ScoreMondo()
    moviodds = MoviOdds([MOVIODDS_KEY, MOVIODDS_KEY_2])
    finished = CacheSet(FINISHED_FILE)
    sinais = CacheSet(ENVIADOS_FILE)
    entradas = CacheSet(ENTRADAS_FILE, limite=200)
    eventos = CacheSet(EVENTOS_FILE, limite=300)
    apostas = Apostas(APOSTAS_FILE)
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
    ultima_tentativa_entrada = 0.0
    ultimo_aviso_conflito = 0.0
    odds_cache = CacheOdds()

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

            # MoviOdds só nos minutos de MOVIODDS_MINUTOS; R1/R2 e a entrada reusam o cache.
            odds_now = obter_odds(moviodds, odds_cache)

            slot = slot_entrada_atual()
            if slot and not entradas.has(slot) and time.time() - ultima_tentativa_entrada >= 30:
                ultima_tentativa_entrada = time.time()
                registrar_resultados_r1(scoremondo.fetch_results(), hist, finished, odds_now)
                fixtures = scoremondo.fetch_fixtures()
                fonte = com_odds(fixtures, odds_now) if fixtures else odds_now
                if not fixtures:
                    log.warning("ScoreMondo fixtures vazio — usando confrontos do MoviOdds (se houver)")
                if fonte or agora_cet().minute >= 58:
                    processar_entrada(slot, hist, sinais, entradas, tg, fonte, apostas)
                else:
                    log.warning(f"[ENTRADA {slot}] sem dados ainda — nova tentativa em 30 s")

            agora_ts = time.time()
            vivos_terminados: List[Resultado] = []
            if modo in ("R1", "R2") and agora_ts - ultimo_scrape >= INTERVALO_SCRAPE:
                ultimo_scrape = agora_ts
                matches = scoremondo.fetch()
                odds_list = odds_now
                if modo == "R1":
                    registrar_resultados_r1(scoremondo.fetch_results(), hist, finished, odds_list)
                log.info(f"[{modo}] partidas={len(matches)} | odds={len(odds_list)}")
                if matches:
                    processar(matches, hist, finished, sinais, tg, modo, odds_list, apostas)
                vivos_terminados = [Resultado(m.player1, m.player2, m.score1, m.score2, None, "live")
                                    for m in matches if m.finished]

            # GREEN / RED das entradas pendentes
            pend = [a for a in apostas.pendentes() if agora_cet() >= _ref(a) + timedelta(minutes=15)]
            if vivos_terminados and apostas.pendentes():
                resolver_apostas(apostas, vivos_terminados)
            if pend and agora_ts - ultimo_resultados >= INTERVALO_RESULTADOS:
                ultimo_resultados = agora_ts
                resolver_apostas(apostas, scoremondo.fetch_results())
            notificar_resultados(apostas, tg)

            tarefas_agendadas(tg, apostas, eventos)

            time.sleep(4)
        except KeyboardInterrupt:
            tg.send("🔴 Bot encerrado.", chat_id=CHAT_ID)
            break
        except Exception as e:
            log.error(f"Loop: {e}")
            time.sleep(15)

if __name__ == "__main__":
    main()
