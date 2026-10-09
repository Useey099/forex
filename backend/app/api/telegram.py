from typing import List, Optional
from fastapi import APIRouter, Query, HTTPException, status
from pydantic import BaseModel
from datetime import datetime, timezone

from app.core.config import settings
from app.services.notifications.telegram_service import get_telegram_service
from app.schemas.ai_analysis import AnalysisRecordRead, ConditionStatus
from app.models.analysis import AnalysisStateEnum

router = APIRouter(prefix="/telegram", tags=["Telegram Bot Setup Alerts"])

class TelegramConfigRequest(BaseModel):
    bot_token: Optional[str] = None
    chat_id: Optional[str] = None
    enabled: Optional[bool] = None
    target_pairs: Optional[List[str]] = None
    notify_on_potential: Optional[bool] = None

class TelegramConfigResponse(BaseModel):
    is_configured: bool
    enabled: bool
    chat_id: Optional[str]
    target_pairs: List[str]
    notify_on_valid: bool
    notify_on_potential: bool
    bot_username: Optional[str] = None

@router.get("/status", response_model=TelegramConfigResponse)
async def get_telegram_status():
    """
    Returns the current Telegram Bot connectivity and target pair status.
    """
    svc = get_telegram_service()
    conn_info = await svc.test_connection() if svc.bot_token else {}
    return TelegramConfigResponse(
        is_configured=svc.is_configured,
        enabled=settings.TELEGRAM_ENABLED,
        chat_id=svc.chat_id or None,
        target_pairs=svc.target_pairs,
        notify_on_valid=settings.TELEGRAM_NOTIFY_ON_VALID_SETUP,
        notify_on_potential=settings.TELEGRAM_NOTIFY_ON_POTENTIAL_SETUP,
        bot_username=conn_info.get("bot_username"),
    )

@router.post("/config", response_model=TelegramConfigResponse)
async def update_telegram_config(req: TelegramConfigRequest):
    """
    Updates the Telegram bot token, chat ID, or target pairs at runtime.
    """
    svc = get_telegram_service()
    if req.bot_token is not None:
        svc.bot_token = req.bot_token
        settings.TELEGRAM_BOT_TOKEN = req.bot_token
    if req.chat_id is not None:
        svc.chat_id = req.chat_id
        settings.TELEGRAM_CHAT_ID = req.chat_id
    if req.enabled is not None:
        settings.TELEGRAM_ENABLED = req.enabled
    if req.target_pairs is not None:
        svc.target_pairs = req.target_pairs
        settings.TELEGRAM_TARGET_PAIRS = req.target_pairs
    if req.notify_on_potential is not None:
        settings.TELEGRAM_NOTIFY_ON_POTENTIAL_SETUP = req.notify_on_potential

    conn_info = await svc.test_connection() if svc.bot_token else {}
    return TelegramConfigResponse(
        is_configured=svc.is_configured,
        enabled=settings.TELEGRAM_ENABLED,
        chat_id=svc.chat_id or None,
        target_pairs=svc.target_pairs,
        notify_on_valid=settings.TELEGRAM_NOTIFY_ON_VALID_SETUP,
        notify_on_potential=settings.TELEGRAM_NOTIFY_ON_POTENTIAL_SETUP,
        bot_username=conn_info.get("bot_username"),
    )

@router.post("/test-setup")
async def send_test_telegram_setup(
    symbol: str = Query("XAUUSD", description="Symbol to simulate (e.g. XAUUSD or XAGUSD)"),
    timeframe: str = Query("15m", description="Timeframe"),
    state: str = Query("VALID_SETUP", description="VALID_SETUP or POTENTIAL_SETUP"),
):
    """
    Triggers an immediate test setup alert for XAUUSD or XAGUSD to your Telegram chat.
    Use this to verify formatting and message delivery.
    """
    svc = get_telegram_service()
    if not svc.bot_token or not svc.chat_id:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Telegram is not configured yet. Set TELEGRAM_BOT_TOKEN and TELEGRAM_CHAT_ID first.",
        )

    st_enum = AnalysisStateEnum.VALID_SETUP if state.upper() == "VALID_SETUP" else AnalysisStateEnum.POTENTIAL_SETUP

    is_gold = "XAU" in symbol.upper()
    summary = (
        "Bullish Market Structure Shift (MSS) with displacement following liquidity sweep of Asian session low. "
        "Price entered high-probability Bullish Fair Value Gap (FVG) in London Killzone."
        if is_gold
        else "Bearish MSS confirmed after London high liquidity grab. Clean Order Block (OB) tapped with rejection wick."
    )

    test_analysis = AnalysisRecordRead(
        id=77777,
        symbol=symbol.upper(),
        instrument_id=1,
        timeframe=timeframe,
        timestamp_utc=datetime.now(timezone.utc),
        session_name="London Killzone",
        model_version="msnr-v2",
        state=st_enum,
        summary=summary,
        condition_breakdown=[
            ConditionStatus(
                condition="Asian Liquidity Sweep",
                satisfied=True,
                evidence=f"{symbol} swept Asian Session low with rejection",
            ),
            ConditionStatus(
                condition="Market Structure Shift (MSS)",
                satisfied=True,
                evidence="Displacement candle broke swing high with body close",
            ),
            ConditionStatus(
                condition="PD Array (FVG / OB Retest)",
                satisfied=True,
                evidence="15m FVG mitigated with zero invalidation",
            ),
            ConditionStatus(
                condition="Session Killzone Timing",
                satisfied=True,
                evidence="London Killzone (08:00 - 11:00 UTC)",
            ),
        ],
        ambiguities_detected=[],
        created_at=datetime.now(timezone.utc),
    )

    delivered = await svc.send_setup_alert(test_analysis, force=True)
    if delivered:
        return {
            "success": True,
            "message": f"Test alert for {symbol} sent successfully to Telegram chat {svc.chat_id}!",
            "symbol": symbol.upper(),
            "timeframe": timeframe,
            "state": st_enum.value,
        }
    else:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail="Failed to send message to Telegram. Check your bot token and chat ID.",
        )
