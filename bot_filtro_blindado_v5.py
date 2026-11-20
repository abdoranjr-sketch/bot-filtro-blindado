#!/usr/bin/env python3
"""
═══════════════════════════════════════════════════════════════════════════════
  BOT TELEGRAM — FILTRO BLINDADO v5 (interativo)
  ScoreMondo (placar, confrontos e resultados — grátis, sem chave)
  + MoviOdds (odds bet365, OPCIONAL) + Telegram
═══════════════════════════════════════════════════════════════════════════════

Horários CET (Europe/Madrid, somente Czech Liga Pro — 24 h, madrugada inclusive):
  ENTRADA (pré-jogo): todo hh:55, para os jogos da hora seguinte (hh+1:00 .. hh+1:50).
      Se a hora tiver jogos e nenhum passar no filtro rígido, a mensagem diz
      "Entrada: NENHUMA — sem desnível claro nesta rodada" e lista o motivo de cada jogo.
      Hora sem jogos da liga não gera mensagem. Acima de 4096 caracteres, a lista de
      fora é cortada ("… e mais N jogos") ou a mensagem é dividida em mais de um envio.
  Fallback ao vivo: em qualquer hora, :00–:50, só confrontos ainda não avaliados no :55.

Filtro rígido por FORMA DO DIA (desde 00:00 CET, o fuso que o bot já usa):
  O favorito sai só das odds pré-jogo do jogo alvo (máx 1.65). Todos os jogos já
  finalizados de cada jogador no dia entram na conta (MoviOdds /results, cache em
  DATA_DIR). Para entrar, as quatro condições valem juntas: o favorito não perdeu
  hoje; tem pelo menos 2 vitórias limpas (3-0 ou 3-1) e nenhuma 3-2; o adversário
  tem derrota feia (0-3 ou 1-3). Seguem os vetos de vencedor x vencedor e
  perdedor x perdedor. Sem odds, ou cache de odds com mais de 20 min, não há entrada.

MoviOdds (odds + resultados) — 160 consultas/dia (4.960 em 31 dias, abaixo de 5.000).
  A grade cobre as 24 horas. Antes de cada hh:55 há odds com cache < 20 min
  (:40 e :52) e resultados para fechar a forma do dia (:10, :30, :48 e, na maior
  parte das horas, :20). 07:48 continua na grade, mas não é a primeira do dia
  (a primeira é 00:10). Se uma consulta volta vazia por erro, o mesmo slot é
  tentado de novo depois de ~60 s (no máximo 2 vezes).

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
  Opcionais:    MOVIODDS_KEY (odds; sem chave não há entrada — falta odds de mercado)
                MOVIODDS_KEY_2 (reserva do MoviOdds, opcional: entra por 30 min se a
                principal falhar com 401, 403, 429, 5xx ou erro de rede)
                SPORTSAPI365_KEY (resultados anteriores, RapidAPI; sem ela o bot segue
                igual, sem linha de histórico e sem o bloqueio extra de H2H)
                DATA_DIR     (pasta dos arquivos .json; padrão = pasta do script)

Resultados anteriores (SportsAPI365, opcional): uma vez por dia, depois das 00:30
Europe/Prague, baixa os finalizados de ontem (no primeiro arranque, até 7 dias) e
guarda 14 dias em DATA_DIR. No máximo 40 chamadas por dia, abaixo do teto de 50.
A mensagem das hh:55 mostra a forma de 7 dias e o H2H de 14, lidos só do cache.
Se o favorito perdeu os 2 últimos confrontos diretos nesses 14 dias, a entrada é
bloqueada. As quatro regras da forma do dia e as 160 consultas do MoviOdds não mudam.
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

from historico_sportsapi365 import HistoricoSportsAPI365

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
EVENTOS_FILE = DATA_DIR / "eventos_v5.json"      # resumo/saudações já enviados
FORMA_FILE = DATA_DIR / "forma_dia_v5.json"      # jogos finalizados do dia (MoviOdds)

TZ = pytz.timezone("Europe/Madrid")

# Favorito claro na 2ª rodada: a odd de mercado do favorito tem de ser no máximo esta.
# 1.80/2.00 não passa (a diferença antiga de 0.15 deixava esse par entrar).
ODD_MAX_FAVORITO = 1.65
# Cache do MoviOdds mais velho que isto é tratado como odds ausentes.
ODDS_CACHE_TTL_S = 20 * 60

logging.basicConfig(level=logging.INFO, format="%(asctime)s | %(levelname)s | %(message)s", datefmt="%H:%M:%S")
log = logging.getLogger("FiltroV5")

# Gravação ao vivo da 1ª hora dos ciclos antigos (o filtro em si usa o dia inteiro).
JANELAS_R1 = [
    (8, 0, 8, 54),
    (12, 0, 12, 54),
    (16, 0, 16, 54),
    (20, 0, 20, 54),
]

# ENTRADA pré-jogo: todo hh:55 (janela até hh:59 se o bot reiniciar), 24 horas.
HORAS_ENTRADA = tuple(range(24))
JANELAS_ENTRADA = [(h, 55, h, 59) for h in HORAS_ENTRADA]

def _agenda_moviodds():
    """160 consultas/dia: odds e resultados em minutos diferentes, nas 24 horas.

    Odds em :40 e :52 deixam o cache com menos de 20 min no hh:55, e o próprio
    :55 consulta de novo. Resultados em :10, :30 e :48 (e :20 em 16 horas)
    atualizam a forma do dia entre um envio e outro. 07:48 permanece.
    """
    odds, resultados = [], []
    for h in range(24):
        resultados.append((h, 10))
        if h % 3 != 2:
            resultados.append((h, 20))
        resultados.append((h, 30))
        odds.append((h, 40))
        resultados.append((h, 48))
        odds.append((h, 52))
        odds.append((h, 55))
    return tuple(odds), tuple(resultados)

MOVIODDS_MINUTOS_ODDS, MOVIODDS_MINUTOS_RESULTADOS = _agenda_moviodds()
# Um minuto = uma chamada (odds ou resultados). 160/dia × 31 = 4.960, abaixo de 5.000.
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
    """Última lista de odds e o instante (time.time) da consulta que a gravou."""
    def __init__(self):
        self.lista: List[OddsMatch] = []
        self.quando: Optional[float] = None
        self.tentativas: Dict[str, int] = {}
        self.ultima_tentativa: Dict[str, float] = {}
        self.falhou: Dict[str, bool] = {}

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
    cache.tentativas[slot] = cache.tentativas.get(slot, 0) + 1
    cache.ultima_tentativa[slot] = ts
    cache.falhou[slot] = erro
    if not erro:
        cache.lista = lista
        cache.quando = ts
    log.info("[ODDS] consulta %s -> %s jogos", slot.split("|", 1)[1], len(lista))
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

class FormaDia:
    """Jogos finalizados da Czech Liga Pro desde 00:00 do dia local, em DATA_DIR.

    Cada consulta MoviOdds de resultados funde aqui. O arquivo não é reescrito
    só porque a resposta veio vazia, e um dia novo zera a lista.
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

    def _abrir(self, dia: str):
        if self.dia != dia:
            self.dia = dia
            self.jogos = []
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

    def mesclar_movi(self, jogos: List[dict], agora: datetime):
        dia = agora.astimezone(TZ).strftime("%Y-%m-%d")
        self._abrir(dia)
        novos = []
        for j in jogos or []:
            if j.get("league") != "Czech Liga Pro":
                continue
            quando = j.get("quando")
            if isinstance(quando, datetime):
                quando_dt = quando if quando.tzinfo else TZ.localize(quando)
            else:
                quando_dt = _ler_inicio({"inicio": quando})
            if quando_dt is None or quando_dt.astimezone(TZ).strftime("%Y-%m-%d") != dia:
                continue
            novos.append({
                "id": j.get("id") or f"{j.get('home')}|{j.get('away')}|{quando_dt.isoformat()}",
                "home": j.get("home") or "",
                "away": j.get("away") or "",
                "sets_home": int(j["sets_home"]),
                "sets_away": int(j["sets_away"]),
                "quando": quando_dt.astimezone(TZ).isoformat(),
                "league": "Czech Liga Pro",
            })
        self._fundir(novos)

    def ingerir_resultados(self, resultados: List["Resultado"], agora: Optional[datetime] = None):
        """Aproveita resultados que o ScoreMondo já trouxe, sem chamada MoviOdds extra."""
        agora = agora or agora_cet()
        dia = agora.astimezone(TZ).strftime("%Y-%m-%d")
        self._abrir(dia)
        novos = []
        for r in resultados or []:
            if not r.kickoff or max(r.sets_home, r.sets_away) < 3:
                continue
            quando = r.kickoff if r.kickoff.tzinfo else TZ.localize(r.kickoff)
            if quando.astimezone(TZ).strftime("%Y-%m-%d") != dia:
                continue
            novos.append({
                "id": r.match_id or f"{r.home}|{r.away}|{quando.isoformat()}",
                "home": r.home, "away": r.away,
                "sets_home": r.sets_home, "sets_away": r.sets_away,
                "quando": quando.astimezone(TZ).isoformat(),
                "league": "Czech Liga Pro",
            })
        self._fundir(novos)

    def do_jogador(self, nome: str, dia: str) -> List[dict]:
        if self.dia != dia:
            return []
        out = []
        for j in self.jogos:
            if j.get("league") != "Czech Liga Pro":
                continue
            if mesmo_jogador(j.get("home") or "", nome):
                sf, sc = j["sets_home"], j["sets_away"]
            elif mesmo_jogador(j.get("away") or "", nome):
                sf, sc = j["sets_away"], j["sets_home"]
            else:
                continue
            quando = _ler_inicio({"inicio": j.get("quando")})
            if quando is None:
                continue
            out.append({
                "resultado": classificar(int(sf), int(sc)),
                "sets_favor": int(sf),
                "sets_contra": int(sc),
                "inicio": quando,
            })
        out.sort(key=lambda x: x["inicio"])
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

    @staticmethod
    def parse_results(data: dict) -> List[dict]:
        """Só Czech Liga Pro, status finished, placar de sets (3-0, 3-1, 3-2 e o inverso)."""
        out = []
        for m in data.get("results") or []:
            if m.get("league") != "Czech Liga Pro" or m.get("status") != "finished":
                continue
            sets = _sets_de_placar(m.get("final_score") or "")
            if not sets:
                continue
            sh, sa = sets
            if max(sh, sa) != 3 or min(sh, sa) > 2:
                continue
            quando = _parse_kickoff(m.get("finished_at") or m.get("kickoff_utc"))
            if quando is None:
                continue
            out.append({
                "id": str(m.get("fixture_id") or "") or None,
                "home": m.get("home") or "",
                "away": m.get("away") or "",
                "sets_home": sh,
                "sets_away": sa,
                "quando": quando,
                "league": "Czech Liga Pro",
            })
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
    """Jogos ainda não iniciados cujo início cai na 2ª rodada do slot (hh+1:00 .. hh+1:50 CET).

    Sem horário de início o jogo não é 2ª rodada.
    """
    ini, fim = janela_rodada2(slot_key)
    out, vistos = [], set()
    for o in odds_list:
        if o.in_play or o.kickoff is None or not (ini <= o.kickoff <= fim):
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

