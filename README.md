# DWEAIBOT Python Signer + Telegram

Signer Python (FastAPI + web3.py) + bot Telegram polling, owner-only.

## Yang sudah diperbaiki dari kode awal

- Auth signer menerima `Bearer <secret>` maupun secret mentah.
- Amount pakai `Decimal` -> wei, bukan float mentah.
- Gas EIP-1559 dulu, fallback legacy kalau tidak didukung.
- `daily_usage.json` ditulis atomik + lock, JSON rusak tidak crash.
- Hapus variabel tak terpakai di `/wallet/address`, tambah `/health`.
- Signer default jalan di `127.0.0.1` saja, bukan `0.0.0.0`.

## Yang dilengkapi

- `bot.py`: bot Telegram polling, hanya untuk `ALLOWED_TELEGRAM_USER_ID`.
  Perintah: `/start`, `/address`, `/balance <chain>`, `/transfer <chain> <alamat> <jumlah>`.
  Transfer wajib 2 langkah: perintah -> tombol konfirmasi Ya/Batal -> baru
  bot memanggil signer dengan `confirm=true`.
- `requirements.txt`, `.env.example`, dan panduan ini.
- Transfer di sini HANYA native (ETH/BNB/dll), bukan swap, mint, atau approve token.
  Limit default: max 0.01 per transaksi, max 0.02 per hari, dalam satuan native.

## Import wallet sendiri (bukan buat baru)

JANGAN kirim private key lewat Telegram, chat Muse, screenshot, atau file.
JANGAN tambah perintah import di bot Telegram.

Cara aman (di terminal server signer, signer sudah jalan):
```
python3 import_wallet.py
```
Script itu minta key lewat `getpass` (tidak tampil, tidak masuk history),
kirim HANYA ke `http://127.0.0.1:8000/wallet/import`, lalu hapus key dari
memori. Server mengenkripsi key ke `keystore.json` (chmod 0600) dan hanya
mengembalikan alamat wallet, tidak pernah mengembalikan key.

Aturan import:
- Ditolak kalau `keystore.json` sudah ada (409). Backup + hapus dulu kalau
  memang mau ganti wallet.
- Key tidak valid ditolak (400), key tidak pernah di-log.
- Pakai dompet khusus bot dengan saldo kecil dulu untuk tes, bukan dompet utama.

## Sambungan Apps Script DWEAIBOT -> Python signer (bisa signer sendiri)

BISA. Arsitekturnya:
```
Telegram -> Apps Script DWEAIBOT (webhook)
         -> HTTPS -> Python signer (main.py)
         -> onchain (transfer native)
```
- Apps Script TIDAK pegang private key. Dia hanya pegang `SIGNER_API_SECRET`
  di Script Properties, dan memanggil signer.
