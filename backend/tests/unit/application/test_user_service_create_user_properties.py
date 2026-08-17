"""
Property-based tests (Hypothesis) for UserService.create_user.

**Validates: Requirements 1.1, 1.2, 1.3, 1.4, 1.5, 1.6, 1.8, 1.9, 1.10, 1.11, 4.3**

Runs against a real Postgres database (settings.DATABASE_URL, migrated to
head). Each example runs inside its own session/transaction that is rolled
back afterward, so examples never leak state.
"""

from uuid import uuid4

from hypothesis import HealthCheck, given, settings as hyp_settings
from hypothesis import strategies as st
from sqlalchemy import func, select

from src.api.v1.schemas.user_request import CreateUserRequest
from src.application.services.user_service import UserService
from src.domain.exceptions.domain_exceptions import ConfigurationError
from src.infrastructure.database.models.user_details_model import UserDetailsModel
from src.infrastructure.database.models.user_model import UserModel
from src.infrastructure.security.password_encoder import verify_password

from tests.unit.application._user_service_test_utils import (
    create_role,
    fresh_session,
    make_actor,
    make_user_repo,
    run_async,
)

_HYP_SETTINGS = hyp_settings(
    max_examples=5,
    deadline=None,
    suppress_health_check=[HealthCheck.function_scoped_fixture, HealthCheck.too_slow],
)

_username_strategy = st.text(
    alphabet=st.characters(whitelist_categories=("Ll", "Lu", "Nd")), min_size=6, max_size=20
).map(lambda s: f"pt_{s}")

_department_strategy = st.text(
    alphabet=st.characters(whitelist_categories=("Ll", "Lu", "Nd", "Zs"), whitelist_characters="&-_()"),
    min_size=1,
    max_size=30,
).filter(lambda s: s.strip() != "")


def _build_request(username: str, department: str, password: str | None = None) -> CreateUserRequest:
    return CreateUserRequest(
        username=username,
        password=password,
        name="Property Tester",
        email="property.tester@example.com",
        department=department,
        designation_title="QA",
        reporting_manager="",
        employee_id=None,
    )


class TestCreateUserUniquenessProperties:
    """P1, P2 — Req 1.1, 1.2"""

    @_HYP_SETTINGS
    @given(username=_username_strategy, department=_department_strategy)
    def test_unique_username_creates_exactly_one_user_and_details_row(self, username, department):
        async def body():
            async with fresh_session() as session:
                repo = make_user_repo(session)
                service = UserService(session=session, user_repo=repo)
                actor = make_actor()

                assert not await repo.exists_by_username(username)

                request = _build_request(username, department, password="ExplicitPass123!")
                created = await service.create_user(request, actor)

                assert await repo.exists_by_username(username)

                count_stmt = select(func.count()).select_from(UserDetailsModel).where(
                    UserDetailsModel.user_id == created.id
                )
                count = (await session.execute(count_stmt)).scalar_one()
                assert count == 1

        run_async(body)

    @_HYP_SETTINGS
    @given(department=_department_strategy)
    def test_duplicate_username_rejected_with_zero_mutation(self, department):
        async def body():
            async with fresh_session() as session:
                repo = make_user_repo(session)
                service = UserService(session=session, user_repo=repo)
                actor = make_actor()

                existing_username = f"pt_existing_{uuid4().hex[:10]}"
                await service.create_user(
                    _build_request(existing_username, department, password="ExplicitPass123!"), actor
                )

                before_count = (
                    await session.execute(select(func.count()).select_from(UserModel))
                ).scalar_one()

                try:
                    await service.create_user(
                        _build_request(existing_username, department, password="AnotherPass123!"), actor
                    )
                    raised = False
                except ValueError:
                    raised = True

                assert raised

                after_count = (
                    await session.execute(select(func.count()).select_from(UserModel))
                ).scalar_one()
                assert after_count == before_count

        run_async(body)


class TestCreateUserPasswordProperties:
    """P3, P4, P5 — Req 1.3, 1.4, 1.5"""

    @_HYP_SETTINGS
    @given(
        username=_username_strategy,
        department=_department_strategy,
        explicit_password=st.one_of(st.none(), st.text(min_size=8, max_size=40)),
    )
    def test_password_fallback_or_explicit(self, username, department, explicit_password):
        async def body():
            async with fresh_session() as session:
                repo = make_user_repo(session)
                service = UserService(session=session, user_repo=repo)
                actor = make_actor()

                request = _build_request(username, department, password=explicit_password)
                created = await service.create_user(request, actor)

                persisted = await repo.get_by_id(created.id)
                if explicit_password:
                    assert verify_password(explicit_password, persisted.password_hash)
                else:
                    from src.config.settings import settings
                    assert verify_password(settings.DARWINBOX_DEFAULT_PASSWORD, persisted.password_hash)

        run_async(body)

    @_HYP_SETTINGS
    @given(username=_username_strategy, department=_department_strategy)
    def test_missing_password_and_unset_default_rejects_with_zero_writes(self, username, department):
        async def body():
            from src.config import settings as settings_module

            original_default = settings_module.settings.DARWINBOX_DEFAULT_PASSWORD
            settings_module.settings.DARWINBOX_DEFAULT_PASSWORD = ""
            try:
                async with fresh_session() as session:
                    repo = make_user_repo(session)
                    service = UserService(session=session, user_repo=repo)
                    actor = make_actor()

                    before_count = (
                        await session.execute(select(func.count()).select_from(UserModel))
                    ).scalar_one()

                    try:
                        await service.create_user(_build_request(username, department, password=None), actor)
                        raised = False
                    except ConfigurationError:
                        raised = True

                    assert raised

                    after_count = (
                        await session.execute(select(func.count()).select_from(UserModel))
                    ).scalar_one()
                    assert after_count == before_count
            finally:
                settings_module.settings.DARWINBOX_DEFAULT_PASSWORD = original_default

        run_async(body)


