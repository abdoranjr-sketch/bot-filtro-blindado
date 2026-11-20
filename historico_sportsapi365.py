#!/usr/bin/env python3
"""Resultados anteriores da Czech Liga Pro via SportsAPI365 (RapidAPI).

Plano gratuito: 50 requisições por dia. Este módulo gasta no máximo 40 e para
antes se o cabeçalho x-ratelimit-requests-remaining chegar na folga. A chave vem
só da env var SPORTSAPI365_KEY. Sem ela, nada é baixado e nenhuma linha de
histórico é calculada.

A coleta é uma vez por dia, depois das 00:30 Europe/Prague: o dia anterior, em
até 3 páginas. No primeiro arranque sem cache, até 7 dias para trás. O arquivo
DATA_DIR/historico_sportsapi365.json guarda 14 dias. Forma e H2H saem desse
cache — nunca há chamada por jogo ou por jogador.

include=form não é usado: as últimas 5 da API não cobrem 7 dias, e a conta é
feita com os jogos já guardados.
"""
from __future__ import annotations

import json
import logging
import re
import unicodedata
from datetime import datetime, timedelta, date
from pathlib import Path
from typing import Callable, Dict, Iterable, List, Optional, Sequence, Tuple

import pytz
import requests

log = logging.getLogger("FiltroV5")

HOST = "table-tennis-api-live-scores-stats-odds-predictions.p.rapidapi.com"
URL = f"https://{HOST}/msdata/v1/table_tennis/events"
TORNEIO = "87328107"
LIGA = "Czech Liga Pro"

# 50 é o teto duro do plano. 40 deixa 10 de folga; o cabeçalho remaining também
# impede a próxima chamada quando já não há essa folga.
TETO_PLANO = 50
TETO_DIA = 40
FOLGA_RESTANTE = TETO_PLANO - TETO_DIA

RETENCAO_DIAS = 14
FORMA_DIAS = 7
H2H_DIAS = 14
BACKFILL_DIAS = 7
MAX_PAGINAS = 3
LIMITE_PAGINA = 100
RETRY_REDE_S = 30 * 60
HORA_COLETA = (0, 30)

ARQUIVO = "historico_sportsapi365.json"
CONTADOR = "sportsapi365_contador.json"

TZ_PRAGA = pytz.timezone("Europe/Prague")

_SUFIXOS = {"jnr", "junior", "jr", "snr", "senior", "sr", "st", "ml"}

HttpGet = Callable[..., object]


def normalizar_nome(nome: str) -> Tuple[str, ...]:
    """Tokens do nome, sem acento, caixa, pontuação nem sufixo (jr, junior…)."""
    n = unicodedata.normalize("NFKD", nome or "").encode("ascii", "ignore").decode().lower()
    return tuple(t for t in re.split(r"[^a-z]+", n) if t and t not in _SUFIXOS)


def mesmo_nome(a: str, b: str) -> bool:
    ta, tb = normalizar_nome(a), normalizar_nome(b)
    return bool(ta) and frozenset(ta) == frozenset(tb)


def nome_api_inicial(nome: str) -> Optional[Tuple[Tuple[str, ...], str]]:
    """'Bilek Z.' ou 'Bílek Z' vira (('bilek',), 'z'). None se não for Sobrenome Inicial."""
    toks = normalizar_nome(nome)
    if len(toks) < 2 or len(toks[-1]) != 1:
        return None
    sobrenome = toks[:-1]
    if any(len(p) < 2 for p in sobrenome):
        return None
    return sobrenome, toks[-1]


def hipoteses_locais(nome: str) -> List[Tuple[Tuple[str, ...], str]]:
    """Cada jeito de ler um nome completo como (sobrenome, inicial).

    'Zdenek Bilek' e 'Bilek Zdenek' incluem (('bilek',), 'z'). A ordem dos
    tokens do sobrenome é preservada. Não chuta um nome de um token só.
    """
    toks = normalizar_nome(nome)
    if len(toks) < 2:
        return []
    saida: List[Tuple[Tuple[str, ...], str]] = []
    vistos = set()
    for i, tok in enumerate(toks):
        resto = toks[:i] + toks[i + 1:]
        if not resto or any(len(p) < 2 for p in resto):
            continue
        chave = (resto, tok[0])
        if chave not in vistos:
            vistos.add(chave)
            saida.append(chave)
    return saida


