# 🤖 Forex AI Telegram Bot & Automated Setup Dispatch Guide

This guide walks you through setting up and using the **Forex AI Institutional Telegram Bot**.

The bot is specialized for **Gold (`XAUUSD`)** and **Silver (`XAGUSD`)** institutional SMC/ICT setups, and connects directly to your live Railway cloud deployment:
👉 `https://forex-ai-backend-production.up.railway.app`

---

## 🌟 What This Bot Does

1. **🔔 Automated High-Probability Setup Alerts (Push):**
   - The 24/7 background session scanner continuously monitors Deriv institutional tick data.
   - When a **`VALID_SETUP`** or **`POTENTIAL_SETUP`** is confirmed during London or New York sessions (MSS with displacement, Asian liquidity sweeps, and FVG retests), the bot immediately fires a detailed alert to your Telegram.
   - Built-in **15-minute anti-spam cooldown** ensures you only get clean, actionable signals.

2. **💬 On-Demand Interactive Slash Commands:**
   - Chat with the bot in Telegram anytime to query live market structure on demand:
   - `/gold` or `/xau` — Instant institutional 15m analysis & key levels for **Gold (XAUUSD)**
   - `/silver` or `/xag` — Instant institutional 15m analysis & key levels for **Silver (XAGUSD)**
   - `/setups` — Scans for active setups across all metals right now
   - `/session` — Checks active Forex session (Asian, London Killzone, NY Killzone) & dealing ranges
   - `/p <symbol>` — Analyze any instrument on-demand (e.g., `/p EURUSD`, `/p GBPUSD`)
   - `/status` — Checks server health, WebSocket feed, and scanner status
   - `/help` — Full command list and overview

---

## ⚙️ Step 1: Environment Variables in Railway

In your [Railway](https://railway.app/) Dashboard › **Backend Service** › **Variables** tab (or `.env` locally):

```env
# ==============================================================================
# Telegram Bot Configuration
# ==============================================================================
TELEGRAM_BOT_TOKEN=8700189214:AAFeWR_dx5WbKFU23KmNoLg8ydWe1qHNZ3w
TELEGRAM_CHAT_ID=1319345715

# Enable Telegram setup alerts (true/false)
TELEGRAM_ENABLED=True

# Target pairs to alert (focused on Metals)
TELEGRAM_TARGET_PAIRS=["XAUUSD", "XAGUSD"]

# Setup eligibility filters
TELEGRAM_NOTIFY_ON_VALID_SETUP=True
TELEGRAM_NOTIFY_ON_POTENTIAL_SETUP=True
```

---

## 🚀 Step 2: How It Runs

Because the Telegram Bot listener is integrated directly into the FastAPI application lifespan, **no extra scripts or second terminals are required!**

When your Railway backend boots:
1. Deriv market ingestion supervisor starts.
2. Continuous 24/7 session scanner starts.
3. Interactive Telegram Bot listener starts automatically.

---

## 💬 Step 3: Telegram Commands Reference

Open your bot (`@my_crypto_perps_scanner_bot` or your custom bot) on Telegram and use:

| Command | Description | Example |
| :--- | :--- | :--- |
| `/gold` or `/xau` | 🥇 Live institutional 15m SMC/ICT structure for Gold | `/gold` |
| `/silver` or `/xag` | 🥈 Live institutional 15m SMC/ICT structure for Silver | `/silver` |
| `/setups` | 🎯 Scan metals for active high-probability setups right now | `/setups` |
| `/session` | 🏛 Active trading session (Asia, London Killzone, NY Killzone) | `/session` |
| `/p <symbol>` | 📊 On-demand institutional analysis for any pair | `/p EURUSD` |
| `/status` | ⚡ Live backend uptime, Deriv connection, and scanner health | `/status` |
| `/help` | 📖 Help menu and quick command guide | `/help` |

---

## 🔔 Step 4: Sample Alert Format

Whenever the background engine detects a confirmed setup, it delivers:

```text
🟢 🎯 CONFIRMED VALID SETUP
🥇 GOLD (XAU/USD) | ⏱ 15M | 🏛 LONDON KILLZONE

💡 Institutional Narrative:
Bullish Market Structure Shift (MSS) with displacement following liquidity 
sweep of Asian session low. Price entered high-probability Bullish Fair Value Gap (FVG).

📋 Strategy Checklist:
✅ Asian Liquidity Sweep (Swept Asian session low with rejection)
✅ Market Structure Shift (MSS) (Displacement candle broke swing high with body close)
✅ PD Array (FVG / OB Retest) (15m FVG mitigated with zero invalidation)
✅ Session Killzone Timing (London Killzone 08:00 - 11:00 UTC)

⏰ Timestamp: 2026-10-09 14:30:00 UTC
🤖 Forex AI Institutional Execution Engine
```

---

## 🌐 Step 5: Test Via REST API

You can also trigger test alerts programmatically anytime via your live Railway endpoint:

- **Send Test Gold Alert:**
  ```bash
  curl -X POST "https://forex-ai-backend-production.up.railway.app/api/v1/telegram/test-setup?symbol=XAUUSD"
  ```
- **Send Test Silver Alert:**
  ```bash
  curl -X POST "https://forex-ai-backend-production.up.railway.app/api/v1/telegram/test-setup?symbol=XAGUSD"
  ```
- **Check Bot Status:**
  ```bash
  curl "https://forex-ai-backend-production.up.railway.app/api/v1/telegram/status"
  ```