class TestCreateUserProfileRoundTrip:
    """P6 — Req 1.6"""

    @_HYP_SETTINGS
    @given(
        username=_username_strategy,
        department=_department_strategy,
        designation=st.text(min_size=0, max_size=40),
        reporting_manager=st.text(min_size=0, max_size=40),
    )
    def test_profile_fields_round_trip(self, username, department, designation, reporting_manager):
        async def body():
            async with fresh_session() as session:
                repo = make_user_repo(session)
                service = UserService(session=session, user_repo=repo)
                actor = make_actor()

                request = CreateUserRequest(
                    username=username,
                    password="ExplicitPass123!",
                    name="Round Trip Tester",
                    email="roundtrip@example.com",
                    department=department,
                    designation_title=designation,
                    reporting_manager=reporting_manager,
                    employee_id=None,
                )
                created = await service.create_user(request, actor)
                details = await service.get_user_details(created.id)

                assert details.employee_name == "Round Trip Tester"
                assert details.email == "roundtrip@example.com"
                assert details.designation_title == designation
                assert details.reporting_manager == reporting_manager

        run_async(body)


class TestCreateUserRoleAssignmentProperties:
    """P7, P8 — Req 1.8, 1.9"""

    @_HYP_SETTINGS
    @given(username=_username_strategy, department=_department_strategy)
    def test_valid_active_role_yields_exactly_one_active_assignment(self, username, department):
        async def body():
            async with fresh_session() as session:
                repo = make_user_repo(session)
                service = UserService(session=session, user_repo=repo)
                actor = make_actor()

                role = await create_role(session, is_active=True)

                request = _build_request(username, department, password="ExplicitPass123!")
                request = request.model_copy(update={"role_id": role.id})
                created = await service.create_user(request, actor)

                roles_resp = await service.get_user_roles(created.id)
                matching = [r for r in roles_resp["roles"] if r["id"] == str(role.id)]
                assert len(matching) == 1

        run_async(body)

    @_HYP_SETTINGS
    @given(username=_username_strategy, department=_department_strategy)
    def test_invalid_role_id_rejects_with_no_user_created(self, username, department):
        async def body():
            async with fresh_session() as session:
                repo = make_user_repo(session)
                service = UserService(session=session, user_repo=repo)
                actor = make_actor()

                before_count = (
                    await session.execute(select(func.count()).select_from(UserModel))
                ).scalar_one()

                request = _build_request(username, department, password="ExplicitPass123!")
                request = request.model_copy(update={"role_id": uuid4()})

                try:
                    await service.create_user(request, actor)
                    raised = False
                except ValueError:
                    raised = True

                assert raised

                after_count = (
                    await session.execute(select(func.count()).select_from(UserModel))
                ).scalar_one()
                assert after_count == before_count

        run_async(body)


class TestDepartmentDedupProperty:
    """P9 — Req 1.10"""

    @_HYP_SETTINGS
    @given(base_name=st.text(alphabet="abcdefghijklmnopqrstuvwxyz", min_size=3, max_size=15))
    def test_case_and_whitespace_insensitive_dedup(self, base_name):
        async def body():
            async with fresh_session() as session:
                repo = make_user_repo(session)
                service = UserService(session=session, user_repo=repo)

                variant_a = base_name
                variant_b = f"  {base_name.upper()} "
                variant_c = base_name.title()

                d1 = await service._get_or_create_department(variant_a)
                d2 = await service._get_or_create_department(variant_b)
                d3 = await service._get_or_create_department(variant_c)

                assert d1.id == d2.id == d3.id

        run_async(body)


class TestCreateUserResponseNeverExposesPassword:
    """P10 — Req 1.11, 4.3"""

    @_HYP_SETTINGS
    @given(
        username=_username_strategy,
        department=_department_strategy,
        explicit_password=st.one_of(st.none(), st.text(min_size=8, max_size=40)),
    )
    def test_response_has_no_password_fields(self, username, department, explicit_password):
        async def body():
            async with fresh_session() as session:
                repo = make_user_repo(session)
                service = UserService(session=session, user_repo=repo)
                actor = make_actor()

                request = _build_request(username, department, password=explicit_password)
                response = await service.create_user(request, actor)

                assert not hasattr(response, "password_hash")
                assert not hasattr(response, "password")

        run_async(body)
