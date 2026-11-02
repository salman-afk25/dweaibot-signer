"""
DWEAIBOT Telegram bot - pelengkap signer (main.py).

Arsitektur yang aman:
- Bot ini HANYA bicara ke signer lewat localhost (default 127.0.0.1:8000).
  Signer TIDAK diekspos ke internet.
- Bot HANYA melayani satu owner: ALLOWED_TELEGRAM_USER_ID.
  User lain ditolak tanpa info saldo / alamat.
- Transfer WAJIB 2 langkah di Telegram:
  1. /transfer <chain> <alamat> <jumlah>
  2. Bot tampilkan ringkasan + tombol Ya / Batal, baru kalau Ya ditekan
     bot memanggil signer dengan confirm=true.
  Jadi "matikan SAFE MODE" di level API tidak berarti transfer jalan
  tanpa konfirmasi kamu di Telegram.
- Bot TIDAK PERNAH menampilkan / meminta private key, seed phrase,
  SIGNER_API_SECRET, atau TELEGRAM_TOKEN di chat.

Jalankan SETELAH signer jalan:
  python3 main.py        # terminal 1, localhost:8000
  python3 bot.py         # terminal 2, polling Telegram

Chain yang didukung signer: ethereum, bsc, base, polygon, arbitrum.
Transfer di sini HANYA native (ETH/BNB/MATIC-dll), bukan swap/mint.
Limit ikut signer: default max 0.01 / hari 0.02 native (lihat .env).
"""
import os
import uuid
from decimal import Decimal

import httpx
from dotenv import load_dotenv
from telegram import BotCommand, InlineKeyboardButton, InlineKeyboardMarkup, Update
from telegram.ext import (
    Application,
    CallbackQueryHandler,
    CommandHandler,
    ContextTypes,
)

load_dotenv()

TELEGRAM_TOKEN = os.getenv("TELEGRAM_TOKEN", "")
ALLOWED_USER_ID = os.getenv("ALLOWED_TELEGRAM_USER_ID", "")
SIGNER_URL = os.getenv("SIGNER_API_URL", "http://127.0.0.1:8000").rstrip("/")
SIGNER_SECRET = os.getenv("SIGNER_API_SECRET", "")

# pending[user_id] = {id, chain, to, amount}
pending = {}


def is_owner(update: Update) -> bool:
    user = update.effective_user
    return bool(user and ALLOWED_USER_ID and str(user.id) == str(ALLOWED_USER_ID))


async def reject_if_not_owner(update: Update) -> bool:
    if not is_owner(update):
        if update.message:
            await update.message.reply_text("Bukan untuk user ini.")
        return True
    return False


def signer_headers():
    return {"Authorization": f"Bearer {SIGNER_SECRET}"}


async def signer_get(path: str):
    # trust_env=False: panggilan ke signer localhost tidak boleh lewat proxy
    # dan tidak boleh gagal karena variabel proxy/no_proxy di host.
    async with httpx.AsyncClient(timeout=20, trust_env=False) as client:
        r = await client.get(f"{SIGNER_URL}{path}", headers=signer_headers())
    return r


async def signer_post(path: str, payload: dict):
    async with httpx.AsyncClient(timeout=30, trust_env=False) as client:
        r = await client.post(f"{SIGNER_URL}{path}", json=payload, headers=signer_headers())
    return r


async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if await reject_if_not_owner(update):
        return
    await update.message.reply_text(
        "DWEAIBOT online.\n\n"
        "Semua perintah:\n"
        "/start - tampilkan daftar perintah ini\n"
        "/help - tampilkan daftar perintah ini\n"
        "/createwallet - buat wallet bot baru (hanya kalau belum ada, tanpa kirim key)\n"
        "/address - lihat alamat wallet signer\n"
        "/balance <chain> - cek saldo, contoh: /balance ethereum\n"
        "/transfer <chain> <alamat> <jumlah> - transfer native, contoh: /transfer ethereum 0xAbc... 0.005\n\n"
        "Transfer itu 2 langkah: kirim /transfer, lalu tekan tombol Ya, kirim (atau Batal) yang muncul. "
        "Tanpa tombol Ya, transfer tidak dikirim.\n\n"
        "Chain: ethereum, bsc, base, polygon, arbitrum\n"
        "Transfer hanya native (ETH/BNB/dll), bukan swap/mint.\n"
        "Limit default signer: max 0.01 / hari 0.02 native (bukan USD).\n"
        "Bot ini owner-only dan tidak pernah meminta private key / seed phrase di chat."
    )


async def help_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await start(update, context)


