import asyncio
import uuid
import random
from datetime import datetime, timezone, timedelta
from app.database import engine
from app.models import ParsedSignal, RawDiscordMessage, AssetTypeEnum, DirectionEnum, SignalSourceEnum, ParseMethodEnum
from sqlalchemy.orm import sessionmaker
from sqlalchemy.ext.asyncio import AsyncSession

AsyncSessionLocal = sessionmaker(
    engine, expire_on_commit=False, class_=AsyncSession
)

async def generate_mock_data():
    async with AsyncSessionLocal() as session:
        # Generate some fake RawDiscordMessages
        messages = []
        signals = []
        
        symbols = ["BTC", "ETH", "SOL", "AAPL", "TSLA"]
        
        now = datetime.now(timezone.utc)
        
        for i in range(15):
            # 1. Create raw message
            msg_id = uuid.uuid4()
            raw_msg = RawDiscordMessage(
                id=msg_id,
                message_id=f"msg_1000{i}",
                channel_id="channel_1",
                guild_id="guild_1",
                author_id="author_1",
                author_username=f"CryptoWhale_{random.randint(1,99)}",
                content=f"Going LONG on {random.choice(symbols)} ! TP 50000",
                message_link="https://discord.com",
                discord_timestamp=now - timedelta(minutes=random.randint(1, 1000)),
                parse_attempted=True,
                parse_succeeded=True
            )
            messages.append(raw_msg)
            
            # 2. Create parsed signal
            is_long = random.choice([True, False])
            sym = random.choice(symbols)
            price = round(random.uniform(50, 60000), 2)
            
            sig = ParsedSignal(
                id=uuid.uuid4(),
                raw_message_id=msg_id,
                symbol=sym,
                asset_type=AssetTypeEnum.crypto if sym in ["BTC", "ETH", "SOL"] else AssetTypeEnum.stock,
                direction=DirectionEnum.long if is_long else DirectionEnum.short,
                entry_price=price,
                take_profit_1=price * 1.05 if is_long else price * 0.95,
                stop_loss=price * 0.95 if is_long else price * 1.05,
                source=SignalSourceEnum.discord,
                parse_method=ParseMethodEnum.regex,
                llm_confidence=random.uniform(0.7, 1.0),
                signal_timestamp=raw_msg.discord_timestamp,
                raw_text=raw_msg.content,
                is_actionable=True
            )
            signals.append(sig)
            
        session.add_all(messages)
        session.add_all(signals)
        await session.commit()
        print(f"Successfully generated {len(messages)} mock messages and signals.")

if __name__ == "__main__":
    asyncio.run(generate_mock_data())
