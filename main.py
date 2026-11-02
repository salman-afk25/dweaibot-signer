"""
DWEAIBOT Python Signer - versi diperbaiki.

Perubahan dari kode asli user (tetap menjaga endpoint & limit asli):
- Auth menerima "Bearer <secret>" maupun secret mentah, agar tidak gagal
  hanya karena format header.
- Amount tidak lagi dihitung pakai float mentah: dikonversi lewat Decimal
  ke wei, supaya 0.01 dst tidak meleset karena presisi float.
- Gas: coba EIP-1559 (maxFeePerGas/maxPriorityFeePerGas) dulu, fallback
  ke gasPrice legacy kalau chain/RPC tidak mendukung.
- daily_usage.json ditulis atomik (tmp + replace) + lock, dan JSON rusak
  tidak membuat server crash - dianggap 0 untuk hari itu.
- /wallet/address: hapus variabel tak terpakai.
- Tambah /health, dan __main__ yang mengikat ke 127.0.0.1 saja secara
  default. Signer ini dirancang DIPANGGIL LOKAL oleh bot Telegram,
  BUKAN diekspos langsung ke internet.

Keamanan yang dipertahankan dari kode asli:
- Private key TIDAK PERNAH ditampilkan. Wallet dibuat acak, dienkripsi
  dengan KEYSTORE_PASSWORD ke keystore.json (chmod 0o600).
- Transfer native saja (bukan swap/mint/approve token).
- Wajib confirm=true, alamat valid, amount > 0,
  max per transaksi dan max harian (default 0.01 / 0.02 native).
- Semua endpoint kecuali / dan /health wajib API_SECRET.
- Tanpa API_SECRET, semua endpoint terproteksi akan 401.
"""
import os
import json
import secrets
import threading
from datetime import date
from decimal import Decimal, InvalidOperation
from pathlib import Path

from fastapi import FastAPI, HTTPException, Header
from pydantic import BaseModel
from web3 import Web3
from eth_account import Account
from dotenv import load_dotenv

load_dotenv()

app = FastAPI(title="DWEAIBOT Python Signer")

API_SECRET = os.getenv("SIGNER_API_SECRET", "")
KEYSTORE_PASSWORD = os.getenv("KEYSTORE_PASSWORD", "")
KEYSTORE_FILE = Path("keystore.json")
DAILY_USAGE_FILE = Path("daily_usage.json")
_usage_lock = threading.Lock()

MAX_TX_NATIVE = Decimal(os.getenv("MAX_TX_NATIVE", "0.01"))
DAILY_LIMIT_NATIVE = Decimal(os.getenv("DAILY_LIMIT_NATIVE", "0.02"))

CHAINS = {
    "ethereum": {"chain_id": 1, "rpc": os.getenv("ETH_RPC", "")},
    "bsc": {"chain_id": 56, "rpc": os.getenv("BSC_RPC", "")},
    "base": {"chain_id": 8453, "rpc": os.getenv("BASE_RPC", "")},
    "polygon": {"chain_id": 137, "rpc": os.getenv("POLYGON_RPC", "")},
    "arbitrum": {"chain_id": 42161, "rpc": os.getenv("ARBITRUM_RPC", "")},
}

# Alias chain yang sering salah ketik / disingkat, dipetakan ke nama resmi.
# Termasuk "etherium" (typo umum untuk ethereum) yang sempat membuat
# /balance gagal 400 di live bot, padahal chain-nya sebenarnya tersedia.
CHAIN_ALIASES = {
    "eth": "ethereum",
    "etherium": "ethereum",
    "ethereum": "ethereum",
    "bnb": "bsc",
    "binance": "bsc",
    "bsc": "bsc",
    "matic": "polygon",
    "polygon": "polygon",
    "arb": "arbitrum",
    "arbitrum": "arbitrum",
    "base": "base",
}


def normalize_chain(chain: str) -> str:
    return CHAIN_ALIASES.get((chain or "").lower().strip(), (chain or "").lower().strip())


def authenticate(token):
    # Terima "Bearer <secret>" atau secret mentah.
    if token:
        token = token.strip()
        if token.lower().startswith("bearer "):
            token = token[7:].strip()
    if not API_SECRET or not secrets.compare_digest(token or "", API_SECRET):
        raise HTTPException(status_code=401, detail="Unauthorized")


