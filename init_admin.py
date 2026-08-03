"""初始化管理员账号脚本。

用途：当数据库被重置或清空后，快速创建一个默认管理员账号。
用法：uv run init_admin.py
"""

import asyncio

from pwdlib import PasswordHash
from sqlmodel import select, SQLModel
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession
from sqlalchemy.orm import sessionmaker

from app.models.users import Users
from app.models.files import File  # 导入以解析外键关联

DATABASE_URL = "postgresql+asyncpg://postgres:123456@localhost:5432/mydb"

ADMIN_CONFIG = {
    "username": "admin",
    "password": "123456",
    "full_name": "系统管理员",
    "email": "admin@example.com",
    "phone": "18614950536",
    "disabled": False,
}


async def init_admin():
    engine = create_async_engine(DATABASE_URL, echo=False)
    AsyncSessionLocal = sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)

    password_hash = PasswordHash.recommended()

    async with AsyncSessionLocal() as session:
        # 确保表已存在
        async with engine.begin() as conn:
            await conn.run_sync(SQLModel.metadata.create_all)

        # 检查是否已存在
        result = await session.execute(
            select(Users).where(Users.username == ADMIN_CONFIG["username"])
        )
        existing = result.scalar_one_or_none()

        if existing:
            print(f"管理员账号 '{ADMIN_CONFIG['username']}' 已存在，无需创建。")
        else:
            admin = Users(
                username=ADMIN_CONFIG["username"],
                full_name=ADMIN_CONFIG["full_name"],
                email=ADMIN_CONFIG["email"],
                phone=ADMIN_CONFIG["phone"],
                disabled=ADMIN_CONFIG["disabled"],
                hashed_password=password_hash.hash(ADMIN_CONFIG["password"]),
            )
            session.add(admin)
            await session.commit()
            await session.refresh(admin)
            print(f"管理员账号创建成功！")
            print(f"  用户名: {admin.username}")
            print(f"  密码: {ADMIN_CONFIG['password']}")
            print(f"  邮箱: {admin.email}")

    await engine.dispose()


if __name__ == "__main__":
    asyncio.run(init_admin())
