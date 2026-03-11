import asyncio
from app.database import engine, Base
from app.models import *

async def init_models():
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    print("SQLite database tables created successfully.")

if __name__ == "__main__":
    asyncio.run(init_models())