def _rotulo(nome: str, outro: str) -> str:
    """Primeiro nome, ou o nome inteiro se os dois jogadores compartilham o primeiro."""
    def prim(n: str) -> str:
        partes = str(n or "").split()
        return partes[0] if partes else ""
    a, b = prim(nome), prim(outro)
    if a and a.casefold() == b.casefold():
        return _html(nome)
    return _html(a or nome)

def _placar(entry: Optional[dict]) -> Optional[str]:
    if not entry:
        return None
    sf, sc = entry.get("sets_favor"), entry.get("sets_contra")
    if sf is None or sc is None:
        return None
    return f"{sf}-{sc}"

def _frase_r1(nome: str, entry: Optional[dict], outro: str) -> str:
    """'Jan venceu 3-1' / 'Petr perdeu 1-3' / 'venceu 3-2', com o nome escapado."""
    rot = _rotulo(nome, outro)
    if not entry:
        return rot
    res = entry.get("resultado") or ""
    if res in ("limpo", "desgaste"):
        verbo = "venceu"
    elif res == "derrota":
        verbo = "perdeu"
    else:
        verbo = ""
    placar = _placar(entry)
    if verbo and placar:
        return f"{rot} {verbo} {placar}"
    if verbo:
        return f"{rot} {verbo}"
    if placar:
        return f"{rot} {placar}"
    return rot

