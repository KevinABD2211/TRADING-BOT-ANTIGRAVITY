from contextlib import asynccontextmanager
from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse
from sqlalchemy.future import select
from sqlalchemy import desc

from app.database import get_db_context, init_db
from app.models import ParsedSignal, RawDiscordMessage, TradeExecution, Position
from app.services.execution_manager import ExecutionManager
from app.services.scanner import start_scanner_loop
from pydantic import BaseModel
import os
import asyncio
import logging

logger = logging.getLogger(__name__)

execution_manager = ExecutionManager()

class SignalActionRequest(BaseModel):
    signal_id: str

@asynccontextmanager
async def lifespan(app: FastAPI):
    # Startup
    await init_db()
    
    # Start the background autonomous commodity scanner ONLY if not on Vercel
    if not os.environ.get("VERCEL"):
        asyncio.create_task(start_scanner_loop())
    else:
        logger.info("Running in Vercel environment. Background scanner disabled. Delegating to Cron.")
    
    yield
    # Shutdown

app = FastAPI(title="Trading Assistant Dashboard", lifespan=lifespan)

# Mount static files
static_dir = os.path.join(os.path.dirname(__file__), "static")
if not os.path.exists(static_dir):
    os.makedirs(static_dir)
app.mount("/static", StaticFiles(directory=static_dir), name="static")


@app.get("/")
async def serve_dashboard():
    return FileResponse(os.path.join(static_dir, "index.html"))


@app.get("/api/stats")
async def get_stats():
    async with get_db_context() as db:
        raw_count_query = await db.execute(select(RawDiscordMessage))
        raw_count = len(raw_count_query.scalars().all())

        signal_count_query = await db.execute(select(ParsedSignal))
        signal_count = len(signal_count_query.scalars().all())

    return {
        "messages_seen": raw_count,
        "signals_detected": signal_count,
        "monitoring": True, # Assume bot is off by default until connected but we show true conceptually for dashboard
        "errors": 0
    }


@app.get("/api/signals")
async def get_recent_signals(limit: int = 50):
    async with get_db_context() as db:
        result = await db.execute(
            select(ParsedSignal).order_by(desc(ParsedSignal.signal_timestamp)).limit(limit)
        )
        signals = result.scalars().all()
        
        return [
            {
                "id": str(s.id),
                "symbol": s.symbol,
                "direction": s.direction.value,
                "entry_price": s.entry_price or s.entry_range_low,
                "take_profit_1": s.take_profit_1,
                "stop_loss": s.stop_loss,
                "confidence": float(s.llm_confidence or 0.0),
                "timestamp": s.signal_timestamp,
                "asset_type": s.asset_type.value,
                "raw_text": s.raw_text,
                "source": s.source.value if s.source else "UNKNOWN",
                "parse_method": s.parse_method.value if s.parse_method else "UNKNOWN",
                "completeness": s.signal_completeness_pct or 0,
                "risk_reward": float(s.risk_reward_ratio) if s.risk_reward_ratio else None,
                "actionable": s.is_actionable,
                "duplicate": s.is_duplicate,
                "leverage": s.leverage,
                "analysis_reasoning": s.analysis_reasoning,
                "trade_timeline": s.trade_timeline
            }
            for s in signals
        ]

@app.post("/api/approve_trade")
async def approve_trade(request: SignalActionRequest):
    async with get_db_context() as db:
        res = await execution_manager.execute_signal(db, request.signal_id)
        return res

@app.post("/api/reject_trade")
async def reject_trade(request: SignalActionRequest):
    async with get_db_context() as db:
        res = await execution_manager.reject_signal(db, request.signal_id)
        return res

@app.get("/api/positions")
async def get_positions():
    async with get_db_context() as db:
        # Get active positions from DB
        result = await db.execute(select(Position).where(Position.is_open == True))
        positions = result.scalars().all()
        
        return [
            {
                "id": str(p.id),
                "symbol": p.symbol,
                "quantity": float(p.quantity),
                "average_entry_price": float(p.average_entry_price),
                "current_price": float(p.current_price) if p.current_price else float(p.average_entry_price),
                "unrealized_pl": float(p.unrealized_pl) if p.unrealized_pl else 0.0,
                "realized_pl": float(p.realized_pl) if p.realized_pl else 0.0,
                "broker": p.broker.value
            }
            for p in positions
        ]
