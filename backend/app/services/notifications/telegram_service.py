import logging
from datetime import datetime, timezone, timedelta
from typing import Optional, List, Dict, Any
import httpx

from app.core.config import settings
from app.schemas.ai_analysis import AnalysisRecordRead
from app.models.analysis import AnalysisStateEnum

logger = logging.getLogger("forex_ai.telegram")

class TelegramService:
    """
    Dedicated Telegram Bot Dispatcher for Forex AI Trading Setups.
    Specialized for high-probability setups on metals (XAUUSD / XAGUSD).
    """

    def __init__(
        self,
        bot_token: Optional[str] = None,
        chat_id: Optional[str] = None,
        target_pairs: Optional[List[str]] = None,
        cooldown_minutes: int = 15,
    ):
        self.bot_token = bot_token or settings.TELEGRAM_BOT_TOKEN
        self.chat_id = chat_id or settings.TELEGRAM_CHAT_ID
        self.target_pairs = target_pairs or settings.TELEGRAM_TARGET_PAIRS
        self.cooldown_minutes = cooldown_minutes
        self._sent_cache: Dict[str, datetime] = {}

    @property
    def is_configured(self) -> bool:
        return bool(self.bot_token and self.chat_id and settings.TELEGRAM_ENABLED)

    def is_pair_eligible(self, symbol: str) -> bool:
        """Checks if symbol is in the target whitelist (default: XAUUSD, XAGUSD)."""
        clean_symbol = symbol.strip().upper().replace("/", "").replace("_", "")
        whitelist = [p.strip().upper().replace("/", "").replace("_", "") for p in self.target_pairs]
        return clean_symbol in whitelist

    async def send_message(
        self,
        text: str,
        chat_id: Optional[str] = None,
        parse_mode: str = "HTML",
    ) -> bool:
        """Sends an HTML formatted message directly to the Telegram Chat / Channel."""
        token = self.bot_token
        target_chat = chat_id or self.chat_id

        if not token or not target_chat:
            logger.debug("Telegram notification skipped: Bot token or Chat ID is not configured.")
            return False

        url = f"https://api.telegram.org/bot{token}/sendMessage"
        payload = {
            "chat_id": target_chat,
            "text": text,
            "parse_mode": parse_mode,
            "disable_web_page_preview": True,
        }

        try:
            async with httpx.AsyncClient(timeout=10.0) as client:
                res = await client.post(url, json=payload)
                if res.status_code == 200:
                    logger.info(f"Telegram alert successfully sent to chat {target_chat}.")
                    return True
                else:
                    logger.warning(
                        f"Telegram API responded with {res.status_code}: {res.text}"
                    )
                    return False
        except Exception as exc:
            logger.error(f"Failed to deliver Telegram message: {exc}", exc_info=True)
            return False

    async def send_setup_alert(
        self,
        analysis: AnalysisRecordRead,
        force: bool = False,
    ) -> bool:
        """
        Formats and delivers a high-priority trading setup alert.
        Filters strictly by target pairs (primarily XAUUSD and XAGUSD).
        """
        symbol = analysis.symbol.upper()

        # 1. Eligibility Check
        if not self.is_pair_eligible(symbol) and not force:
            logger.debug(f"Telegram alert skipped: {symbol} is not in target pairs ({self.target_pairs}).")
            return False

        state_str = analysis.state.value if hasattr(analysis.state, "value") else str(analysis.state)
        if state_str not in [AnalysisStateEnum.VALID_SETUP.value, AnalysisStateEnum.POTENTIAL_SETUP.value] and not force:
            logger.debug(f"Telegram alert skipped: state '{state_str}' is neither VALID_SETUP nor POTENTIAL_SETUP.")
            return False

        if state_str == AnalysisStateEnum.POTENTIAL_SETUP.value and not settings.TELEGRAM_NOTIFY_ON_POTENTIAL_SETUP and not force:
            return False

        if state_str == AnalysisStateEnum.VALID_SETUP.value and not settings.TELEGRAM_NOTIFY_ON_VALID_SETUP and not force:
            return False

        # 2. Cooldown & Deduplication Check
        cache_key = f"{symbol}:{analysis.timeframe}:{state_str}"
        now = datetime.now(timezone.utc)
        if not force and cache_key in self._sent_cache:
            last_sent = self._sent_cache[cache_key]
            if (now - last_sent) < timedelta(minutes=self.cooldown_minutes):
                logger.info(f"Telegram alert for {symbol} suppressed due to {self.cooldown_minutes}m cooldown.")
                return False

        # 3. Format Telegram Message
        message = self._format_setup_message(analysis)

        # 4. Dispatch
        success = await self.send_message(message)
        if success:
            self._sent_cache[cache_key] = now
            # Clean expired items in cache
            threshold = now - timedelta(hours=2)
            self._sent_cache = {k: v for k, v in self._sent_cache.items() if v > threshold}

        return success

    def _format_setup_message(self, analysis: AnalysisRecordRead) -> str:
        """Creates a professional trading alert layout with emojis and HTML markup."""
        symbol = analysis.symbol.upper()
        state_str = analysis.state.value if hasattr(analysis.state, "value") else str(analysis.state)

        # Pair Icon
        if "XAU" in symbol or "GOLD" in symbol:
            pair_badge = "🥇 <b>GOLD (XAU/USD)</b>"
        elif "XAG" in symbol or "SILVER" in symbol:
            pair_badge = "🥈 <b>SILVER (XAG/USD)</b>"
        else:
            pair_badge = f"📊 <b>{symbol}</b>"

        # State Header
        if state_str == AnalysisStateEnum.VALID_SETUP.value:
            status_header = "🎯 <b>CONFIRMED VALID SETUP</b>"
            status_color = "🟢"
        elif state_str == AnalysisStateEnum.POTENTIAL_SETUP.value:
            status_header = "⚠️ <b>SETUP FORMING (WATCH)</b>"
            status_color = "🟡"
        else:
            status_header = f"ℹ️ <b>MARKET ALERT: {state_str}</b>"
            status_color = "🔵"

        session_str = (analysis.session_name or "Active Session").upper()
        tf_str = analysis.timeframe.upper()
        now_str = analysis.timestamp_utc.strftime("%Y-%m-%d %H:%M:%S UTC")

        lines = [
            f"{status_color} {status_header}",
            f"{pair_badge} | ⏱ <b>{tf_str}</b> | 🏛 <b>{session_str}</b>",
            "",
            f"💡 <b>Strategy Summary:</b>",
            f"<blockquote>{analysis.summary}</blockquote>",
        ]

        # Checklist breakdown
        if analysis.condition_breakdown:
            lines.append("📋 <b>Strategy Checklist:</b>")
            for cond in analysis.condition_breakdown[:6]:
                check = "✅" if cond.satisfied else "❌"
                notes = f" ({cond.evidence})" if cond.evidence else ""
                lines.append(f"{check} <b>{cond.condition}</b>{notes}")
            lines.append("")

        # Ambiguities or cautions if any
        if analysis.ambiguities_detected:
            lines.append("⚠️ <b>Risk / Ambiguities:</b>")
            for amb in analysis.ambiguities_detected[:2]:
                lines.append(f"• {amb.reason}")
            lines.append("")

        lines.append(f"⏰ <i>Timestamp: {now_str}</i>")
        lines.append("🤖 <i>Forex AI Institutional Execution Engine</i>")

        return "\n".join(lines)

    async def test_connection(self) -> Dict[str, Any]:
        """Tests connectivity with the Telegram Bot API and returns diagnostic details."""
        if not self.bot_token:
            return {
                "success": False,
                "configured": False,
                "error": "TELEGRAM_BOT_TOKEN is not set in environment or settings.",
            }

        url = f"https://api.telegram.org/bot{self.bot_token}/getMe"
        try:
            async with httpx.AsyncClient(timeout=10.0) as client:
                res = await client.get(url)
                if res.status_code == 200:
                    data = res.json().get("result", {})
                    bot_username = data.get("username", "Unknown")
                    test_msg_sent = False
                    if self.chat_id:
                        test_msg_sent = await self.send_message(
                            f"🔔 <b>Forex AI Telegram Bot Connected!</b>\n\n"
                            f"🤖 Bot: @{bot_username}\n"
                            f"🎯 Target Setups: {', '.join(self.target_pairs)}\n"
                            f"🚀 Status: Ready to dispatch high-probability Gold & Silver setups."
                        )
                    return {
                        "success": True,
                        "configured": True,
                        "bot_username": bot_username,
                        "chat_id": self.chat_id,
                        "test_message_delivered": test_msg_sent,
                        "target_pairs": self.target_pairs,
                    }
                else:
                    return {
                        "success": False,
                        "configured": True,
                        "error": f"Telegram API error {res.status_code}: {res.text}",
                    }
        except Exception as exc:
            return {
                "success": False,
                "configured": True,
                "error": str(exc),
            }

_telegram_service_instance: Optional[TelegramService] = None

def get_telegram_service() -> TelegramService:
    global _telegram_service_instance
    if _telegram_service_instance is None:
        _telegram_service_instance = TelegramService()
    return _telegram_service_instance