def _resumo_r1(n1: str, h1: Optional[dict], n2: str, h2: Optional[dict]) -> str:
    partes = []
    if h1:
        partes.append(_frase_r1(n1, h1, n2))
    if h2:
        partes.append(_frase_r1(n2, h2, n1))
    return ", ".join(partes)

def _dia_local(ref: Optional[datetime]) -> str:
    base = ref or agora_cet()
    if base.tzinfo is None:
        base = TZ.localize(base)
    return base.astimezone(TZ).strftime("%Y-%m-%d")

def _jogos_do_historico(entry: Optional[dict], dia: str) -> List[dict]:
    if not entry:
        return []
    itens = entry.get("jogos") or [entry]
    out = []
    for j in itens:
        if not isinstance(j, dict):
            continue
        ini = _ler_inicio(j) or _ler_inicio(entry)
        sf, sc = j.get("sets_favor"), j.get("sets_contra")
        if ini is None or _dia_local(ini) != dia or sf is None or sc is None:
            continue
        sf, sc = int(sf), int(sc)
        out.append({
            "resultado": j.get("resultado") or classificar(sf, sc),
            "sets_favor": sf,
            "sets_contra": sc,
            "inicio": ini,
        })
    out.sort(key=lambda j: j["inicio"])
    return out

def _jogos_do_jogador(nome: str, hist: Historico, forma: Optional[FormaDia], dia: str) -> List[dict]:
    jogos = forma.do_jogador(nome, dia) if forma is not None else []
    vistos = set()
    for j in jogos:
        vistos.add((j["inicio"].strftime("%Y-%m-%d %H:%M"), j["sets_favor"], j["sets_contra"]))
    entry = hist.get(nome) if hist is not None else None
    for j in _jogos_do_historico(entry, dia):
        chave = (j["inicio"].strftime("%Y-%m-%d %H:%M"), j["sets_favor"], j["sets_contra"])
        if chave in vistos:
            continue
        vistos.add(chave)
        jogos.append(j)
    jogos.sort(key=lambda j: j["inicio"])
    return jogos

