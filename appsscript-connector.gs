/**
 * DWEAIBOT - Konektor Apps Script -> Python Signer
 *
 * CARA PASANG (di proyek Apps Script DWEAIBOT, BUKAN di telegram ai bot):
 * 1. Salin file ini jadi file baru di proyek Apps Script, misal Signer.gs.
 * 2. Di Project Settings > Script Properties, tambah (HANYA nama + nilai di sana,
 *    JANGAN tulis nilainya di kode ini):
 *      SIGNER_URL         = https://domain-signer-kamu...  (HARUS https, tanpa / di akhir)
 *      SIGNER_API_SECRET  = secret yang sama dengan .env signer
 *      OWNER_CHAT_ID      = (opsional tapi SANGAT disarankan) ID Telegram kamu, angka saja
 * 3. JANGAN taruh private key di Script Properties, di kode, atau di chat Telegram.
 *    Private key HANYA ada di signer Python, terenkripsi di keystore.json.
 *    Apps Script di sini HANYA pegang SIGNER_API_SECRET, bukan private key.
 *
 * KENAPA HARUS https PUBLIK:
 * Apps Script jalan di server Google, jadi dia TIDAK BISA memanggil
 * http://127.0.0.1:8000 di komputermu. Signer Python harus jalan di VPS /
 * server yang bisa diakses internet lewat https (atau tunnel sementara
 * untuk tes, misal Cloudflare Tunnel / ngrok, dengan secret yang kuat).
 * Kalau SIGNER_URL masih localhost, fungsi di bawah akan gagal - itu normal.
 *
 * ALUR TRANSFER (tetap 2 langkah, walau SAFE MODE dimatikan di API):
 *   User: /transfer ethereum 0xAbc... 0.005
 *   Bot : ringkasan + "Balas YA_KIRIM dalam 5 menit untuk konfirmasi, atau BATAL"
 *   User: YA_KIRIM
 *   Bot : panggil signer dengan confirm=true -> balas tx_hash
 *   User lain / bukan owner (kalau OWNER_CHAT_ID diisi) -> ditolak.
 *
 * Fungsi-fungsi di bawah ini contoh integrasi. Sesuaikan nama fungsi
 * pengirim pesan Telegram di proyekmu (di sini dipakai sendTelegram_
 * sebagai placeholder - ganti dengan fungsi kirim yang sudah ada di Kode.gs
 * kalau namanya beda, misal sendMessage).
 */

// ---------- Panggilan dasar ke signer ----------

function signerProps_() {
  var p = PropertiesService.getScriptProperties();
  return {
    url: p.getProperty('SIGNER_URL'),
    secret: p.getProperty('SIGNER_API_SECRET'),
    ownerId: p.getProperty('OWNER_CHAT_ID')
  };
}

function signerCall_(method, path, payload) {
  var cfg = signerProps_();
  if (!cfg.url || !cfg.secret) {
    throw new Error('SIGNER_URL / SIGNER_API_SECRET belum diatur di Script Properties');
  }
  var options = {
    method: method,
    headers: { 'Authorization': 'Bearer ' + cfg.secret, 'Content-Type': 'application/json' },
    muteHttpExceptions: true
  };
  if (payload) options.payload = JSON.stringify(payload);
  var res = UrlFetchApp.fetch(cfg.url + path, options);
  var code = res.getResponseCode();
  var text = res.getContentText();
  var data = {};
  try { data = JSON.parse(text); } catch (e) { data = { raw: text }; }
  if (code < 200 || code >= 300) {
    throw new Error('Signer error ' + code + ': ' + (data.detail || text).toString().slice(0, 300));
  }
  return data;
}

function signerGetAddress_() {
  return signerCall_('get', '/wallet/address').address;
}

function signerGetBalance_(chain) {
  var d = signerCall_('get', '/balance/' + encodeURIComponent(chain.toLowerCase()));
  return d.chain + ': ' + d.balance_native + ' native\nAlamat: ' + d.address;
}

