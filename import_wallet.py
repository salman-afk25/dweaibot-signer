"""
Import private key ke signer DWEAIBOT - HANYA dari terminal server signer.

Cara pakai (di server yang sama dengan signer, signer sudah jalan):
  python3 import_wallet.py

Script ini:
- Meminta private key lewat getpass (tidak tampil di layar, tidak masuk
  shell history, JANGAN pakai argumen command line).
- Mengirimnya HANYA ke http://127.0.0.1:8000/wallet/import (localhost).
- Tidak menyimpan, tidak mencetak, dan tidak me-log private key.
- Mengembalikan HANYA alamat wallet hasil import.

JANGAN:
- Jangan paste private key ke Telegram, ke chat Muse, ke screenshot,
  atau ke file .env / .txt / repo.
- Jangan pakai wallet utama kamu kalau belum paham risikonya.
  Pakai dompet khusus bot dengan saldo kecil dulu untuk tes.
- Jangan jalankan script ini dari komputer lain / lewat API publik.
  Endpoint /wallet/import dirancang untuk localhost, dan signer
  seharusnya tidak diekspos tanpa TLS + secret yang kuat kalau
  mau diakses Apps Script dari internet (lihat README bagian sambungan).
"""
import getpass
import os
import sys

import httpx
from dotenv import load_dotenv

load_dotenv()

SIGNER_URL = os.getenv("SIGNER_API_URL", "http://127.0.0.1:8000").rstrip("/")
SECRET = os.getenv("SIGNER_API_SECRET", "")

if not SECRET:
    print("SIGNER_API_SECRET belum diatur di .env")
    sys.exit(1)

if SIGNER_URL not in ("http://127.0.0.1:8000", "http://localhost:8000") and "127.0.0.1" not in SIGNER_URL and "localhost" not in SIGNER_URL:
    print("DITOLAK: script ini hanya boleh ke signer localhost.")
    print(f"SIGNER_API_URL di .env: {SIGNER_URL}")
    sys.exit(1)

key = getpass.getpass("Tempel private key (tidak tampil di layar, Enter untuk kirim ke localhost): ").strip()
if not key:
    print("Dibatalkan: key kosong.")
    sys.exit(1)

try:
    r = httpx.post(
        f"{SIGNER_URL}/wallet/import",
        json={"private_key": key},
        headers={"Authorization": f"Bearer {SECRET}"},
        timeout=20,
    )
finally:
    # Hapus dari memori proses ini secepatnya.
    key = "0" * 64

if r.status_code == 409:
    print("Gagal: wallet sudah ada. Backup + hapus keystore lama dulu kalau memang mau ganti.")
elif r.status_code != 200:
    print(f"Gagal: {r.status_code} {r.text[:200]}")
else:
    print(f"Berhasil import. Alamat wallet: {r.json().get('address')}")
    print("Private key TIDAK ditampilkan dan sudah terenkripsi ke keystore.json.")