def _placar_jogador(j: dict) -> str:
    return f"{j['sets_favor']}-{j['sets_contra']}"

def _so_vitorias(jogos: List[dict]) -> bool:
    return bool(jogos) and all(j["resultado"] in ("limpo", "desgaste") for j in jogos)

def _so_derrotas(jogos: List[dict]) -> bool:
    return bool(jogos) and all(j["resultado"] == "derrota" for j in jogos)

def _derrotas(jogos: List[dict]) -> List[dict]:
    return [j for j in jogos if j["resultado"] == "derrota"]

def _tem_3_2(jogos: List[dict]) -> bool:
    return any(j["sets_favor"] == 3 and j["sets_contra"] == 2 for j in jogos)

def _limpas(jogos: List[dict]) -> List[dict]:
    return [j for j in jogos if j["sets_favor"] == 3 and j["sets_contra"] <= 1]

def _feias(jogos: List[dict]) -> List[dict]:
    return [j for j in jogos if j["sets_contra"] == 3 and j["sets_favor"] in (0, 1)]

def _texto_limpas(n: int) -> str:
    if n == 1:
        return "⏳ favorito só tem 1 vitória limpa hoje, precisa de 2"
    return f"⏳ favorito só tem {n} vitórias limpas hoje, precisa de 2"

