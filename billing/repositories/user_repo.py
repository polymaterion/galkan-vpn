from typing import Optional

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from models.models import User


class UserRepository:
    def __init__(self, session: AsyncSession):
        self.session = session

    async def get_by_telegram_id(self, telegram_id: int) -> Optional[User]:
        result = await self.session.execute(
            select(User).where(User.telegram_id == telegram_id)
        )
        return result.scalar_one_or_none()

    async def get_or_create(
        self,
        telegram_id: int,
        username: Optional[str] = None,
        first_name: Optional[str] = None,
        last_name: Optional[str] = None,
    ) -> tuple[User, bool]:
        user = await self.get_by_telegram_id(telegram_id)
        if user:
            # Update display info, but never blank out existing values with a
            # None passed by a caller that doesn't have that info at hand
            # (e.g. set_language() only has telegram_id).
            if username is not None:
                user.username = username
            if first_name is not None:
                user.first_name = first_name
            if last_name is not None:
                user.last_name = last_name
            return user, False
        user = User(
            telegram_id=telegram_id,
            username=username,
            first_name=first_name,
            last_name=last_name,
        )
        self.session.add(user)
        await self.session.flush()
        return user, True

    async def get_all(self, offset: int = 0, limit: int = 50) -> list[User]:
        result = await self.session.execute(
            select(User).offset(offset).limit(limit).order_by(User.id.desc())
        )
        return list(result.scalars().all())

    async def set_language(self, telegram_id: int, language: str) -> User:
        user, _ = await self.get_or_create(telegram_id=telegram_id)
        user.language = language
        await self.session.flush()
        return user

    async def count(self) -> int:
        from sqlalchemy import func
        result = await self.session.execute(select(func.count(User.id)))
        return result.scalar_one()
