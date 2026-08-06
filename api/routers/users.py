"""
User preferences (currently just language). Called by the bot on /start
and when the user changes language.
"""
from __future__ import annotations

from typing import Optional

from fastapi import APIRouter, Depends
from pydantic import BaseModel

from api.dependencies import verify_internal_key
from billing.database import get_db
from billing.repositories.user_repo import UserRepository

router = APIRouter(dependencies=[Depends(verify_internal_key)])

SUPPORTED_LANGUAGES = {"ru", "tk"}


class UserOut(BaseModel):
    telegram_id: int
    language: Optional[str]


class SetLanguageRequest(BaseModel):
    telegram_id: int
    language: str


@router.get("/me", response_model=UserOut)
async def get_me(telegram_id: int, session=Depends(get_db)):
    repo = UserRepository(session)
    user, _ = await repo.get_or_create(telegram_id=telegram_id)
    return UserOut(telegram_id=user.telegram_id, language=user.language)


@router.post("/language", response_model=UserOut)
async def set_language(req: SetLanguageRequest, session=Depends(get_db)):
    lang = req.language if req.language in SUPPORTED_LANGUAGES else "ru"
    repo = UserRepository(session)
    user = await repo.set_language(req.telegram_id, lang)
    return UserOut(telegram_id=user.telegram_id, language=user.language)
