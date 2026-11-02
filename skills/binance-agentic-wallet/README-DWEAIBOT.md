# Binance Agentic Wallet skill (vendored, read-only reference)

This folder is a copy of the upstream Binance skill
`binance-agentic-wallet` from
https://github.com/binance/binance-skills-hub
(path `skills/binance-web3/binance-agentic-wallet`),
vendored here on 2026-11-02.

- Upstream commit at vendoring:
  `96563daf34fa5a87af5d76c2f1107d697ae7ce07`
- Skill version: `1.15.0`
- Required CLI version: `1.12.0`
  (`npm install -g @binance/agentic-wallet@1.12.0`, package `baw`)
- Contents: `SKILL.md`, `references/` (19 files), `scripts/`.

## This is NOT the DWEAIBOT Telegram bot

The Telegram bot in this repo (`bot.py` + `main.py`) is unchanged by
adding this folder. It still uses its own local Python signer with an
encrypted keystore, native transfers only, and its own limits.

The Binance skill is a separate wallet system:

- It drives the `baw` CLI against a Binance Web3 / Agentic Wallet
  in the Binance App (sign-in by QR / pairing code in the app).
- It supports balance, token transfers, DEX market/limit orders,
  approvals, DeFi, prediction markets, x402 payments, and
  contract-call / sign-message (the last two need Developer Mode
  enabled in the Binance App).
- Supported chains (from `baw wallet chains`): Base, BNB Smart
  Chain, Ethereum, Polygon, Robinhood, Solana, Arbitrum One.
  opBNB is not in that list.

Do not mix the two wallets: different addresses, balances, limits,
and sessions. A Binance session is temporary (sign-in again after
it expires) and is never stored in this repo.

## No secrets in this folder

No Telegram token, signer secret, keystore password, private key,
seed phrase, session token, or API key is included here, and none
should ever be added. Sign-in happens only in the Binance App.
The contract addresses in `SKILL.md` are public token addresses
from the upstream skill, not user wallets.

## Quick start (agent side)

1. Install the CLI: `npm install -g @binance/agentic-wallet@1.12.0`
2. Preflight: `baw skill-check --skill-name binance-agentic-wallet
   --current-version 1.15.0 --json`, then
   `baw cli-check --required-version 1.12.0 --json`, then
   `baw wallet status --json`.
3. If `UNCONNECTED`, sign in first:
   `baw auth signin --json` (show the pairing code verbatim),
   confirm in the Binance App, then
   `baw auth verify --qrCodeId <id> --json`.
4. Confirm every state-changing action with the user before
   running it. Never ask for or store a seed phrase or private key.