async def createwallet(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if await reject_if_not_owner(update):
        return
    r = await signer_post("/wallet/create", {})
    if r.status_code == 409:
        await update.message.reply_text("Wallet sudah ada. Pakai /address untuk lihat alamatnya.")
        return
    if r.status_code != 200:
        await update.message.reply_text(f"Gagal buat wallet: {r.status_code} {r.text[:200]}")
        return
    await update.message.reply_text(
        f"Wallet bot baru dibuat.\nAlamat: {r.json().get('address')}\n\n"
        "Ini dompet khusus bot, bukan dompet utama kamu. "
        "Kirim saldo kecil dulu dari dompet utama kamu ke alamat ini untuk tes, "
        "jangan kirim private key apa pun lewat chat."
    )


async def address(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if await reject_if_not_owner(update):
        return
    r = await signer_get("/wallet/address")
    if r.status_code == 404:
        await update.message.reply_text("Wallet belum dibuat. Buat dulu lewat signer (/wallet/create), lalu coba lagi.")
        return
    if r.status_code != 200:
        await update.message.reply_text(f"Gagal ambil alamat: {r.status_code} {r.text[:200]}")
        return
    await update.message.reply_text(f"Alamat wallet:\n{r.json().get('address')}")


async def balance(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if await reject_if_not_owner(update):
        return
    if not context.args:
        await update.message.reply_text("Pakai: /balance <chain>\nContoh: /balance ethereum")
        return
    chain = context.args[0].lower()
    r = await signer_get(f"/balance/{chain}")
    if r.status_code != 200:
        await update.message.reply_text(f"Gagal cek saldo: {r.status_code} {r.text[:200]}")
        return
    d = r.json()
    await update.message.reply_text(
        f"Chain: {d.get('chain')}\nAlamat: {d.get('address')}\nSaldo: {d.get('balance_native')} native"
    )


async def transfer(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if await reject_if_not_owner(update):
        return
    if len(context.args) != 3:
        await update.message.reply_text(
            "Pakai: /transfer <chain> <alamat> <jumlah>\nContoh: /transfer ethereum 0xAbc... 0.005"
        )
        return
    chain, to, amount_str = context.args[0].lower(), context.args[1], context.args[2]
    try:
        amount = Decimal(amount_str)
        if amount <= 0:
            raise ValueError
    except Exception:
        await update.message.reply_text("Jumlah tidak valid. Contoh: 0.005")
        return
    tid = uuid.uuid4().hex[:12]
    pending[str(update.effective_user.id)] = {"id": tid, "chain": chain, "to": to, "amount": str(amount)}
    keyboard = [[
        InlineKeyboardButton("✅ Ya, kirim", callback_data=f"confirm:{tid}"),
        InlineKeyboardButton("❌ Batal", callback_data=f"cancel:{tid}"),
    ]]
    await update.message.reply_text(
        f"Konfirmasi transfer:\nChain: {chain}\nKe: {to}\nJumlah: {amount} native\n\n"
        "Tekan Ya kalau benar. Kalau salah, tekan Batal.",
        reply_markup=InlineKeyboardMarkup(keyboard),
    )


async def on_button(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    if not is_owner(update):
        await query.edit_message_text("Bukan untuk user ini.")
        return
    data = query.data or ""
    action, _, tid = data.partition(":")
    item = pending.get(str(update.effective_user.id))
    if not item or item["id"] != tid:
        await query.edit_message_text("Permintaan ini sudah kedaluwarsa / dibatalkan. Kirim /transfer lagi.")
        return
    if action == "cancel":
        pending.pop(str(update.effective_user.id), None)
        await query.edit_message_text("Transfer dibatalkan.")
        return
    if action != "confirm":
        return
    pending.pop(str(update.effective_user.id), None)
    await query.edit_message_text("Mengirim... tunggu konfirmasi on-chain.")
    r = await signer_post("/transfer/native", {
        "chain": item["chain"],
        "to": item["to"],
        "amount": float(item["amount"]),
        "confirm": True,
    })
    if r.status_code != 200:
        await query.message.reply_text(f"Gagal kirim: {r.status_code} {r.text[:300]}")
        return
    d = r.json()
    await query.message.reply_text(
        f"✅ Terkirim (submitted).\nChain: {d.get('chain')}\nTx hash: {d.get('tx_hash')}\n"
        "Cek status di explorer chain tersebut. Laporan ini bukan jaminan final."
    )


async def post_init(app: Application):
    # Daftarkan daftar perintah ke Telegram, supaya saat mengetik "/"
    # di kolom chat, semua perintah muncul sebagai menu autocomplete.
    await app.bot.set_my_commands([
        BotCommand("start", "Tampilkan semua perintah"),
        BotCommand("help", "Tampilkan semua perintah"),
        BotCommand("createwallet", "Buat wallet bot baru"),
        BotCommand("address", "Lihat alamat wallet signer"),
        BotCommand("balance", "Cek saldo: /balance <chain>"),
        BotCommand("transfer", "Transfer native: /transfer <chain> <alamat> <jumlah>"),
    ])


def main():
    if not TELEGRAM_TOKEN:
        raise SystemExit("TELEGRAM_TOKEN belum diatur di .env")
    if not ALLOWED_USER_ID:
        raise SystemExit("ALLOWED_TELEGRAM_USER_ID belum diatur di .env")
    if not SIGNER_SECRET:
        raise SystemExit("SIGNER_API_SECRET belum diatur di .env")
    app = Application.builder().token(TELEGRAM_TOKEN).post_init(post_init).build()
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("help", help_cmd))
    app.add_handler(CommandHandler("createwallet", createwallet))
    app.add_handler(CommandHandler("address", address))
    app.add_handler(CommandHandler("balance", balance))
    app.add_handler(CommandHandler("transfer", transfer))
    app.add_handler(CallbackQueryHandler(on_button))
    print("DWEAIBOT Telegram polling jalan. Owner-only, signer di", SIGNER_URL)
    app.run_polling()


if __name__ == "__main__":
    main()
