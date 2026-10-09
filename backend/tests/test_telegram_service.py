import pytest
from datetime import datetime, timezone
from unittest.mock import AsyncMock, patch

from app.services.notifications.telegram_service import TelegramService
from app.schemas.ai_analysis import AnalysisRecordRead, ConditionStatus
from app.models.analysis import AnalysisStateEnum

@pytest.fixture
def sample_gold_analysis():
    return AnalysisRecordRead(
        id=101,
        symbol="XAUUSD",
        instrument_id=1,
        timeframe="15m",
        timestamp_utc=datetime.now(timezone.utc),
        session_name="london",
        model_version="msnr-v2",
        state=AnalysisStateEnum.VALID_SETUP,
        summary="Bullish MSS displacement above Asian high with FVG retest.",
        condition_breakdown=[
            ConditionStatus(condition="Liquidity Sweep", satisfied=True, evidence="Swept Asian low"),
            ConditionStatus(condition="MSS", satisfied=True, evidence="Closed above swing high"),
        ],
        ambiguities_detected=[],
        created_at=datetime.now(timezone.utc),
    )

@pytest.fixture
def sample_eur_analysis():
    return AnalysisRecordRead(
        id=102,
        symbol="EURUSD",
        instrument_id=2,
        timeframe="15m",
        timestamp_utc=datetime.now(timezone.utc),
        session_name="london",
        model_version="msnr-v2",
        state=AnalysisStateEnum.VALID_SETUP,
        summary="EUR setup test.",
        condition_breakdown=[],
        ambiguities_detected=[],
        created_at=datetime.now(timezone.utc),
    )

def test_telegram_pair_filtering():
    svc = TelegramService(target_pairs=["XAUUSD", "XAGUSD"])
    assert svc.is_pair_eligible("XAUUSD") is True
    assert svc.is_pair_eligible("XAGUSD") is True
    assert svc.is_pair_eligible("xauusd") is True
    assert svc.is_pair_eligible("EURUSD") is False
    assert svc.is_pair_eligible("BTCUSD") is False

@pytest.mark.asyncio
async def test_telegram_alert_dispatch_gold(sample_gold_analysis):
    svc = TelegramService(
        bot_token="test_token",
        chat_id="123456789",
        target_pairs=["XAUUSD", "XAGUSD"],
    )
    with patch.object(svc, "send_message", new_callable=AsyncMock) as mock_send:
        mock_send.return_value = True
        result = await svc.send_setup_alert(sample_gold_analysis)
        assert result is True
        mock_send.assert_awaited_once()
        sent_text = mock_send.await_args[0][0]
        assert "GOLD (XAU/USD)" in sent_text
        assert "CONFIRMED VALID SETUP" in sent_text

@pytest.mark.asyncio
async def test_telegram_alert_skips_non_metal_pair(sample_eur_analysis):
    svc = TelegramService(
        bot_token="test_token",
        chat_id="123456789",
        target_pairs=["XAUUSD", "XAGUSD"],
    )
    with patch.object(svc, "send_message", new_callable=AsyncMock) as mock_send:
        result = await svc.send_setup_alert(sample_eur_analysis)
        assert result is False
        mock_send.assert_not_awaited()
