"""
Authentication API endpoints.
Handles login, logout, and token refresh operations.
Captures audit trail for all authentication events.
"""

from fastapi import APIRouter, Depends, HTTPException, Request, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.api.v1.dependencies import get_auth_manager, get_current_active_user, get_user_repository
from src.api.v1.schemas.auth_schema import (
    LoginRequest,
    RefreshRequest,
    TokenResponse,
)
from src.common.decorators.log_execution import log_execution
from src.domain.entities.user import User
from src.infrastructure.database.models.audit_log_model import AuditLogModel
from src.infrastructure.database.session import get_db_session
from src.infrastructure.security.audit_service import AuditService
from src.infrastructure.security.auth_manager import (
    AuthManager,
    AuthenticationError,
    InvalidCredentialsError,
    UserBlockedError,
    UserInactiveError,
)
from src.observability.structured_logger import get_logger

router = APIRouter(prefix="/auth", tags=["Authentication"])
logger = get_logger(__name__)


def _get_client_ip(request: Request) -> str:
    forwarded = request.headers.get("x-forwarded-for")
    if forwarded:
        return forwarded.split(",")[0].strip()
    return request.client.host if request.client else ""


@router.post(
    "/login",
    response_model=TokenResponse,
    status_code=status.HTTP_200_OK,
    summary="Authenticate user",
    description="Validate credentials and return JWT token pair.",
)
@log_execution
async def login(
    request: LoginRequest,
    http_request: Request,
    auth_manager: AuthManager = Depends(get_auth_manager),
    session: AsyncSession = Depends(get_db_session),
) -> TokenResponse:
    """POST /api/v1/auth/login — Authenticates and logs the event."""
    audit = AuditService(session)
    ip = _get_client_ip(http_request)
    user_agent = http_request.headers.get("user-agent", "")

    try:
        result = await auth_manager.login(
            username=request.username,
            password=request.password,
        )
    except InvalidCredentialsError as e:
        await audit.log_login(
            user_id=None, username=request.username, success=False,
            ip_address=ip, user_agent=user_agent, reason="Invalid credentials",
        )
        raise HTTPException(status_code=e.status_code, detail=e.message)
    except UserInactiveError as e:
        await audit.log_login(
            user_id=None, username=request.username, success=False,
            ip_address=ip, user_agent=user_agent, reason="User inactive",
        )
        raise HTTPException(status_code=e.status_code, detail=e.message)
    except UserBlockedError as e:
        await audit.log_login(
            user_id=None, username=request.username, success=False,
            ip_address=ip, user_agent=user_agent, reason="User blocked",
        )
        raise HTTPException(status_code=e.status_code, detail=e.message)

    # Log successful login
    from src.domain.repositories.user_repository import IUserRepository
    from src.infrastructure.database.repositories.user_repository_impl import UserRepositoryImpl
    user_repo = UserRepositoryImpl(session)
    user = await user_repo.get_by_username(request.username)
    if user:
        await audit.log_login(
            user_id=user.id, username=user.username, success=True,
            ip_address=ip, user_agent=user_agent,
        )

    return TokenResponse(
        access_token=result.access_token,
        refresh_token=result.refresh_token,
        token_type=result.token_type,
        expires_in=result.expires_in,
    )


@router.post(
    "/logout",
    status_code=status.HTTP_200_OK,
    summary="Logout user",
    description="Logs the logout event in audit trail.",
)
async def logout(
    http_request: Request,
    current_user: User = Depends(get_current_active_user),
    session: AsyncSession = Depends(get_db_session),
) -> dict:
    """POST /api/v1/auth/logout — Records logout in audit trail."""
    audit = AuditService(session)
    ip = _get_client_ip(http_request)
    user_agent = http_request.headers.get("user-agent", "")

    await audit.log(
        actor_id=current_user.id,
        actor_username=current_user.username,
        action="LOGOUT",
        resource_type="Authentication",
        resource_id=current_user.username,
        ip_address=ip,
        user_agent=user_agent,
    )

    return {"detail": "Logged out successfully"}


@router.post(
    "/refresh",
    response_model=TokenResponse,
    status_code=status.HTTP_200_OK,
    summary="Refresh access token",
    description="Exchange a valid refresh token for a new access token.",
)
@log_execution
async def refresh_token(
    request: RefreshRequest,
    auth_manager: AuthManager = Depends(get_auth_manager),
) -> TokenResponse:
    """
    POST /api/v1/auth/refresh

    Validates refresh token and issues a new access token.

    Errors:
        401: Invalid or expired refresh token
        403: User blocked or inactive
    """
    try:
        result = await auth_manager.refresh(refresh_token=request.refresh_token)
    except AuthenticationError as e:
        raise HTTPException(status_code=e.status_code, detail=e.message)

    return TokenResponse(
        access_token=result.access_token,
        refresh_token=result.refresh_token,
        token_type=result.token_type,
        expires_in=result.expires_in,
    )


