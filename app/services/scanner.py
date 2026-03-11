import asyncio
import logging
import uuid
from datetime import datetime, timezone
from sqlalchemy.dialects.sqlite import insert as sqlite_insert

from app.database import get_db_context
from app.models import ParsedSignal, SignalSourceEnum, ParseMethodEnum, AssetTypeEnum, DirectionEnum
from app.services.analyzer import AnalyzerService

logger = logging.getLogger(__name__)

class AutomatedScanner:
    def __init__(self):
        self.analyzer = AnalyzerService()
        self.commodities = [
            {"symbol": "GC=F", "name": "Gold", "asset_type": "futures"},
            {"symbol": "SI=F", "name": "Silver", "asset_type": "futures"},
            {"symbol": "CL=F", "name": "Crude Oil", "asset_type": "futures"}
        ]
        self.scan_interval_seconds = 3600  # 1 hour

    async def run_scanner(self):
        """Continuously loop through core commodities and create autonomous signals."""
        logger.info("Starting Autonomous Commodity Scanner Loop...")
        while True:
            for item in self.commodities:
                try:
                    await self._scan_asset(item["symbol"], item["asset_type"])
                except Exception as e:
                    logger.error(f"Scanner failed to process {item['symbol']}: {e}")
                
                # Small sleep between assets to avoid rate limiting
                await asyncio.sleep(5)
            
            # Sleep for an hour before repeating
            logger.info(f"Autonomous Scan complete. Sleeping for {self.scan_interval_seconds} seconds.")
            await asyncio.sleep(self.scan_interval_seconds)

    async def _scan_asset(self, symbol: str, asset_type: str):
        advice = await self.analyzer.generate_autonomous_advice(symbol, asset_type)
        
        if not advice:
            return
            
        direction_str = advice.get("direction", "unknown")
        
        if direction_str == "long":
            direction_enum = DirectionEnum.long
        elif direction_str == "short":
            direction_enum = DirectionEnum.short
        else:
            return  # Invalid direction

        ai_score_raw = advice.get("confidence_score", 50)
        ai_score_normalized = float(ai_score_raw) / 100.0

        # Create autonomous ParsedSignal record immediately
        sg_id = uuid.uuid4()
        now = datetime.now(timezone.utc)

        record = ParsedSignal(
            id=sg_id,
            raw_message_id=None,
            source=SignalSourceEnum.opportunity_scanner,
            parse_method=ParseMethodEnum.llm,
            symbol=symbol,
            asset_type=AssetTypeEnum[asset_type],
            exchange="YFINANCE",
            direction=direction_enum,
            entry_price=advice.get("entry_price"),
            take_profit_1=advice.get("take_profit"),
            stop_loss=advice.get("stop_loss"),
            timeframe="Auto",
            leverage=1,
            discord_author_name="AI_SCANNER",
            raw_text=f"Autonomously generated signal based purely on AI technical scan at {now.strftime('%H:%M:%S UTC')}.",
            signal_completeness_pct=100,
            is_duplicate=False,
            is_actionable=True if ai_score_raw >= 60 else False,
            signal_timestamp=now,
            llm_model_used="gpt-4o-mini",
            llm_confidence=ai_score_normalized,
            analysis_reasoning=advice.get("reasoning"),
            trade_timeline=advice.get("trade_timeline")
        )

        async with get_db_context() as db:
            db.add(record)
            await db.commit()
            
        logger.info(f"Scanner successfully dispatched autonomous {direction_str.upper()} signal for {symbol} to Dashboard.")

# Function to kick it off in background
async def start_scanner_loop():
    scanner = AutomatedScanner()
    await scanner.run_scanner()