def get_wallet():
    if not KEYSTORE_FILE.exists():
        raise HTTPException(status_code=404, detail="Wallet belum dibuat")
    try:
        return json.loads(KEYSTORE_FILE.read_text())
    except Exception:
        raise HTTPException(status_code=500, detail="Keystore rusak / tidak bisa dibaca")


def get_account():
    if not KEYSTORE_PASSWORD:
        raise HTTPException(status_code=500, detail="KEYSTORE_PASSWORD belum diatur")
    encrypted = get_wallet()
    try:
        private_key = Account.decrypt(encrypted, KEYSTORE_PASSWORD)
        return Account.from_key(private_key)
    except Exception:
        raise HTTPException(status_code=500, detail="Gagal membuka wallet")


def get_web3(chain):
    config = CHAINS.get(normalize_chain(chain))
    if not config or not config["rpc"]:
        raise HTTPException(status_code=400, detail="Chain atau RPC tidak tersedia")
    w3 = Web3(Web3.HTTPProvider(config["rpc"], request_kwargs={"timeout": 15}))
    if not w3.is_connected():
        raise HTTPException(status_code=503, detail="RPC tidak terhubung")
    return w3, config


def read_daily_usage():
    today = str(date.today())
    if not DAILY_USAGE_FILE.exists():
        return {"date": today, "total": Decimal("0")}
    try:
        data = json.loads(DAILY_USAGE_FILE.read_text())
    except Exception:
        return {"date": today, "total": Decimal("0")}
    if data.get("date") != today:
        return {"date": today, "total": Decimal("0")}
    try:
        return {"date": today, "total": Decimal(str(data.get("total", "0")))}
    except (InvalidOperation, ValueError):
        return {"date": today, "total": Decimal("0")}


def save_daily_usage(total: Decimal):
    # Tulis atomik agar file tidak setengah tertulis kalau proses mati.
    tmp = DAILY_USAGE_FILE.with_suffix(".tmp")
    tmp.write_text(json.dumps({"date": str(date.today()), "total": str(total)}))
    tmp.replace(DAILY_USAGE_FILE)


def gas_params(w3):
    """Kembalikan dict gas EIP-1559 kalau didukung, kalau tidak legacy."""
    try:
        priority = w3.eth.max_priority_fee
        latest = w3.eth.get_block("latest")
        base_fee = latest.get("baseFeePerGas") if isinstance(latest, dict) else getattr(latest, "baseFeePerGas", None)
        if priority is not None and base_fee is not None:
            max_fee = int(base_fee) * 2 + int(priority)
            return {"maxFeePerGas": max_fee, "maxPriorityFeePerGas": int(priority)}, max_fee
    except Exception:
        pass
    price = w3.eth.gas_price
    return {"gasPrice": price}, price


class TransferRequest(BaseModel):
    chain: str
    to: str
    amount: float
    confirm: bool = False


class ImportRequest(BaseModel):
    # HANYA untuk dipanggil dari localhost / CLI di server signer yang sama.
    # JANGAN kirim field ini lewat Telegram, chat Muse, atau API publik.
    # Server tidak pernah mengembalikan, me-log, atau menyimpan key ini
    # dalam bentuk plaintext: langsung dienkripsi ke keystore.json lalu
    # variabelnya dihapus.
    private_key: str


@app.get("/")
def home():
    return {"bot": "DWEAIBOT", "status": "online"}


@app.get("/health")
def health():
    return {
        "status": "ok",
        "wallet_exists": KEYSTORE_FILE.exists(),
        "chains_configured": [k for k, v in CHAINS.items() if v["rpc"]],
    }


@app.post("/wallet/create")
def create_wallet(authorization: str = Header(None)):
    authenticate(authorization)
    if KEYSTORE_FILE.exists():
        raise HTTPException(status_code=409, detail="Wallet sudah ada")
    if not KEYSTORE_PASSWORD:
        raise HTTPException(status_code=500, detail="Password keystore belum diatur")
    account = Account.create()
    encrypted = Account.encrypt(account.key, KEYSTORE_PASSWORD)
    KEYSTORE_FILE.write_text(json.dumps(encrypted))
    os.chmod(KEYSTORE_FILE, 0o600)
    # Sengaja: private key / mnemonic TIDAK dikembalikan.
    # Akun ini dibuat acak (bukan dari mnemonic), jadi backup = keystore.json
    # + KEYSTORE_PASSWORD yang disimpan terpisah. Kalau keduanya hilang, dana hilang.
    return {
        "status": "created",
        "address": account.address,
        "message": "Private key terenkripsi dan tidak ditampilkan. Backup keystore.json + passwordnya terpisah.",
    }


