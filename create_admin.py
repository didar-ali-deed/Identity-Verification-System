import asyncio
from app.database import async_session_factory
from app.models.user import User
from app.utils.security import hash_password

async def create_admin():
    async with async_session_factory() as db:
        admin = User(
            email="admin@idv.com",
            password_hash=hash_password("Admin1234!"),
            role="admin",
            full_name="Admin",
        )
        db.add(admin)
        await db.commit()
        print("Done: admin@idv.com / Admin1234!")

asyncio.run(create_admin())
