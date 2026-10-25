"""Backwards-compatible shim.

The old stub here (a UUID-existence check + ``len>=5 & isalnum`` roll rule) has
been superseded by the real record-linkage cascade in :mod:`roster_validator`.
This module is kept only so any lingering imports of ``StudentValidator`` /
``validate_roll_number`` keep working; new code should use ``RosterValidator``.
"""
from __future__ import annotations

import uuid

from sqlalchemy.ext.asyncio import AsyncSession

from app.repositories.student_repo import student_repo
from app.validators.roster_matching import canonical_student_id
from app.validators.roster_validator import RosterConfig, RosterValidator

__all__ = ["StudentValidator", "RosterValidator", "RosterConfig"]

_DEFAULT_CONFIG = RosterConfig()


class StudentValidator:
    @staticmethod
    async def validate_student_exists(db: AsyncSession, student_id: uuid.UUID) -> bool:
        student = await student_repo.get(db, student_id)
        return student is not None

    @staticmethod
    def validate_roll_number(roll_number: str) -> bool:
        """Now backed by the configurable roster roll-number pattern."""
        import re

        return bool(re.match(_DEFAULT_CONFIG.roll_pattern, canonical_student_id(roll_number)))