function signerTransfer_(chain, to, amount) {
  // confirm=true HANYA dipanggil dari handleSignerConfirm_() setelah user
  // mengetik YA_KIRIM, bukan langsung dari /transfer.
  return signerCall_('post', '/transfer/native', {
    chain: chain.toLowerCase(),
    to: to,
    amount: Number(amount),
    confirm: true
  });
}

function signerHealth_() {
  return signerCall_('get', '/health');
}

// ---------- Contoh perintah Telegram untuk Apps Script ----------
// Panggil fungsi-fungsi ini dari router pesan di Kode.gs / doPost yang sudah ada.
// Contoh: kalau teks diawali '/transfer', panggil handleSignerTransfer_(chatId, teks)
// Kalau teks == 'YA_KIRIM' atau 'BATAL', panggil handleSignerConfirm_(chatId, teks)

function isSignerOwner_(chatId) {
  var owner = signerProps_().ownerId;
  if (!owner) return true; // kalau OWNER_CHAT_ID kosong, semua user bisa - TIDAK DISARANKAN
  return String(chatId) === String(owner);
}

function handleSignerTransfer_(chatId, text) {
  // Format: /transfer <chain> <alamat> <jumlah>
  var parts = text.trim().split(/\s+/);
  if (!isSignerOwner_(chatId)) {
    sendTelegram_(chatId, 'Perintah transfer hanya untuk owner.');
    return;
  }
  if (parts.length !== 4) {
    sendTelegram_(chatId, 'Pakai: /transfer <chain> <alamat> <jumlah>\nContoh: /transfer ethereum 0xAbc... 0.005');
    return;
  }
  var chain = parts[1].toLowerCase();
  var to = parts[2];
  var amount = Number(parts[3]);
  if (!(amount > 0)) {
    sendTelegram_(chatId, 'Jumlah tidak valid.');
    return;
  }
  var pending = { chain: chain, to: to, amount: amount };
  CacheService.getScriptCache().put(
    'pending_transfer_' + chatId,
    JSON.stringify(pending),
    300 // 5 menit
  );
  sendTelegram_(chatId,
    'Konfirmasi transfer:\nChain: ' + chain +
    '\nKe: ' + to +
    '\nJumlah: ' + amount + ' native' +
    '\n\nBalas YA_KIRIM dalam 5 menit untuk kirim, atau BATAL untuk batalkan.' +
    '\nLimit ikut signer (default max 0.01 / hari 0.02 native).');
}

function handleSignerConfirm_(chatId, text) {
  var cache = CacheService.getScriptCache();
  var key = 'pending_transfer_' + chatId;
  var raw = cache.get(key);
  if (text === 'BATAL') {
    cache.remove(key);
    sendTelegram_(chatId, 'Transfer dibatalkan.');
    return;
  }
  if (text !== 'YA_KIRIM' || !raw) {
    return; // bukan konfirmasi transfer, biarkan router lain yang handle
  }
  if (!isSignerOwner_(chatId)) {
    sendTelegram_(chatId, 'Perintah transfer hanya untuk owner.');
    return;
  }
  cache.remove(key);
  var p = JSON.parse(raw);
  sendTelegram_(chatId, 'Mengirim... tunggu konfirmasi on-chain.');
  try {
    var res = signerTransfer_(p.chain, p.to, p.amount);
    sendTelegram_(chatId, 'Terkirim (submitted).\nChain: ' + res.chain + '\nTx hash: ' + res.tx_hash +
      '\nCek status di explorer chain tersebut.');
  } catch (e) {
    sendTelegram_(chatId, 'Gagal kirim: ' + e.message);
  }
}

// Placeholder: ganti dengan fungsi kirim Telegram yang sudah ada di proyekmu
// kalau namanya berbeda. Jangan hapus fungsi ini sebelum diganti, supaya
// file ini tidak error saat dites terpisah.
function sendTelegram_(chatId, text) {
  // TODO: panggil fungsi kirim yang sudah ada di Kode.gs, misal:
  // return sendMessage(chatId, text);
  throw new Error('Hubungkan sendTelegram_() ke fungsi kirim Telegram di Kode.gs dulu');
}