def nomes_compativeis(nome_moviodds: str, nome_api: str) -> bool:
    """True se o nome da MoviOdds pode ser a mesma pessoa que o da SportsAPI365.

    O formato da API é sobrenome + inicial ('Bilek Z.'). Se a API mandar o nome
    completo, só vale igualdade dos tokens — sem aproximar.
    """
    api = nome_api_inicial(nome_api)
    if api is not None:
        return api in hipoteses_locais(nome_moviodds)
    local = normalizar_nome(nome_moviodds)
    remoto = normalizar_nome(nome_api)
    return len(local) >= 2 and frozenset(local) == frozenset(remoto)


def resolver_ids(nomes: Sequence[str], catalogo: Dict[int, str]) -> Dict[str, Optional[int]]:
    """Casa cada nome local com um id da API. Sem casamento único, o valor é None.

    Único significa: um só id compatível, e esse id não serve para outra pessoa
    da lista. 'Zdenek Bilek' e 'Zbynek Bilek' diante de um único 'Bilek Z.' ficam
    os dois sem histórico.
    """
    grupos: List[List[str]] = []
    for nome in nomes:
        if not nome or not normalizar_nome(nome):
            continue
        for grupo in grupos:
            if mesmo_nome(grupo[0], nome):
                grupo.append(nome)
                break
        else:
            grupos.append([nome])

    candidatos: List[set] = []
    for grupo in grupos:
        ids = set()
        for pid, nome_api in catalogo.items():
            if isinstance(nome_api, str) and nomes_compativeis(grupo[0], nome_api):
                ids.add(pid)
        candidatos.append(ids)

    saida: Dict[str, Optional[int]] = {}
    for i, grupo in enumerate(grupos):
        ids = candidatos[i]
        pid: Optional[int] = None
        if len(ids) == 1:
            unico = next(iter(ids))
            if not any(unico in candidatos[j] for j in range(len(grupos)) if j != i):
                pid = unico
        for nome in grupo:
            saida[nome] = pid
    return saida


