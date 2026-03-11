import asyncio
import json
import uuid
import logging
from datetime import datetime, timezone
from sqlalchemy.dialects.sqlite import insert as sqlite_insert

try:
    import websockets
except ImportError:
    import os
    os.system("pip install websockets")
    import websockets

from app.database import get_db_context
from app.models import RawDiscordMessage
from app.services.signal_parser.parser_router import ParserRouter
from app.services.signal_detector import SignalDetector
from app.config import get_settings

logging.basicConfig(level=logging.INFO, format="%(asctime)s | %(levelname)s | %(message)s")
logger = logging.getLogger(__name__)

detector = SignalDetector()
router = ParserRouter()

# Binance AggTrade stream for BTC and ETH
STREAM_URL = "wss://fstream.binance.com/stream?streams=btcusdt@aggTrade/ethusdt@aggTrade/solusdt@aggTrade"

async def save_and_parse_message(content: str, author: str):
    msg_id_str = f"ws_{uuid.uuid4().hex[:16]}"
    raw_id = uuid.uuid4()
    now = datetime.now(timezone.utc)
    
    async with get_db_context() as db:
        # Save exact raw message
        stmt = (
            sqlite_insert(RawDiscordMessage)
            .values(
                id=raw_id,
                message_id=msg_id_str,
                channel_id="binance_public_stream",
                guild_id="binance",
                author_id="binance_bot",
                author_username=author,
                content=content,
                message_link="https://binance.com",
                discord_timestamp=now,
                parse_attempted=False
            )
        )
        await db.execute(stmt)
        await db.commit()
    
    # Check if it has signal keywords
    is_signal, conf, kws = detector.detect(content)
    if is_signal:
        logger.info(f"Signal picked up: {content} (conf: {conf})")
        async with get_db_context() as db:
            await router.parse_and_store(db, raw_id, content)

async def listen_to_binance():
    logger.info("Connecting to Binance Public WebSocket Stream...")
    async with websockets.connect(STREAM_URL) as ws:
        logger.info("Connected successfully! Listening for whale trades...")
        while True:
            try:
                response = await ws.recv()
                data = json.loads(response)
                
                stream = data.get("stream", "")
                trade = data.get("data", {})
                
                # Trade details
                price = float(trade.get("p", 0))
                quantity = float(trade.get("q", 0))
                is_buyer_maker = trade.get("m", False) # If buyer is maker, it's a SELL order taking liquidity. If False, it's a BUY order.
                
                notional = price * quantity
                
                # Filter for "whale" trades (e.g., > $50k)
                if notional > 50000:
                    symbol = trade.get("s", "UNKNOWN").replace("USDT", "")
                    direction = "SHORT" if is_buyer_maker else "LONG"
                    
                    author = f"WhaleTracker_{uuid.uuid4().hex[:4]}"
                    # Generate a realistic text signal that the regex parser will catch easily
                    take_profit = price * 1.05 if direction == "LONG" else price * 0.95
                    stop_loss = price * 0.98 if direction == "LONG" else price * 1.02
                    
                    content = f"${symbol}/USDT {direction} @ {price:.2f} | Target: {take_profit:.2f} | Stop: {stop_loss:.2f} | Lev: 10x"
                    
                    # Offload to parser
                    asyncio.create_task(save_and_parse_message(content, author))
                    
            except Exception as e:
                logger.error(f"Error reading stream: {e}")
                await asyncio.sleep(1)

if __name__ == "__main__":
    try:
        asyncio.run(listen_to_binance())
    except KeyboardInterrupt:
        logger.info("Bot shutting down...")
