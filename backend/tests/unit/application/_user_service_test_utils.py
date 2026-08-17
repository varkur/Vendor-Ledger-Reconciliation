"""
Shared test helpers for UserService property/example tests.

These tests exercise UserService against a real Postgres database (the
locally configured DATABASE_URL, already migrated to head). Each Hypothesis
example creates its own async engine bound to a fresh event loop (via
asyncio.run) and rolls back all changes at the end, so examples never leak
state into each other or into the shared dev database.
"""

import asyncio
from collections.abc import Awaitable, Callable
from contextlib import asynccontextmanager
from datetime import datetime, timezone
from uuid import uuid4

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from src.config.settings import settings
from src.domain.entities.user import User
from src.infrastructure.database.models.role_model import RoleModel
from src.infrastructure.database.repositories.user_repository_impl import UserRepositoryImpl


@asynccontextmanager
async def fresh_session():
    """
    Create a brand-new engine + session bound to the current event loop,
    yield it inside an explicit transaction, and always roll back + dispose
    on exit so tests never persist data.
    """
    engine = create_async_engine(settings.DATABASE_URL, pool_size=1, max_overflow=0)
    session_factory = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    session = session_factory()
    try:
        yield session
    finally:
        await session.rollback()
        await session.close()
        await engine.dispose()


def run_async(coro_fn: Callable[[], Awaitable]) -> None:
    """Run an async test body in a fresh event loop (for use with @given on sync tests)."""
    asyncio.run(coro_fn())


def make_actor(username: str = "test_actor") -> User:
    """Build a plain (non-persisted) domain User to use as the `actor` argument."""
    return User(
        id=uuid4(),
        username=username,
        password_hash="unused",
        is_active=True,
        is_blocked=False,
        is_validate_ad=False,
        created_by="system",
        created_date=datetime.now(timezone.utc),
        modified_by="system",
        modified_date=datetime.now(timezone.utc),
    )


async def create_role(session: AsyncSession, *, is_active: bool = True, code: str | None = None) -> RoleModel:
    """Create an ad hoc role row scoped to this test's transaction (rolled back after)."""
    role = RoleModel(
        id=uuid4(),
        code=code or f"hyp_role_{uuid4().hex[:12]}",
        name="Hypothesis Test Role",
        description="",
        is_system=False,
        is_active=is_active,
        created_by="test",
        modified_by="test",
    )
    session.add(role)
    await session.flush()
    return role


def make_user_repo(session: AsyncSession) -> UserRepositoryImpl:
    return UserRepositoryImpl(session)


class FakeADClient:
    """Duck-typed stand-in for EmployeeADClient — returns a fixed payload or raises."""

    def __init__(self, response: dict | None = None, exc: Exception | None = None) -> None:
        self._response = response if response is not None else {"employeeData": []}
        self._exc = exc
        self.calls: list[list[str]] = []

    async def get_selected_employees(self, employee_ids: list[str]) -> dict:
        self.calls.append(employee_ids)
        if self._exc is not None:
            raise self._exc
        return self._response


def darwin_payload(employee_id: str, **overrides) -> dict:
    """Build a minimal Darwin `/getselectedemployees`-shaped response for one employee."""
    record = {
        "employee_id": employee_id,
        "first_name": "Test",
        "middle_name": "",
        "last_name": "User",
        "company_email_id": f"{employee_id.lower()}@example.com",
        "designation_title": "Analyst",
        "department": "Finance",
        "business_unit": "Corporate",
        "group_company": "Acme Holdings",
        "office_location": "Pune",
        "office_state": "MH",
        "office_city": "Pune",
        "job_level": "L2",
        "office_mobile_no": "",
        "personal_mobile_no": "",
        "date_of_joining": "2023-01-01",
        "direct_manager_employee_id": "",
        "direct_manager_name": "",
        "direct_manager_email": "",
        "cost_center_id": "",
        "division": "",
        "territory_code_(sales_hq_code)": "",
    }
    record.update(overrides)
    return {"employeeData": [record]}
