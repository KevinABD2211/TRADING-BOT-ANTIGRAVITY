import logging
import uuid
from datetime import datetime, timezone
from pydantic import BaseModel, ConfigDict
from fastapi import HTTPException

from app.database import get_db_context
from app.models import ParsedSignal, SignalSourceEnum, ParseMethodEnum, AssetTypeEnum, DirectionEnum

logger = logging.getLogger(__name__)

# Basic Pydantic Model for incoming TradingView payloads
class TradingViewWebhook(BaseModel):
    model_config = ConfigDict(extra='ignore')
    
    symbol: str
    action: str  # "buy" or "sell"
    price: float
    asset_type: str = "crypto" # Defaulting for now
    timeframe: str = "Live Webhook"
    reasoning: str = "Triggered by external TradingView alert."
    take_profit: float | None = None
    stop_loss: float | None = None

class WebhookService:
    async def process_tradingview_alert(self, payload: TradingViewWebhook) -> dict:
        logger.info(f"Received TradingView webhook: {payload.action} {payload.symbol}")

        # Map 'buy/sell' to Internal Enums
        direction_map = {
            "buy": DirectionEnum.long,
            "sell": DirectionEnum.short,
            "long": DirectionEnum.long,
            "short": DirectionEnum.short
        }
        
        direction = direction_map.get(payload.action.lower())
        if not direction:
            logger.error(f"Invalid direction in webhook payload: {payload.action}")
            raise HTTPException(status_code=400, detail="Invalid action parameter. Must be 'buy' or 'sell'.")

        try:
            asset_enum = AssetTypeEnum[payload.asset_type.lower()]
        except KeyError:
            logger.warning(f"Unrecognized asset_type '{payload.asset_type}', defaulting to 'unknown'")
            asset_enum = AssetTypeEnum.unknown

        sg_id = uuid.uuid4()
        now = datetime.now(timezone.utc)

        signal_record = ParsedSignal(
            id=sg_id,
            source=SignalSourceEnum.tradingview,
            parse_method=ParseMethodEnum.manual, # Since it came pre-parsed from a webhook structure
            symbol=payload.symbol.upper(),
            asset_type=asset_enum,
            direction=direction,
            entry_price=payload.price,
            take_profit_1=payload.take_profit,
            stop_loss=payload.stop_loss,
            timeframe=payload.timeframe,
            leverage=1, # Default 1x
            discord_author_name="TradingView_System",
            raw_text=str(payload.model_dump()),
            signal_completeness_pct=100, # A webhook is highly structured
            is_duplicate=False,
            is_actionable=True, # Assuming direct alerts should always be actionable
            signal_timestamp=now,
            llm_confidence=1.0, # Complete trust in direct external algorithm
            analysis_reasoning=payload.reasoning
        )

        async with get_db_context() as db:
            db.add(signal_record)
            await db.commit()
            
        logger.info(f"Stored TradingView signal {sg_id} for {payload.symbol}")
        
        # NOTE: At this stage you would normally send the signal to ExecutionManager automatically!
        # Like: await execution_manager.execute_signal(...)
        
        return {"status": "success", "signal_id": str(sg_id), "message": "Signal ingested gracefully"}