def _linha_hoje(fav: str, jogos_fav: List[dict], jogos_und: List[dict]) -> str:
    sf = ", ".join(_placar_jogador(j) for j in jogos_fav)
    su = ", ".join(_placar_jogador(j) for j in jogos_und)
    return f"{_html(fav)} hoje: {sf} | Adversário hoje: {su}"

def _resumo_jogos(n1: str, j1: List[dict], n2: str, j2: List[dict]) -> str:
    def parte(nome, jogos, outro):
        if len(jogos) == 1:
            return _frase_r1(nome, jogos[0], outro)
        scores = ", ".join(_placar_jogador(j) for j in jogos)
        return f"{_rotulo(nome, outro)} hoje: {scores}"
    return ", ".join(p for p in (parte(n1, j1, n2), parte(n2, j2, n1)) if p)

def _odds_do_par(player1: str, player2: str, odds_map: Dict[str, OddsMatch]):
    om = achar_odds(player1, player2, [o for o in odds_map.values() if not o.in_play])
    if om and mesmo_jogador(om.home, player1):
        return om.odd_home, om.odd_away
    if om and mesmo_jogador(om.away, player1):
        return om.odd_away, om.odd_home
    return None, None

def avaliar(m, hist: Historico, odds_map: Dict[str, OddsMatch],
            forma: Optional[FormaDia] = None) -> Tuple[str, List[str], Optional[str]]:
    """Aplica as regras a qualquer objeto com .player1 e .player2 (LiveMatch ou OddsMatch)."""
    return avaliar_par(m.player1, m.player2, hist, odds_map,
                       kickoff=getattr(m, "kickoff", None), forma=forma)

def avaliar_par(player1: str, player2: str, hist: Historico,
                odds_map: Dict[str, OddsMatch],
                kickoff: Optional[datetime] = None,
                forma: Optional[FormaDia] = None) -> Tuple[str, List[str], Optional[str]]:
    """Filtro rígido pela forma do dia. O favorito sai só das odds deste jogo."""
    dia = _dia_local(kickoff)
    j1 = _jogos_do_jogador(player1, hist, forma, dia)
    j2 = _jogos_do_jogador(player2, hist, forma, dia)
    if not j1 or not j2:
        faltam = [n for n, j in ((player1, j1), (player2, j2)) if not j]
        quem = " e ".join(_html(n) for n in faltam)
        return "indefinido", [f"sem jogo finalizado hoje de {quem}"], None

    resumo = _resumo_jogos(player1, j1, player2, j2)
    odd1, odd2 = _odds_do_par(player1, player2, odds_map)
    fav = None
    if odd1 and odd2 and odd1 != odd2 and min(odd1, odd2) <= ODD_MAX_FAVORITO:
        if odd1 < odd2:
            fav = (player1, player2, j1, j2, odd1)
        else:
            fav = (player2, player1, j2, j1, odd2)

    if _so_derrotas(j1) and _so_derrotas(j2):
        return "bloqueado", [f"Duelo de Perdedores (Regra 3): {resumo}"], None

    if fav:
        fav_nome, _und, jf, _ju, odd_fav = fav
        perdas = _derrotas(jf)
        if perdas:
            placar = ", ".join(_placar_jogador(j) for j in perdas)
            return "bloqueado", [
                f"❌ favorito {_html(fav_nome)} já perdeu hoje ({placar}) — odd {odd_fav:.2f} ignorada"
            ], None
        if _tem_3_2(jf):
            return "bloqueado", ["⚠️ alerta amarelo: vitória sofrida 3-2"], None

    if _so_vitorias(j1) and _so_vitorias(j2):
        return "bloqueado", [f"Duelo de Vencedores (Regra 2): {resumo}"], None

    if not odd1 or not odd2:
        return "bloqueado", [f"sem odds de mercado: {resumo}" if resumo else "sem odds de mercado"], None
    if fav is None:
        return "bloqueado", [
            f"odds {odd1:.2f} x {odd2:.2f}, sem favorito claro (máx {ODD_MAX_FAVORITO:.2f}): {resumo}"
        ], None

    fav_nome, _und_nome, jf, ju, odd_fav = fav
    limpas = _limpas(jf)
    if len(limpas) < 2:
        return "indefinido", [_texto_limpas(len(limpas))], None
    if not _feias(ju):
        return "bloqueado", ["❌ adversário sem derrota feia hoje"], None

    motivos = [
        f"✓ {_linha_hoje(fav_nome, jf, ju)}",
        f"✓ Favorito: <b>{_html(fav_nome)}</b> (odd {odd_fav:.2f})",
        f"✓ Odds: {_html(player1)} {odd1:.2f} x {_html(player2)} {odd2:.2f}",
    ]
    return "verde", motivos, fav_nome

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