@router.get(
    "/me",
    summary="Get current user info",
    description="Returns the authenticated user's profile (no password hash).",
)
async def get_me(
    current_user: User = Depends(get_current_active_user),
    session: AsyncSession = Depends(get_db_session),
) -> dict:
    """GET /api/v1/auth/me - Returns current user info.

    `email` is resolved from user_details.email (populated by Darwin AD
    import / Microsoft SSO) when available, falling back to `username` if
    it looks like an email address (e.g. users provisioned via Microsoft
    SSO, where username IS the email).
    """
    from src.infrastructure.database.models.user_details_model import UserDetailsModel

    email = ""
    details_stmt = select(UserDetailsModel.email).where(
        UserDetailsModel.user_id == current_user.id
    )
    details_result = await session.execute(details_stmt)
    details_email = details_result.scalar_one_or_none()
    if details_email:
        email = details_email
    elif "@" in current_user.username:
        email = current_user.username

    return {
        "id": str(current_user.id),
        "username": current_user.username,
        "email": email,
        "is_active": current_user.is_active,
    }


# ─── Microsoft OAuth2 / Azure AD SSO ───


@router.get(
    "/microsoft/login",
    summary="Get Microsoft SSO login URL",
    description="Returns the Azure AD authorization URL for browser redirect.",
)
async def microsoft_login() -> dict:
    """
    GET /api/v1/auth/microsoft/login

    Returns the Azure AD OAuth2 authorization URL.
    Frontend should redirect the browser to the returned auth_url.
    Returns 501 if Azure SSO is not configured.
    """
    from src.infrastructure.external.azure_sso import AzureSsoClient

    client = AzureSsoClient()
    if not client.is_configured:
        raise HTTPException(
            status_code=status.HTTP_501_NOT_IMPLEMENTED,
            detail="Microsoft SSO is not configured on this server",
        )

    auth_url, redirect_uri = client.build_authorization_url()
    return {"auth_url": auth_url, "redirect_uri": redirect_uri}


@router.post(
    "/microsoft/callback",
    response_model=TokenResponse,
    summary="Exchange Microsoft auth code for tokens",
    description="Exchanges Azure AD authorization code for application JWT pair.",
)
@log_execution
async def microsoft_callback(
    body: dict,
    user_repo=Depends(get_user_repository),
) -> TokenResponse:
    """
    POST /api/v1/auth/microsoft/callback

    Flow:
    1. Exchange code for Microsoft access_token via AzureSsoClient
    2. Fetch Graph profile (UPN, email, employeeId, name)
    3. Look up local user by username (email)
    4. If not found → auto-provision with is_active=True
    5. Issue app JWT pair
    6. Return token response

    Errors:
        400: Missing code or exchange failure
        403: User account is inactive/blocked
        501: Azure SSO not configured
    """
    from uuid import uuid4

    from src.infrastructure.external.azure_sso import (
        AzureAuthError,
        AzureSsoClient,
        AzureTokenMissingError,
        AzureUnavailableError,
    )
    from src.infrastructure.security.jwt_provider import JWTProvider
    from src.infrastructure.security.password_encoder import hash_password
    import secrets

    client = AzureSsoClient()
    if not client.is_configured:
        raise HTTPException(
            status_code=status.HTTP_501_NOT_IMPLEMENTED,
            detail="Microsoft SSO is not configured on this server",
        )

    code = (body.get("code") or "").strip()
    if not code:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Authorization code is required",
        )

    # Exchange code for Microsoft tokens + Graph profile
    try:
        ms_user = await client.exchange_code_for_profile(code)
    except AzureTokenMissingError:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Failed to obtain access token from Microsoft",
        )
    except AzureAuthError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=exc.detail)
    except AzureUnavailableError:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail="Could not reach Microsoft authentication service",
        )

    # Extract user info from Graph profile
    upn = ms_user.get("userPrincipalName") or ms_user.get("mail") or ""
    email = (ms_user.get("mail") or upn or "").lower().strip()

    if not email:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Microsoft account has no email — cannot map to a user",
        )

    # Find or create local user
    user = await user_repo.get_by_username(email)

    if user is None:
        # Auto-provision: create local user from Microsoft profile
        from src.domain.entities.user import User as UserEntity

        user = UserEntity(
            id=uuid4(),
            username=email,
            password_hash=hash_password(secrets.token_urlsafe(32)),
            is_active=True,
            is_blocked=False,
            role="USER",
            created_by="microsoft_sso",
            modified_by="microsoft_sso",
        )
        user = await user_repo.create(user)

    if not user.is_active:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="User account is inactive",
        )
    if user.is_blocked:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="User account is blocked",
        )

    # Issue application JWT pair
    jwt_provider = JWTProvider()
    access_token = jwt_provider.create_access_token(user.username, user.id)
    refresh_token = jwt_provider.create_refresh_token(user.username, user.id)

    from src.config.settings import settings as app_settings

    return TokenResponse(
        access_token=access_token,
        refresh_token=refresh_token,
        token_type="Bearer",
        expires_in=app_settings.ACCESS_TOKEN_EXPIRE_MINUTES * 60,
    )