- Private key hanya di signer, terenkripsi di `keystore.json`.
- Transfer di Apps Script juga 2 langkah: `/transfer ...` -> bot minta
  balas `YA_KIRIM` dalam 5 menit -> baru panggil signer `confirm=true`.
  Lihat [appsscript-connector.gs](sandbox://workspace/dweaibot-signer/appsscript-connector.gs).
- Isi di Script Properties Apps Script: `SIGNER_URL` (https publik),
  `SIGNER_API_SECRET` (sama dengan .env signer), dan `OWNER_CHAT_ID`
  (sangat disarankan, supaya transfer hanya owner).
- SYARAT PENTING: Apps Script jalan di server Google, jadi TIDAK BISA
  memanggil `127.0.0.1`. Signer harus di VPS / server publik lewat https,
  atau tunnel sementara untuk tes. Kalau signer masih localhost, konektor
  akan gagal - itu normal, bukan bug Apps Script.
- Jangan jalankan bot Python polling (`bot.py`) dan bot Apps Script webhook
  pakai token Telegram yang sama sekaligus. Pilih satu front-end Telegram:
  Apps Script webhook ATAU Python polling, signer-nya sama.

## Tanpa VPS / domain, tetap bisa jalan dan tidak bocor

BISA, asal pakai bot Python polling, BUKAN Apps Script webhook.

Kenapa polling aman tanpa domain:
- Bot polling yang aktif mengambil update dari Telegram (koneksi keluar).
  Bot tidak butuh domain, tidak butuh port inbound, dan Telegram tidak
  pernah memanggil server kamu.
- Signer + bot jalan di SATU host yang sama (laptop kamu, atau host gratis
  sebagai worker). Signer hanya di `127.0.0.1:8000`, tidak diekspos ke internet.
- Jadi tidak ada URL signer publik yang bisa ditebak / diserang orang luar.

Jalankan keduanya sekaligus:
```
python3 run_all.py
```
Script ini mengecek `.env` dulu, menyalakan signer localhost, menunggu
`/health`, baru menyalakan bot polling. Ctrl+C mematikan keduanya.

Pilihan host tanpa beli VPS/domain:
1. **Laptop/PC kamu sendiri** - paling aman dari sisi bocor, tapi bot hanya
   jalan selama laptop hidup dan script jalan.
2. **Host gratis sebagai worker** (Render/Railway/Fly/dll, pakai Dockerfile
   di folder ini) - host kasih subdomain gratis, tapi bot polling tidak
   butuh subdomain itu untuk inbound. Isi secret lewat Environment Variables
   di dashboard host, JANGAN di kode / image. Catatan: tier gratis bisa
   tidur / restart, jadi bot tidak dijamin 24 jam penuh.
3. **Di VM Muse ini sementara untuk tes** - bisa, tapi proses tidak dijamin
   hidup terus setelah VM restart/replacement. Cocok untuk tes, bukan produksi.

Yang bikin bocor (hindari):
- Private key di Telegram/chat/screenshot/file/.env yang di-commit.
- Signer dibuka ke `0.0.0.0` / internet tanpa TLS.
- Secret / token ditulis langsung di kode atau di Apps Script yang dibagikan.
- Wallet utama dipakai bot. Pakai dompet khusus bot, saldo kecil dulu.

Catatan: kalau tetap mau front-end Apps Script webhook, signer HARUS publik
https, jadi opsi tanpa VPS/domain di atas tidak berlaku untuk Apps Script.
Pilih: Apps Script webhook (butuh signer publik) ATAU Python polling
(tidak butuh domain, signer localhost).

## Yang BELUM jalan / belum dibuat

- Wallet signer BELUM dibuat (`keystore.json` belum ada).
- Bot Telegram BELUM live, karena `TELEGRAM_TOKEN`, RPC, dan secret di `.env`
  belum diisi.
- Tidak ada dana di wallet ini sampai kamu isi sendiri dari dompet lain,
  dengan jumlah kecil dulu untuk tes.

## Cara jalan lokal (tes, tanpa dana)

1. Buat venv dan install:
   ```
   python3 -m venv .venv
   .venv/bin/pip install -r requirements.txt
   ```
2. Salin `.env.example` jadi `.env`, isi secret/RPC/token di server itu sendiri.
   Jangan commit `.env`, jangan kirim isinya ke chat.
3. Terminal 1 - signer:
   ```
   .venv/bin/python main.py
   ```
   Cek: `curl http://127.0.0.1:8000/` -> `{"bot":"DWEAIBOT","status":"online"}`
4. Terminal 2 - bot (setelah signer jalan):
   ```
   .venv/bin/python bot.py
   ```
5. Di Telegram, chat bot kamu sendiri: `/start`, lalu `/address`.
   Kalau wallet belum ada, buat wallet HANYA setelah `.env` lengkap, lewat API
   signer dengan header Authorization, misal dari terminal yang sama:
   ```
   curl -X POST http://127.0.0.1:8000/wallet/create -H "Authorization: Bearer <SIGNER_API_SECRET>"
   ```
   Alamat yang dikembalikan itu alamat wallet bot. Backup `keystore.json`
   + `KEYSTORE_PASSWORD` secara terpisah. Private key tidak pernah ditampilkan.
   Kalau keduanya hilang, dana di wallet itu tidak bisa dipulihkan - akun ini
   dibuat acak, bukan dari mnemonic.

## Catatan keamanan penting

- Jangan ekspos signer ke internet tanpa TLS + firewall. Desain ini memang
  signer localhost, bot yang jadi satu-satunya pemanggil.
- Limit di atas dalam native, bukan USD. 0.01 ETH, 0.01 BNB, dan 0.01 MATIC
  nilainya beda jauh. Turunkan limit kalau perlu, atau isi hanya chain yang dipakai.
- Daily limit menghitung jumlah transfer, belum termasuk gas. Siapkan saldo
  ekstra untuk gas di luar limit itu.
- Bot ini BUKAN Rensheen Apps Script. Rensheen tetap proyek terpisah di
  Google Apps Script; DWEAIBOT ini proyek Python terpisah.
- Untuk jalan 24 jam permanen butuh host yang selalu hidup (VPS / server
  sendiri) + proses yang diawasi (misal systemd). VM ini bisa dipakai tes,
  tapi prosesnya tidak dijamin hidup terus setelah restart/replacement.
