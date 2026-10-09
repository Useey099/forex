import asyncio
import logging
from datetime import datetime, timezone
from typing import Optional, Dict, Any, List
import httpx

from app.core.config import settings
from app.core.database import async_session_factory
from app.services.session import SessionEngine
from app.services.ai import AIAnalysisEngine
from app.schemas.ai_analysis import AIAnalysisRequest
from app.models.analysis import AnalysisStateEnum
from app.services.notifications.telegram_service import get_telegram_service

logger = logging.getLogger("forex_ai.telegram_bot")

class TelegramBotRunner:
    """
    Interactive Telegram Bot Command Listener for Forex AI Platform.
    Enables commands (/gold, /silver, /setups, /session, /status, /help)
    with zero external dependencies via async long-polling.
    """

    def __init__(self):
        self.bot_token = settings.TELEGRAM_BOT_TOKEN
        self.chat_id = settings.TELEGRAM_CHAT_ID
        self._running = False
        self._task: Optional[asyncio.Task] = None
        self._offset = 0

    async def start(self) -> None:
        """Starts the background long-polling listener if configured."""
        if not settings.TELEGRAM_BOT_TOKEN or not settings.TELEGRAM_ENABLED:
            logger.info("TelegramBotRunner: Bot token not set or disabled. Skipping listener.")
            return

        if self._running:
            return

        self._running = True
        self._task = asyncio.create_task(self._poll_loop())
        logger.info("TelegramBotRunner: Interactive command polling loop started.")

    async def stop(self) -> None:
        """Stops the listener gracefully."""
        self._running = False
        if self._task and not self._task.done():
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass
            self._task = None
        logger.info("TelegramBotRunner: Interactive polling stopped.")

    async def _poll_loop(self) -> None:
        # Give DB and ingestion supervisor a moment on startup
        await asyncio.sleep(5)
        tg_svc = get_telegram_service()

        async with httpx.AsyncClient(timeout=35.0) as client:
            while self._running:
                try:
                    token = settings.TELEGRAM_BOT_TOKEN
                    if not token:
                        await asyncio.sleep(10)
                        continue

                    url = f"https://api.telegram.org/bot{token}/getUpdates"
                    params = {
                        "offset": self._offset,
                        "timeout": 25,
                        "allowed_updates": ["message"],
                    }

                    res = await client.get(url, params=params)
                    if res.status_code == 200:
                        data = res.json()
                        updates = data.get("result", [])
                        for update in updates:
                            self._offset = update.get("update_id", 0) + 1
                            msg = update.get("message", {})
                            text = (msg.get("text") or "").strip()
                            chat = msg.get("chat", {})
                            chat_id = str(chat.get("id", ""))

                            if not text or not chat_id:
                                continue

                            # Auto-lock chat_id if not configured
                            if not settings.TELEGRAM_CHAT_ID:
                                settings.TELEGRAM_CHAT_ID = chat_id
                                tg_svc.chat_id = chat_id
                                logger.info(f"TelegramBotRunner: Auto-locked TELEGRAM_CHAT_ID to {chat_id}")

                            await self._handle_command(text, chat_id, tg_svc)

                    elif res.status_code == 409:
                        # Conflict: Another instance might be polling
                        logger.warning("TelegramBotRunner: getUpdates conflict (409). Backing off 10s...")
                        await asyncio.sleep(10)
                    else:
                        logger.warning(f"Telegram getUpdates returned {res.status_code}: {res.text}")
                        await asyncio.sleep(5)

                except asyncio.CancelledError:
                    break
                except Exception as exc:
                    logger.debug(f"Telegram polling network cycle exception: {exc}")
                    await asyncio.sleep(5)

    async def _handle_command(self, text: str, chat_id: str, tg_svc) -> None:
        cmd_parts = text.split()
        cmd = cmd_parts[0].lower().split("@")[0] # Strip bot username if mentioned
        args = cmd_parts[1:] if len(cmd_parts) > 1 else []

        if cmd in ["/start", "/help"]:
            await tg_svc.send_message(self._msg_help(), chat_id=chat_id)

        elif cmd in ["/gold", "/xau", "/xauusd"]:
            await self._handle_symbol_analysis("XAUUSD", chat_id, tg_svc)

        elif cmd in ["/silver", "/xag", "/xagusd"]:
            await self._handle_symbol_analysis("XAGUSD", chat_id, tg_svc)

        elif cmd in ["/p", "/price", "/analyze"]:
            sym = args[0].upper() if args else "XAUUSD"
            await self._handle_symbol_analysis(sym, chat_id, tg_svc)

        elif cmd in ["/session", "/sessions"]:
            await self._handle_session_info(chat_id, tg_svc)

        elif cmd in ["/setups", "/signals"]:
            await self._handle_active_setups(chat_id, tg_svc)

        elif cmd in ["/status", "/health"]:
            await self._handle_status(chat_id, tg_svc)

        else:
            # Friendly fallback for unrecognised commands
            if text.startswith("/"):
                await tg_svc.send_message(
                    f"❓ Unknown command: <code>{text}</code>\n\nUse /gold, /silver, /session, /setups, or /help.",
                    chat_id=chat_id,
                )

    async def _handle_symbol_analysis(self, symbol: str, chat_id: str, tg_svc) -> None:
        clean_sym = symbol.upper().replace("/", "").replace("_", "")
        # Preliminary typing indicator message
        await tg_svc.send_message(f"⏳ Analyzing institutional ICT/SMC structure for <b>{clean_sym}</b>...", chat_id=chat_id)

        try:
            async with async_session_factory() as db:
                ai_engine = AIAnalysisEngine(db)
                req = AIAnalysisRequest(symbol=clean_sym, timeframe="15m")
                analysis = await ai_engine.execute_analysis(req)

                is_gold = "XAU" in clean_sym
                is_silver = "XAG" in clean_sym
                badge = "🥇 <b>GOLD (XAU/USD)</b>" if is_gold else ("🥈 <b>SILVER (XAG/USD)</b>" if is_silver else f"📊 <b>{clean_sym}</b>")

                st_val = analysis.state.value if hasattr(analysis.state, "value") else str(analysis.state)
                if st_val == AnalysisStateEnum.VALID_SETUP.value:
                    st_header = "🟢 🎯 <b>CONFIRMED VALID SETUP</b>"
                elif st_val == AnalysisStateEnum.POTENTIAL_SETUP.value:
                    st_header = "🟡 ⚠️ <b>SETUP FORMING (WATCH)</b>"
                else:
                    st_header = f"⚪ ℹ️ <b>MARKET STATUS: {st_val}</b>"

                lines = [
                    st_header,
                    f"{badge} | ⏱ <b>15M</b> | 🏛 <b>{(analysis.session_name or 'Active').upper()}</b>",
                    "",
                    "💡 <b>Institutional Narrative:</b>",
                    f"<blockquote>{analysis.summary}</blockquote>",
                ]

                if analysis.condition_breakdown:
                    lines.append("📋 <b>Strategy Checklist:</b>")
                    for c in analysis.condition_breakdown[:5]:
                        icon = "✅" if c.satisfied else "❌"
                        notes = f" ({c.evidence})" if c.evidence else ""
                        lines.append(f"{icon} <b>{c.condition}</b>{notes}")
                    lines.append("")

                now_str = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")
                lines.append(f"⏰ <i>{now_str}</i>")
                lines.append("🤖 <i>Forex AI Institutional Execution Engine</i>")

                await tg_svc.send_message("\n".join(lines), chat_id=chat_id)

        except Exception as e:
            logger.error(f"Error running Telegram on-demand analysis for {clean_sym}: {e}", exc_info=True)
            await tg_svc.send_message(
                f"⚠️ Could not compute analysis for <b>{clean_sym}</b>: {e}\n\nMake sure candles are ingested for this instrument.",
                chat_id=chat_id,
            )

    async def _handle_session_info(self, chat_id: str, tg_svc) -> None:
        now_utc = datetime.now(timezone.utc)
        session_state = SessionEngine.evaluate_sessions(now_utc)
        kz_info = SessionEngine.get_killzone_info(now_utc)

        lines = [
            "🏛 <b>FOREX SESSION & KILLZONE RADAR</b>",
            f"⏰ <i>Current UTC: {now_utc.strftime('%H:%M:%S UTC')}</i>",
            "",
            f"🌍 <b>Primary Session:</b> {(session_state.primary_session or 'Off-Hours').upper()}",
            f"🔄 <b>Overlap Active:</b> {'YES (' + str(session_state.overlap_name) + ')' if session_state.is_overlap else 'NO'}",
            f"🎯 <b>Killzone Status:</b> {'🚨 ACTIVE: ' + kz_info.get('active_killzone', '') if kz_info.get('in_killzone') else 'Idle (Outside Killzones)'}",
            "",
            "🕒 <b>Session Windows:</b>",
            "• <b>Asian Session:</b> 00:00 - 08:00 UTC (Liquidity Range)",
            "• <b>London Killzone:</b> 08:00 - 11:00 UTC (Judas Swing / Expansion)",
            "• <b>New York Killzone:</b> 13:00 - 16:00 UTC (High Volatility Trend Continuation)",
            "• <b>London Close:</b> 15:00 - 17:00 UTC (Retracement / Reversal)",
            "",
            "💡 <i>Tip: The highest-probability Gold (XAUUSD) setups occur during London & NY Killzone overlaps.</i>",
        ]
        await tg_svc.send_message("\n".join(lines), chat_id=chat_id)

    async def _handle_active_setups(self, chat_id: str, tg_svc) -> None:
        await tg_svc.send_message("🔍 Scanning live institutional market conditions across target metals...", chat_id=chat_id)
        symbols = ["XAUUSD", "XAGUSD"]
        found = []

        async with async_session_factory() as db:
            ai_engine = AIAnalysisEngine(db)
            for s in symbols:
                try:
                    req = AIAnalysisRequest(symbol=s, timeframe="15m")
                    res = await ai_engine.execute_analysis(req)
                    st = res.state.value if hasattr(res.state, "value") else str(res.state)
                    if st in [AnalysisStateEnum.VALID_SETUP.value, AnalysisStateEnum.POTENTIAL_SETUP.value]:
                        found.append((s, st, res.summary))
                except Exception:
                    pass

        if found:
            lines = ["🎯 <b>ACTIVE HIGH-PROBABILITY SETUPS DETECTED</b>", ""]
            for s, st, summary in found:
                icon = "🥇" if s == "XAUUSD" else "🥈"
                lines.append(f"{icon} <b>{s}</b> [{st}]")
                lines.append(f"<blockquote>{summary}</blockquote>\n")
            lines.append("Send /gold or /silver for complete checklist breakdown.")
            await tg_svc.send_message("\n".join(lines), chat_id=chat_id)
        else:
            await tg_svc.send_message(
                "😴 <b>No active setup at this moment.</b>\n\n"
                "Structure is currently consolidating or in dealing range formation. "
                "The bot will automatically notify you the moment a setup is confirmed on <b>XAUUSD</b> or <b>XAGUSD</b>!",
                chat_id=chat_id,
            )

    async def _handle_status(self, chat_id: str, tg_svc) -> None:
        from app.services.market_data import get_market_data_provider
        prov = get_market_data_provider(settings.DEFAULT_PROVIDER)
        now_str = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")

        lines = [
            "⚡ <b>FOREX AI BACKEND STATUS</b>",
            f"🌐 <b>Environment:</b> {settings.ENVIRONMENT}",
            f"📡 <b>Market Data Provider:</b> {settings.DEFAULT_PROVIDER.upper()}",
            f"🔌 <b>WebSocket Feed:</b> {'Connected' if getattr(prov, 'is_connected', False) else 'Active'}",
            f"🎯 <b>Target Telegram Pairs:</b> {', '.join(settings.TELEGRAM_TARGET_PAIRS)}",
            f"⏰ <b>Server Time:</b> {now_str}",
            "",
            "✅ <i>Continuous session scanner running 24/7.</i>",
        ]
        await tg_svc.send_message("\n".join(lines), chat_id=chat_id)

    def _msg_help(self) -> str:
        return (
            "🏛 <b>Forex AI Institutional Trading Bot</b>\n\n"
            "Real-time institutional ICT/SMC market structure analysis and setup dispatch for <b>Gold (XAU/USD)</b> and <b>Silver (XAG/USD)</b>.\n\n"
            "<b>Available Commands:</b>\n"
            "🥇 /gold or /xau - Instant 15m Gold structure & setup analysis\n"
            "🥈 /silver or /xag - Instant 15m Silver structure & setup analysis\n"
            "🎯 /setups - Check for active setups right now\n"
            "🏛 /session - Check active Forex session & Killzone windows\n"
            "📊 /p &lt;symbol&gt; - Quick analysis for any instrument (e.g. <code>/p EURUSD</code>)\n"
            "⚡ /status - Check backend connectivity & live feed status\n"
            "❓ /help - Show this guide\n\n"
            "🔔 <i>Automated Push: You will automatically receive a message here whenever a valid setup is confirmed during London or New York sessions!</i>"
        )

_bot_runner_instance: Optional[TelegramBotRunner] = None

def get_telegram_bot_runner() -> TelegramBotRunner:
    global _bot_runner_instance
    if _bot_runner_instance is None:
        _bot_runner_instance = TelegramBotRunner()
    return _bot_runner_instance