def percentual_limpas(limpas: int, total: int) -> int:
    """Fatia dos jogos que foram vitória limpa (3-0 ou 3-1), meio arredonda para cima."""
    if total <= 0 or limpas <= 0:
        return 0
    return (limpas * 100 + total // 2) // total


def analisar_evento(item: dict) -> Optional[dict]:
    """Um item de /events, ou None se não for jogo terminado da liga com placar de sets."""
    if not isinstance(item, dict):
        return None
    competicao = item.get("competitionName")
    if isinstance(competicao, str) and competicao.strip() and competicao.strip() != LIGA:
        return None
    status = item.get("status")
    if isinstance(status, str) and status.strip() and status.strip().lower() != "finished":
        return None
    home = item.get("homeTeam") if isinstance(item.get("homeTeam"), dict) else {}
    away = item.get("awayTeam") if isinstance(item.get("awayTeam"), dict) else {}
    try:
        sh = int((item.get("homeScore") or {})["current"])
        sa = int((item.get("awayScore") or {})["current"])
        ts = int(item.get("startTimestamp"))
        hid = int(home.get("id"))
        aid = int(away.get("id"))
    except (TypeError, ValueError, KeyError):
        return None
    if hid == aid or max(sh, sa) != 3 or min(sh, sa) < 0 or min(sh, sa) > 2:
        return None
    hn = str(home.get("name") or "").strip()
    an = str(away.get("name") or "").strip()
    if not hn or not an:
        return None
    eid = item.get("id")
    return {
        "id": None if eid is None else str(eid),
        "ts": ts,
        "home_id": hid,
        "home": hn,
        "away_id": aid,
        "away": an,
        "sh": sh,
        "sa": sa,
    }


def _inicio_do_dia(d: date) -> int:
    return int(TZ_PRAGA.localize(datetime(d.year, d.month, d.day)).timestamp())


def _data_praga(agora: datetime) -> date:
    return agora.astimezone(TZ_PRAGA).date()


def _cabecalho(headers, nome: str) -> Optional[str]:
    if not headers:
        return None
    try:
        pares = headers.items()
    except Exception:
        return None
    for chave, valor in pares:
        if str(chave).lower() == nome.lower():
            return None if valor is None else str(valor)
    return None


def _inteiro(valor) -> Optional[int]:
    if valor is None:
        return None
    try:
        return int(float(str(valor).strip()))
    except (TypeError, ValueError):
        return None


def _instante_reset(valor, agora: datetime) -> Optional[float]:
    """Unix (s ou ms) ou segundos até o reset. None se não der para ler."""
    if valor is None or str(valor).strip() == "":
        return None
    texto = str(valor).strip()
    try:
        n = float(texto)
    except (TypeError, ValueError):
        try:
            dt = datetime.fromisoformat(texto.replace("Z", "+00:00"))
            if dt.tzinfo is None:
                dt = pytz.utc.localize(dt)
            return dt.timestamp()
        except (TypeError, ValueError):
            return None
    if n > 10_000_000_000:
        return n / 1000.0
    if n > 1_000_000_000:
        return n
    if n >= 0:
        return agora.timestamp() + n
    return None


def _chave_jogo(j: dict) -> str:
    if j.get("id"):
        return f"id:{j['id']}"
    return f"{j.get('home_id')}|{j.get('away_id')}|{j.get('ts')}"


def _gravar_atomico(path: Path, payload: dict):
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(json.dumps(payload, ensure_ascii=False, indent=1), encoding="utf-8")
    tmp.replace(path)


def _tem_mais(data: dict, items: list, page: int) -> bool:
    has_more = data.get("hasMore")
    if isinstance(has_more, str):
        has_more = has_more.strip().lower() == "true"
    if has_more is True:
        return True
    if has_more is False:
        return False
    try:
        total = int(data["totalPages"]) if data.get("totalPages") is not None else None
        atual = int(data["page"]) if data.get("page") is not None else page
    except (TypeError, ValueError):
        total = atual = None
    if total is not None and atual is not None:
        return atual < total
    return len(items) >= LIMITE_PAGINA


class OrcamentoSportsAPI:
    """Contador persistido. No máximo TETO_DIA chamadas por janela, e nunca come a folga."""

    def __init__(self, path: Path):
        self.path = path
        self.usadas = 0
        self.remaining: Optional[int] = None
        self.reset_em: Optional[float] = None
        self.desligado_ate: Optional[float] = None
        self.janela = ""
        self.avisou = False
        self.proxima_tentativa: Optional[float] = None
        self._carregar()

    def _carregar(self):
        if not self.path.exists():
            return
        try:
            raw = json.loads(self.path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            log.warning("SportsAPI365: contador ilegível, recomeçando a janela")
            return
        if not isinstance(raw, dict):
            return
        self.usadas = int(raw.get("usadas") or 0)
        self.remaining = raw.get("remaining") if isinstance(raw.get("remaining"), int) else None
        self.reset_em = raw.get("reset_em") if isinstance(raw.get("reset_em"), (int, float)) else None
        self.desligado_ate = raw.get("desligado_ate") if isinstance(raw.get("desligado_ate"), (int, float)) else None
        self.janela = str(raw.get("janela") or "")
        self.avisou = bool(raw.get("avisou"))
        prox = raw.get("proxima_tentativa")
        self.proxima_tentativa = prox if isinstance(prox, (int, float)) else None

    def save(self):
        try:
            _gravar_atomico(self.path, {
                "usadas": self.usadas,
                "remaining": self.remaining,
                "reset_em": self.reset_em,
                "desligado_ate": self.desligado_ate,
                "janela": self.janela,
                "avisou": self.avisou,
                "proxima_tentativa": self.proxima_tentativa,
            })
        except OSError:
            log.warning("SportsAPI365: não gravou o contador (%s)", "OSError")

    def sincronizar(self, agora: datetime):
        now = agora.timestamp()
        dia = _data_praga(agora).isoformat()
        mudou = False
        if self.reset_em is not None and now >= self.reset_em:
            self.usadas = 0
            self.remaining = None
            self.reset_em = None
            self.desligado_ate = None
            self.janela = dia
            self.avisou = False
            self.proxima_tentativa = None
            mudou = True
        elif self.desligado_ate is not None and now >= self.desligado_ate:
            self.desligado_ate = None
            self.avisou = False
            mudou = True
        if self.reset_em is None and self.janela != dia:
            self.usadas = 0
            self.remaining = None
            self.desligado_ate = None
            self.janela = dia
            self.avisou = False
            mudou = True
        if not self.janela:
            self.janela = dia
            mudou = True
        if mudou:
            self.save()

    def bloqueado(self, agora: datetime) -> bool:
        self.sincronizar(agora)
        return self.desligado_ate is not None and agora.timestamp() < self.desligado_ate

    def pode(self, agora: datetime) -> bool:
        self.sincronizar(agora)
        if self.desligado_ate is not None and agora.timestamp() < self.desligado_ate:
            return False
        if self.usadas >= TETO_DIA:
            return False
        if self.remaining is not None and self.remaining <= FOLGA_RESTANTE:
            return False
        return True

    def consumir(self, agora: datetime, resposta=None):
        self.sincronizar(agora)
        self.usadas += 1
        if self.janela == "":
            self.janela = _data_praga(agora).isoformat()
        if resposta is not None:
            headers = getattr(resposta, "headers", None)
            rem = _inteiro(_cabecalho(headers, "x-ratelimit-requests-remaining"))
            reset = _instante_reset(_cabecalho(headers, "x-ratelimit-requests-reset"), agora)
            if rem is not None:
                self.remaining = rem
            # Um reset no passado não pode reabrir a janela na hora seguinte.
            if reset is not None and reset > agora.timestamp():
                self.reset_em = reset
            status = getattr(resposta, "status_code", None)
            if status in (429, 403):
                futuro = self.reset_em if self.reset_em is not None and self.reset_em > agora.timestamp() else None
                ate = futuro if futuro is not None else agora.timestamp() + 24 * 3600
                self.desligado_ate = ate
                if futuro is None:
                    self.reset_em = ate
        self.save()

    def avisar_esgotado(self):
        if self.avisou:
            return
        self.avisou = True
        self.save()
        log.info("SportsAPI365: orçamento de %s chamadas no período esgotado", TETO_DIA)

    def liberar_em(self, agora: datetime) -> float:
        if self.desligado_ate is not None and self.desligado_ate > agora.timestamp():
            return self.desligado_ate
        if self.reset_em is not None and self.reset_em > agora.timestamp():
            return self.reset_em
        amanha = _data_praga(agora) + timedelta(days=1)
        return float(_inicio_do_dia(amanha))


class HistoricoSportsAPI365:
    """Cache local dos resultados anteriores. Sem chave, ativo fica False e os métodos não fazem nada."""

    def __init__(self, key: Optional[str], data_dir: Path, http_get: Optional[HttpGet] = None):
        self.key = (key or "").strip()
        self.ativo = bool(self.key)
        self.dir = Path(data_dir)
        self.http_get = http_get or requests.get
        self.path = self.dir / ARQUIVO
        self.jogos: List[dict] = []
        self.dias: set = set()
        self.backfill_pendente = True
        self.concluido_em = ""
        self.orcamento = OrcamentoSportsAPI(self.dir / CONTADOR) if self.ativo else None
        if self.ativo:
            self._carregar()

    def __repr__(self) -> str:
        return f"HistoricoSportsAPI365(ativo={self.ativo}, jogos={len(self.jogos)})"

    def _carregar(self):
        if not self.path.exists():
            self.backfill_pendente = True
            return
        try:
            raw = json.loads(self.path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            log.warning("SportsAPI365: cache ilegível, recomeçando a coleta")
            self.backfill_pendente = True
            return
        if not isinstance(raw, dict):
            self.backfill_pendente = True
            return
        self.jogos = [j for j in (raw.get("jogos") or []) if isinstance(j, dict) and isinstance(j.get("ts"), int)]
        self.dias = {str(d) for d in (raw.get("dias") or [])}
        if "backfill_pendente" in raw:
            self.backfill_pendente = bool(raw.get("backfill_pendente"))
        else:
            self.backfill_pendente = not self.dias and not self.jogos
        self.concluido_em = str(raw.get("concluido_em") or "")

    def _salvar(self):
        try:
            _gravar_atomico(self.path, {
                "backfill_pendente": self.backfill_pendente,
                "concluido_em": self.concluido_em,
                "dias": sorted(self.dias),
                "jogos": self.jogos,
            })
        except OSError:
            log.warning("SportsAPI365: não gravou o histórico (%s)", "OSError")

    def _aviso(self, modelo: str, *args):
        texto = modelo % args if args else modelo
        if self.key:
            texto = texto.replace(self.key, "***")
        log.warning("%s", texto)

    def atualizar(self, agora: datetime) -> bool:
        """Baixa o que falta desta madrugada. Sem chave, ou antes das 00:30, não chama a API."""
        if not self.ativo or self.orcamento is None:
            return False
        local = agora.astimezone(TZ_PRAGA)
        if (local.hour, local.minute) < HORA_COLETA:
            return False
        hoje = local.date()
        if self.concluido_em == hoje.isoformat():
            return False
        if self.orcamento.bloqueado(agora):
            return False
        proxima = self.orcamento.proxima_tentativa
        if proxima is not None and agora.timestamp() < proxima:
            return False
        alvos = self._alvos(hoje)
        if not alvos:
            self.backfill_pendente = False
            self.concluido_em = hoje.isoformat()
            self._salvar()
            return False
        if not self.orcamento.pode(agora):
            self.orcamento.avisar_esgotado()
            self.orcamento.proxima_tentativa = self.orcamento.liberar_em(agora)
            self.orcamento.save()
            return False
        for dia in alvos:
            if not self.orcamento.pode(agora):
                self.orcamento.avisar_esgotado()
                self.orcamento.proxima_tentativa = self.orcamento.liberar_em(agora)
                self.orcamento.save()
                self._salvar()
                return False
            jogos = self._baixar_dia(dia, agora)
            if jogos is None:
                if self.orcamento.bloqueado(agora):
                    self.orcamento.proxima_tentativa = self.orcamento.desligado_ate
                else:
                    self.orcamento.proxima_tentativa = agora.timestamp() + RETRY_REDE_S
                self.orcamento.save()
                self._salvar()
                return False
            self._substituir_dia(dia, jogos)
            self.dias.add(dia)
            self._podar(hoje)
            self.orcamento.proxima_tentativa = None
            self.orcamento.save()
            self._salvar()
            guardados = sum(1 for jogo in self.jogos if jogo.get("dia") == dia)
            log.info("SportsAPI365: %s coletado (%s jogos)", dia, guardados)
        self.backfill_pendente = False
        self.concluido_em = hoje.isoformat()
        self._salvar()
        return True

    def _alvos(self, hoje: date) -> List[str]:
        ontem = hoje - timedelta(days=1)
        if self.backfill_pendente:
            datas = [ontem - timedelta(days=i) for i in range(BACKFILL_DIAS)]
        else:
            datas = [ontem]
        return [d.isoformat() for d in datas if d.isoformat() not in self.dias]

    def _baixar_dia(self, dia: str, agora: datetime) -> Optional[List[dict]]:
        jogos: List[dict] = []
        page = 1
        while page <= MAX_PAGINAS:
            if self.orcamento is None or not self.orcamento.pode(agora):
                return None
            resposta = self._requisitar(dia, page, agora)
            if resposta is None:
                return None
            try:
                data = resposta.json()
            except Exception:
                self._aviso("SportsAPI365: resposta inválida em %s página %s", dia, page)
                return None
            if not isinstance(data, dict):
                self._aviso("SportsAPI365: resposta inválida em %s página %s", dia, page)
                return None
            items = data.get("items") or []
            if not isinstance(items, list):
                self._aviso("SportsAPI365: resposta inválida em %s página %s", dia, page)
                return None
            for item in items:
                evento = analisar_evento(item)
                if evento:
                    jogos.append(evento)
            if not _tem_mais(data, items, page):
                return jogos
            if page == MAX_PAGINAS:
                self._aviso("SportsAPI365: %s limitado a %s páginas", dia, MAX_PAGINAS)
                return jogos
            page += 1
        return jogos

    def _requisitar(self, dia: str, page: int, agora: datetime):
        params = {
            "fromDate": dia,
            "toDate": dia,
            "tournamentId": TORNEIO,
            "status": "finished",
            "page": page,
            "limit": LIMITE_PAGINA,
        }
        headers = {"x-rapidapi-key": self.key, "x-rapidapi-host": HOST}
        try:
            resposta = self.http_get(URL, params=params, headers=headers, timeout=20)
        except Exception as exc:
            if self.orcamento is not None:
                self.orcamento.consumir(agora, None)
            self._aviso("SportsAPI365: falha de rede (%s)", type(exc).__name__)
            return None
        if self.orcamento is not None:
            self.orcamento.consumir(agora, resposta)
        status = getattr(resposta, "status_code", None)
        if status in (429, 403):
            ate = self.orcamento.desligado_ate if self.orcamento is not None else None
            quando = (
                datetime.fromtimestamp(ate, pytz.utc).strftime("%Y-%m-%d %H:%M UTC")
                if ate else "o reset da cota"
            )
            self._aviso("SportsAPI365: HTTP %s; histórico desligado até %s", status, quando)
            return None
        if status != 200:
            self._aviso("SportsAPI365: HTTP %s em %s", status, dia)
            return None
        return resposta

    def _substituir_dia(self, dia: str, jogos: List[dict]):
        novos = []
        chaves = set()
        for jogo in jogos:
            item = dict(jogo)
            item["dia"] = dia
            chave = _chave_jogo(item)
            if chave in chaves:
                continue
            chaves.add(chave)
            novos.append(item)
        self.jogos = [j for j in self.jogos if j.get("dia") != dia and _chave_jogo(j) not in chaves]
        self.jogos.extend(novos)
        self.jogos.sort(key=lambda j: j.get("ts") or 0)

    def _podar(self, hoje: date):
        t0 = _inicio_do_dia(hoje - timedelta(days=RETENCAO_DIAS))
        self.jogos = [j for j in self.jogos if isinstance(j.get("ts"), int) and j["ts"] >= t0]
        limite = hoje - timedelta(days=RETENCAO_DIAS)
        manter = set()
        for dia in self.dias:
            try:
                d = date.fromisoformat(dia)
            except ValueError:
                continue
            if d >= limite:
                manter.add(dia)
        self.dias = manter

    def _na_janela(self, agora: datetime, dias: int) -> List[dict]:
        hoje = _data_praga(agora)
        t0 = _inicio_do_dia(hoje - timedelta(days=dias))
        t1 = _inicio_do_dia(hoje)
        return [j for j in self.jogos if isinstance(j.get("ts"), int) and t0 <= j["ts"] < t1]

    def _catalogo(self, agora: datetime) -> Dict[int, str]:
        cat: Dict[int, str] = {}
        for jogo in self._na_janela(agora, RETENCAO_DIAS):
            try:
                cat[int(jogo["home_id"])] = str(jogo.get("home") or "")
                cat[int(jogo["away_id"])] = str(jogo.get("away") or "")
            except (TypeError, ValueError, KeyError):
                continue
        return cat

    def _mapa(self, universo: Sequence[str], agora: datetime) -> Dict[str, Optional[int]]:
        return resolver_ids(list(universo), self._catalogo(agora))

    @staticmethod
    def _lado(jogo: dict, pid: int) -> Optional[Tuple[int, int]]:
        try:
            hid, aid = int(jogo["home_id"]), int(jogo["away_id"])
            sh, sa = int(jogo["sh"]), int(jogo["sa"])
        except (TypeError, ValueError, KeyError):
            return None
        if hid == pid and aid != pid:
            return sh, sa
        if aid == pid and hid != pid:
            return sa, sh
        return None

    def _ganhou(self, jogo: dict, pid: int) -> bool:
        lado = self._lado(jogo, pid)
        return bool(lado) and lado[0] == 3 and lado[1] <= 2

    def _perdeu(self, jogo: dict, pid: int) -> bool:
        lado = self._lado(jogo, pid)
        return bool(lado) and lado[1] == 3 and lado[0] <= 2

    def _limpa(self, jogo: dict, pid: int) -> bool:
        lado = self._lado(jogo, pid)
        return bool(lado) and lado[0] == 3 and lado[1] <= 1

    @staticmethod
    def _confronto(jogo: dict, a: int, b: int) -> bool:
        try:
            return {int(jogo["home_id"]), int(jogo["away_id"])} == {a, b}
        except (TypeError, ValueError, KeyError):
            return False

    def forma(self, nome: str, universo: Sequence[str], agora: datetime) -> Optional[Tuple[int, int, int]]:
        """(vitórias, derrotas, % limpas) nos 7 dias anteriores, ou None sem casamento único."""
        if not self.ativo:
            return None
        pid = self._mapa(universo, agora).get(nome)
        if pid is None:
            return None
        vitorias = derrotas = limpas = 0
        for jogo in self._na_janela(agora, FORMA_DIAS):
            if self._ganhou(jogo, pid):
                vitorias += 1
                if self._limpa(jogo, pid):
                    limpas += 1
            elif self._perdeu(jogo, pid):
                derrotas += 1
        total = vitorias + derrotas
        if total == 0:
            return None
        return vitorias, derrotas, percentual_limpas(limpas, total)

    def h2h(self, home: str, away: str, universo: Sequence[str], agora: datetime
            ) -> Optional[Tuple[int, int]]:
        """(vitórias do primeiro nome, vitórias do segundo) nos 14 dias, ou None."""
        if not self.ativo:
            return None
        mapa = self._mapa(universo, agora)
        ph, pa = mapa.get(home), mapa.get(away)
        if ph is None or pa is None or ph == pa:
            return None
        jogos = [j for j in self._na_janela(agora, H2H_DIAS) if self._confronto(j, ph, pa)]
        if not jogos:
            return None
        return (
            sum(1 for j in jogos if self._ganhou(j, ph)),
            sum(1 for j in jogos if self._ganhou(j, pa)),
        )

    def perdeu_ultimos_2(self, favorito: str, adversario: str, universo: Sequence[str], agora: datetime) -> bool:
        """True só se os 2 confrontos mais recentes dos 14 dias foram derrotas do favorito."""
        if not self.ativo:
            return False
        mapa = self._mapa(universo, agora)
        pf, pa = mapa.get(favorito), mapa.get(adversario)
        if pf is None or pa is None or pf == pa:
            return False
        jogos = [j for j in self._na_janela(agora, H2H_DIAS) if self._confronto(j, pf, pa)]
        if len(jogos) < 2:
            return False
        jogos.sort(key=lambda j: j.get("ts") or 0, reverse=True)
        return all(self._perdeu(j, pf) for j in jogos[:2])