def _bloco_verde(o: OddsMatch, fav: Optional[str], motivos: List[str], extras: Optional[List[str]] = None) -> str:
    texto = (
        f"🚨 <b>{_html(o.home)}</b> vs <b>{_html(o.away)}</b> ({_hora_jogo(o)})\n"
        f"👉 Entrada: <b>{_html(fav or '')}</b>\n" + "\n".join(motivos)
    )
    if extras:
        texto += "\n" + "\n".join(extras)
    return texto

def _linha_sem_entrada(o: OddsMatch, status: str, motivos: List[str], extras: Optional[List[str]] = None) -> str:
    marca = "⏳" if status == "indefinido" else "❌"
    motivo = "; ".join(motivos) if motivos else status
    linha = f"{marca} <b>{_html(o.home)}</b> vs <b>{_html(o.away)}</b> ({_hora_jogo(o)}) — {motivo}"
    if extras:
        linha += "\n" + "\n".join(extras)
    return linha

def _adversario_de(fav: str, p1: str, p2: str) -> str:
    return p2 if mesmo_jogador(fav, p1) else p1

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

def _h2h_bloqueia(hist, fav: Optional[str], p1: str, p2: str, universo: List[str]) -> bool:
    """Critério extra, só de bloqueio. Não altera o filtro da forma do dia."""
    if hist is None or not getattr(hist, "ativo", False) or not fav:
        return False
    try:
        return bool(hist.perdeu_ultimos_2(fav, _adversario_de(fav, p1, p2), universo, agora_cet()))
    except Exception as exc:
        log.warning("SportsAPI365: histórico ignorado (%s)", type(exc).__name__)
        return False

