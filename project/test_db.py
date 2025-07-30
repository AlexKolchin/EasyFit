import asyncio
import os
from dotenv import load_dotenv
import asyncpg

load_dotenv()  # Завантажує змінні середовища з .env

DATABASE_URL = os.getenv("DATABASE_URL")

async def test_connection():
    try:
        # asyncpg.connect не підтримує повний URL із схемою postgresql+asyncpg://,
        # тому видаляємо схему для asyncpg, лишаємо 'postgresql://...'
        url = DATABASE_URL.replace("postgresql+asyncpg://", "postgresql://")

        conn = await asyncpg.connect(dsn=url)
        print("✅ Підключення успішне!")
        await conn.close()
    except Exception as e:
        print("❌ Помилка підключення:", e)

if __name__ == "__main__":
    asyncio.run(test_connection())