@app.post("/wallet/import")
def import_wallet(request: ImportRequest, authorization: str = Header(None)):
    authenticate(authorization)
    if KEYSTORE_FILE.exists():
        raise HTTPException(status_code=409, detail="Wallet sudah ada. Hapus keystore lama dulu kalau memang mau ganti (dan backup dulu).")
    if not KEYSTORE_PASSWORD:
        raise HTTPException(status_code=500, detail="Password keystore belum diatur")
    raw = (request.private_key or "").strip()
    if raw.lower().startswith("0x"):
        raw = raw[2:]
    try:
        if len(raw) != 64 or int(raw, 16) == 0:
            raise ValueError
        account = Account.from_key(raw)
        encrypted = Account.encrypt(account.key, KEYSTORE_PASSWORD)
    except Exception:
        raise HTTPException(status_code=400, detail="Private key tidak valid")
    finally:
        # Hapus dari memori secepatnya; jangan pernah log / kembalikan.
        raw = "0" * 64
        request.private_key = ""
    KEYSTORE_FILE.write_text(json.dumps(encrypted))
    os.chmod(KEYSTORE_FILE, 0o600)
    return {
        "status": "imported",
        "address": account.address,
        "message": "Private key terenkripsi ke keystore dan tidak ditampilkan / tidak disimpan plaintext.",
    }


@app.get("/wallet/address")
def wallet_address(authorization: str = Header(None)):
    authenticate(authorization)
    account = get_account()
    return {"address": account.address}


@app.get("/balance/{chain}")
def get_balance(chain: str, authorization: str = Header(None)):
    authenticate(authorization)
    account = get_account()
    w3, config = get_web3(chain)
    balance = w3.eth.get_balance(account.address)
    return {
        "chain": chain,
        "address": account.address,
        "balance_wei": str(balance),
        "balance_native": str(w3.from_wei(balance, "ether")),
    }


@app.post("/transfer/native")
def transfer_native(request: TransferRequest, authorization: str = Header(None)):
    authenticate(authorization)
    if not request.confirm:
        raise HTTPException(status_code=400, detail="Konfirmasi transaksi wajib")
    if not Web3.is_address(request.to):
        raise HTTPException(status_code=400, detail="Alamat tujuan tidak valid")
    try:
        amount = Decimal(str(request.amount))
    except (InvalidOperation, ValueError):
        raise HTTPException(status_code=400, detail="Jumlah tidak valid")
    if amount <= 0:
        raise HTTPException(status_code=400, detail="Jumlah harus lebih dari nol")
    if amount > MAX_TX_NATIVE:
        raise HTTPException(status_code=400, detail="Melebihi batas per transaksi")
    with _usage_lock:
        usage = read_daily_usage()
        if usage["total"] + amount > DAILY_LIMIT_NATIVE:
            raise HTTPException(status_code=400, detail="Melebihi batas harian")
        account = get_account()
        w3, config = get_web3(request.chain)
        balance = w3.eth.get_balance(account.address)
        value = int(amount * Decimal(10**18))
        if balance < value:
            raise HTTPException(status_code=400, detail="Saldo tidak mencukupi")
        nonce = w3.eth.get_transaction_count(account.address, "pending")
        gas_dict, gas_unit_price = gas_params(w3)
        gas_limit = 21000
        if balance < value + (gas_limit * gas_unit_price):
            raise HTTPException(status_code=400, detail="Saldo tidak cukup untuk biaya gas")
        tx = {
            "chainId": config["chain_id"],
            "nonce": nonce,
            "to": Web3.to_checksum_address(request.to),
            "value": value,
            "gas": gas_limit,
            **gas_dict,
        }
        signed = account.sign_transaction(tx)
        tx_hash = w3.eth.send_raw_transaction(signed.raw_transaction)
        save_daily_usage(usage["total"] + amount)
    return {"status": "submitted", "chain": request.chain, "tx_hash": tx_hash.hex()}


if __name__ == "__main__":
    import uvicorn

    # Sengaja localhost saja. Jangan ubah ke 0.0.0.0 tanpa TLS + firewall,
    # karena siapa pun yang bisa mencapai API ini + tahu secret bisa transfer.
    uvicorn.run(app, host="127.0.0.1", port=int(os.getenv("SIGNER_PORT", "8000")))