def montar_mensagem_entrada(slot_key: str, confrontos: List[OddsMatch], hist: Historico,
                            odds_list: List[OddsMatch],
                            forma: Optional[FormaDia] = None,
                            historico_anterior: Optional[HistoricoSportsAPI365] = None,
                            ) -> Tuple[List[str], list, List[OddsMatch]]:
    """Retorna (textos, verdes, avaliados_definitivos). Cada texto cabe no Telegram.

    historico_anterior só acrescenta contexto e, no máximo, troca um verde pelo
    bloqueio de H2H. Sem o argumento, a mensagem é a do filtro rígido.
    """
    odds_map = montar_odds_map(odds_list)
    ini, fim = janela_rodada2(slot_key)
    hora = slot_key.split("|")[1]
    cab = (f"🎯 <b>ENTRADA {hora}</b> — Czech Liga Pro "
           f"{ini.strftime('%H:%M')}–{fim.strftime('%H:%M')} CET")

    if not confrontos:
        return [], [], []

    universo = [n for o in confrontos for n in (o.home, o.away)]
    verdes, definitivos, blocos, linhas = [], [], [], []
    for o in confrontos:
        status, motivos, fav = avaliar(o, hist, odds_map, forma)
        if status == "verde" and _h2h_bloqueia(historico_anterior, fav, o.home, o.away, universo):
            adv = _adversario_de(fav, o.home, o.away)
            status, motivos, fav = "bloqueado", [
                f"❌ H2H: favorito perdeu os 2 últimos para {_html(adv)}"
            ], None
        extras = _linhas_historico(historico_anterior, o.home, o.away, universo)
        if status in ("verde", "bloqueado"):
            definitivos.append(o)
        if status == "verde":
            verdes.append((o, fav))
            blocos.append(_bloco_verde(o, fav, motivos, extras))
        else:
            linhas.append(_linha_sem_entrada(o, status, motivos, extras))

    aviso = "" if verdes else "Entrada: NENHUMA — sem desnível claro nesta rodada"
    rodape = f"⏰ {agora_cet().strftime('%H:%M:%S')} CET"
    textos = _empacotar_entrada(cab, blocos, aviso, linhas, rodape)
    return textos, verdes, definitivos

def processar_entrada(slot_key: str, hist: Historico, sinais: CacheSet, entradas: CacheSet,
                      tg: Telegram, odds_list: List[OddsMatch], apostas: "Apostas" = None,
                      forma: Optional[FormaDia] = None,
                      historico_anterior: Optional[HistoricoSportsAPI365] = None) -> bool:
    if entradas.has(slot_key):
        return False
    confrontos = confrontos_rodada2(odds_list, slot_key)
    if not confrontos:
        log.info(f"[ENTRADA {slot_key}] sem jogos da Czech Liga Pro nesta hora")
        return False
    textos, verdes, definitivos = montar_mensagem_entrada(
        slot_key, confrontos, hist, odds_list, forma, historico_anterior)
    if not textos:
        log.error(f"[ENTRADA {slot_key}] falha ao enviar — tenta de novo no próximo ciclo")
        return False
    for texto in textos:
        if not tg.send(texto):
            log.error(f"[ENTRADA {slot_key}] falha ao enviar — tenta de novo no próximo ciclo")
            return False
    entradas.add(slot_key)
    ini, _fim = janela_rodada2(slot_key)
    dia = ini.strftime("%Y-%m-%d")
    for o in definitivos:   # verdes e bloqueados: o ao vivo não reavalia
        sinais.add(chave_sinal(o.home, o.away, dia))
    if apostas is not None:
        bloco = f"{ini.hour:02d}"
        for o, fav in verdes:
            apostas.add(o.home, o.away, fav, bloco, "55", o.kickoff)
    log.info(f"[ENTRADA {slot_key}] confrontos={len(confrontos)} verdes={len(verdes)}")
    return True

# ══════════════════════════════════════════════════════════════════════════════
# PROCESSAMENTO AO VIVO (R1 grava / R2 fallback)
# ══════════════════════════════════════════════════════════════════════════════

