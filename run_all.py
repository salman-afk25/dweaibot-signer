"""
Jalankan DWEAIBOT tanpa VPS / domain, tanpa port publik.

Cara kerja:
- Signer jalan di localhost:8000 di proses yang sama (satu host).
- Bot Telegram jalan dengan POLLING, bukan webhook.
  Polling = bot yang aktif mengambil update dari server Telegram (outbound).
  Jadi bot TIDAK butuh domain, TIDAK butuh port inbound, dan TIDAK butuh
  URL publik. Telegram tidak pernah memanggil server kamu.
- Karena signer hanya di localhost dan bot + signer satu host, tidak ada
  orang luar yang bisa mencapai signer lewat internet, selama host itu
  tidak sengaja membuka port 8000 ke publik.

Jalankan:
  python3 run_all.py
  (di laptop/PC kamu, atau di host gratis seperti Render/Railway/Fly
   sebagai worker - lihat Dockerfile)

Berhenti: Ctrl+C, script ini mematikan signer juga.

Syarat .env (lihat .env.example):
  TELEGRAM_TOKEN, ALLOWED_TELEGRAM_USER_ID, SIGNER_API_SECRET,
  KEYSTORE_PASSWORD, dan RPC chain yang dipakai.
  Tanpa itu, script berhenti sebelum apa pun jalan, dan tidak mencetak secret.
"""
import os
import subprocess
import sys
import time
import urllib.request

from dotenv import load_dotenv

load_dotenv()

HERE = os.path.dirname(os.path.abspath(__file__))


def need(name):
    v = os.getenv(name, "")
    if not v:
        print(f"Berhenti: {name} belum diatur di .env")
        sys.exit(1)
    return v


def wait_health(timeout=20):
    for _ in range(timeout):
        try:
            with urllib.request.urlopen("http://127.0.0.1:8000/health", timeout=3) as r:
                if r.status == 200:
                    return True
        except Exception:
            time.sleep(1)
    return False


def main():
    need("TELEGRAM_TOKEN")
    need("ALLOWED_TELEGRAM_USER_ID")
    need("SIGNER_API_SECRET")
    need("KEYSTORE_PASSWORD")

    signer = subprocess.Popen([sys.executable, os.path.join(HERE, "main.py")])
    try:
        if not wait_health():
            print("Signer tidak jalan di localhost:8000, batalkan bot.")
            signer.terminate()
            sys.exit(1)
        print("Signer jalan di localhost:8000 (tidak publik). Bot polling mulai...")
        bot = subprocess.Popen([sys.executable, os.path.join(HERE, "bot.py")])
        try:
            bot.wait()
        except KeyboardInterrupt:
            print("\nBerhenti...")
        finally:
            bot.terminate()
    finally:
        signer.terminate()
        try:
            signer.wait(timeout=5)
        except Exception:
            signer.kill()
    print("Berhenti. Signer + bot sudah dimatikan.")


if __name__ == "__main__":
    main()
