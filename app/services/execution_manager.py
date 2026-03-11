import uuid
import logging
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select
from app.models import ParsedSignal, TradeExecution, Position, OrderStatusEnum, OrderSideEnum, BrokerEnum
from app.services.alpaca_service import AlpacaService
from datetime import datetime, timezone

logger = logging.getLogger(__name__)

class ExecutionManager:
    def __init__(self):
        self.alpaca_service = AlpacaService()

    async def execute_signal(self, db: AsyncSession, signal_id: str) -> dict:
        """
        Manually approve and execute a parsed signal.
        """
        try:
            sig_uuid = uuid.UUID(signal_id)
            result = await db.execute(select(ParsedSignal).where(ParsedSignal.id == sig_uuid))
            signal = result.scalar_one_or_none()

            if not signal:
                return {"success": False, "error": "Signal not found"}

            if not signal.is_actionable:
                return {"success": False, "error": "Signal is not actionable"}

            # Map direction to side
            side_str = "buy" if signal.direction.value == "long" else "sell"
            
            # Very basic sizing logic: default to 1 unit unless otherwise specified
            qty = 1.0
            if signal.entry_price and signal.entry_price > 0:
                # If we have price, let's size it to $1000 notional for demo
                # unless price is higher than 1000
                qty = round(1000.0 / float(signal.entry_price), 4) if signal.entry_price < 1000 else 1.0
            
            # 1. Place order with Alpaca
            order_res = self.alpaca_service.place_order(
                symbol=signal.symbol,
                qty=qty,
                side=side_str,
                order_type='market',
                take_profit=float(signal.take_profit_1) if signal.take_profit_1 else None,
                stop_loss=float(signal.stop_loss) if signal.stop_loss else None
            )

            if not order_res:
                return {"success": False, "error": "Failed to place order with Alpaca"}

            # 2. Record TradeExecution in DB
            broker_order_id = order_res.get("id", f"mock_{uuid.uuid4().hex[:8]}")
            
            new_exec = TradeExecution(
                id=uuid.uuid4(),
                signal_id=signal.id,
                broker_order_id=broker_order_id,
                broker=BrokerEnum.paper_alpaca,
                status=OrderStatusEnum.submitted,
                side=OrderSideEnum.buy if side_str == "buy" else OrderSideEnum.sell,
                symbol=signal.symbol,
                quantity=qty,
                filled_quantity=0.0,
                average_fill_price=float(signal.entry_price) if signal.entry_price else 0.0,
                notional_value=qty * float(signal.entry_price) if signal.entry_price else 0.0
            )
            db.add(new_exec)

            # 3. MOCK create position
            pos_result = await db.execute(select(Position).where(Position.symbol == signal.symbol, Position.is_open == True))
            existing_pos = pos_result.scalar_one_or_none()
            if not existing_pos:
                new_pos = Position(
                    id=uuid.uuid4(),
                    symbol=signal.symbol,
                    broker=BrokerEnum.paper_alpaca,
                    quantity=qty if side_str == "buy" else -qty,
                    average_entry_price=float(signal.entry_price) if signal.entry_price else 0.0,
                    current_price=float(signal.entry_price) if signal.entry_price else 0.0,
                    is_open=True,
                    realized_pl=0.0,
                    unrealized_pl=0.0
                )
                db.add(new_pos)
            else:
                existing_pos.quantity += qty if side_str == "buy" else -qty
                # simplistic approximation
                existing_pos.average_entry_price = float(signal.entry_price) if signal.entry_price else existing_pos.average_entry_price

            await db.commit()
            return {"success": True, "order_id": broker_order_id}

        except Exception as e:
            logger.error(f"Error executing signal: {e}")
            await db.rollback()
            return {"success": False, "error": str(e)}

    async def reject_signal(self, db: AsyncSession, signal_id: str) -> dict:
        """
        Mark a signal as not actionable.
        """
        try:
            sig_uuid = uuid.UUID(signal_id)
            result = await db.execute(select(ParsedSignal).where(ParsedSignal.id == sig_uuid))
            signal = result.scalar_one_or_none()

            if not signal:
                return {"success": False, "error": "Signal not found"}

            signal.is_actionable = False
            await db.commit()
            return {"success": True}
        except Exception as e:
            logger.error(f"Error rejecting signal: {e}")
            await db.rollback()
            return {"success": False, "error": str(e)}