def processar(matches: List[LiveMatch], hist: Historico, finished: CacheSet,
              sinais: CacheSet, tg: Telegram, modo: str, odds_list: List[OddsMatch],
              apostas: "Apostas" = None, forma: Optional[FormaDia] = None,
              historico_anterior: Optional[HistoricoSportsAPI365] = None):
    dia = agora_cet().strftime("%Y-%m-%d")
    universo = [n for m in matches for n in (m.player1, m.player2)]

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
                continue   # já enviado/avaliado às hh:55
            # Só pré-jogo: odd ao vivo significa que o confronto já começou.
            if _tem_odd_ao_vivo(m.player1, m.player2, odds_list):
                continue
            agora = agora_cet()
            janela = _janela_r2_inicio(agora)
            pre = achar_odds(m.player1, m.player2, [o for o in odds_list if not o.in_play])
            kickoff = getattr(m, "kickoff", None) or (pre.kickoff if pre else None)
            if (janela is None or kickoff is None or not (janela[0] <= kickoff <= janela[1])
                    or kickoff <= agora):
                continue
            if getattr(m, "kickoff", None) is None:
                m.kickoff = kickoff
            odds_map = montar_odds_map([o for o in odds_list if not o.in_play])
            status, motivos, fav = avaliar(m, hist, odds_map, forma)
            if status == "verde" and _h2h_bloqueia(historico_anterior, fav, m.player1, m.player2, universo):
                status = "bloqueado"
            if status == "verde":
                texto = (
                    f"🚨 <b>SINAL VERDE</b> (ao vivo)\n\n"
                    f"<b>{_html(m.player1)}</b> vs <b>{_html(m.player2)}</b>\n"
                    f"👉 Entrada: <b>{_html(fav or '')}</b>\n"
                    f"Placar: {m.score1 if m.score1 is not None else '-'} : {m.score2 if m.score2 is not None else '-'} ({m.current_set or '—'})\n\n"
                    + "\n".join(motivos) +
                    f"\n\n⏰ {agora_cet().strftime('%H:%M:%S')} CET"
                )
                partes = _partir_telegram(texto)
                if partes and all(tg.send(p) for p in partes):
                    sinais.add(key_s)
                    if apostas is not None:
                        apostas.add(m.player1, m.player2, fav, f"{agora_cet().hour:02d}", "ao_vivo")
                    log.info(f"SINAL VERDE (ao vivo) → {m.player1} vs {m.player2}")

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
    "Somente <b>Czech Liga Pro</b>, 24 h (madrugada inclusive)\n"
    "🎯 ENTRADA: <b>todo hh:55</b>, jogos da hora seguinte\n"
    "Forma do dia desde 00:00 CET"
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
JANELA_SAUDACAO_MIN = 4    # termina antes do hh:55, agora que toda hora tem entrada
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
                "🎯 Entrada todo hh:55 (CET), só Czech Liga Pro.\n"
                "Bora com disciplina! 💪")
    if chave == "boatarde":
        st = estatisticas(apostas.periodo(dia, dia))
        parcial = f"📊 Parcial de hoje: {fmt_placar(st)}\n" if (st["g"] or st["r"]) else ""
        return ("🌤️ <b>Boa tarde, time!</b>\n\n"
                f"💬 “{frase}”\n\n" + parcial +
                "🎯 Próxima entrada no próximo hh:55 (CET)")
    return ("🌙 <b>Boa noite, pessoal!</b>\n\n"
            f"💬 “{frase}”\n\n"
            "A entrada seguinte sai no próximo hh:55. Descansem! 😴")

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

            slot = slot_entrada_atual()
            if slot and not entradas.has(slot) and time.time() - ultima_tentativa_entrada >= 30:
                ultima_tentativa_entrada = time.time()
                registrar_resultados_r1(_trazer_resultados(scoremondo, forma), hist, finished, odds_now)
                fixtures = scoremondo.fetch_fixtures()
                fonte = com_odds(fixtures, odds_now) if fixtures else odds_now
                if not fixtures:
                    log.warning("ScoreMondo fixtures vazio — usando confrontos do MoviOdds (se houver)")
                if fonte or agora_cet().minute >= 58:
                    processar_entrada(slot, hist, sinais, entradas, tg, fonte, apostas, forma,
                                      historico_anterior)
                else:
                    log.warning(f"[ENTRADA {slot}] sem dados ainda — nova tentativa em 30 s")

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
                              historico_anterior)
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
