FROM python:3.12-slim
WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY main.py bot.py import_wallet.py run_all.py ./
# JANGAN copy .env / keystore.json ke image. Isi lewat Environment Variables
# di dashboard host (Render/Railway/Fly/dll). Bot polling tidak butuh port inbound.
CMD ["python", "run_all.py"]
