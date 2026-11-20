# Bot Filtro Blindado — Czech Liga Pro (v5)

Bot de Telegram que analisa a Czech Liga Pro (tênis de mesa) e envia as entradas da 2ª rodada às
**08:55 · 12:55 · 16:55 · 20:55 (CET)**, com GREEN/RED de cada entrada, resumo diário às 22:30,
saudações com frases motivacionais e comandos (/placar /semana /mes /entradas /ajuda /id).

Fontes: ScoreMondo (jogos, resultados e placar ao vivo — páginas públicas) e MoviOdds (odds, opcional).

## Configuração (variáveis de ambiente)
Veja `.env.example`. **Nunca** coloque tokens no código nem faça commit do `.env`.

| Variável | Uso |
|---|---|
| `TELEGRAM_TOKEN` | token do bot (obrigatório) |
| `TELEGRAM_CHAT_ID` | chat privado do dono/admin (obrigatório) |
| `TELEGRAM_GROUP_ID` | canal/grupo onde saem entradas, resultados, resumo e saudações |
| `TELEGRAM_DISCUSSION_ID` | grupo de discussão ligado ao canal (conversa e comandos) |
| `TELEGRAM_OWNER_ID` | id do admin (padrão = `TELEGRAM_CHAT_ID`) |
| `MOVIODDS_KEY` | chave do MoviOdds (odds) |
| `DATA_DIR` | pasta persistente dos dados (ex.: `/data`) |

## Deploy
Railway/Render/Fly usam o `Dockerfile` (ou `Procfile`: `worker: python bot_filtro_blindado_v5.py`).
Monte um volume em `/data`.

## Testes
```
pip install -r requirements.txt
python tests/test_v5.py && python tests/test_v5_discussao.py
```

🔞 +18 · Aposte com responsabilidade.
