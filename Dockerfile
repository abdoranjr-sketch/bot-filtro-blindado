FROM python:3.12-slim
ENV PYTHONUNBUFFERED=1 \
    DATA_DIR=/data
WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY bot_filtro_blindado_v5_final.py historico_sportsapi365.py ./
RUN mkdir -p /data
# Monte um volume persistente em /data (histórico, entradas e placar)
CMD ["python", "bot_filtro_blindado_v5_final.py"]
