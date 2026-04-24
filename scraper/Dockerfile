# ============================================================================
# Scraper service — FastAPI + Playwright
# ============================================================================
# Basado en la imagen oficial de Playwright para Python, que trae preinstalados
# los browsers (Chromium, Firefox, WebKit) y todas las dependencias nativas
# necesarias (libs de X11, fonts, etc.).
# ============================================================================
FROM mcr.microsoft.com/playwright/python:v1.49.1-jammy

WORKDIR /app

# Instalar dependencias Python primero (mejora cacheo de layers)
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copiar código del servicio
COPY . .

# Puerto interno — sólo expuesto dentro de la red Docker
EXPOSE 8000

# Healthcheck: consulta /health cada 30s
HEALTHCHECK --interval=30s --timeout=5s --start-period=15s --retries=3 \
  CMD python -c "import httpx; httpx.get('http://localhost:8000/health').raise_for_status()" || exit 1

CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8000"]
