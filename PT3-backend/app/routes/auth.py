from fastapi import APIRouter, Depends, HTTPException, Request, Response, status

from app.core.auth import current_user
from app.core.rate_limit import check_auth_rate_limit, clear_auth_rate_limit
from app.schemas.auth import (
    AuthResponse,
    ChangePasswordRequest,
    LoginRequest,
    LogoutResponse,
    RegisterRequest,
    UserResponse,
)
from app.services.auth_service import (
    AuthError,
    SessionUser,
    authenticate_user,
    change_password,
    create_session,
    create_user,
    revoke_session_hash,
)

router = APIRouter(prefix="/auth", tags=["auth"])


def _user_response(user) -> UserResponse:
    return UserResponse(
        user_id=user.user_id,
        display_name=user.display_name,
        created_at=user.created_at,
    )


def _rate_client(request: Request) -> str:
    forwarded_for = request.headers.get("x-forwarded-for", "")
    if forwarded_for:
        return forwarded_for.split(",", 1)[0].strip()[:64]
    return request.client.host if request.client else "unknown"


def _no_store(response: Response) -> None:
    response.headers["Cache-Control"] = "no-store"
    response.headers["Pragma"] = "no-cache"


@router.post("/register", response_model=AuthResponse, status_code=status.HTTP_201_CREATED)
def register(body: RegisterRequest, request: Request, response: Response) -> AuthResponse:
    rate_key = f"register:{_rate_client(request)}:{body.user_id}"
    check_auth_rate_limit(rate_key)
    try:
        user = create_user(body.user_id, body.password, body.display_name)
        token = create_session(user.user_id)
    except AuthError as exc:
        raise HTTPException(status_code=exc.status_code, detail=exc.detail) from exc

    clear_auth_rate_limit(rate_key)
    _no_store(response)
    return AuthResponse(access_token=token, user=_user_response(user))


@router.post("/login", response_model=AuthResponse)
def login(body: LoginRequest, request: Request, response: Response) -> AuthResponse:
    rate_key = f"login:{_rate_client(request)}:{body.user_id}"
    check_auth_rate_limit(rate_key)
    try:
        user = authenticate_user(body.user_id, body.password)
        token = create_session(user.user_id)
    except AuthError as exc:
        raise HTTPException(status_code=exc.status_code, detail=exc.detail) from exc

    clear_auth_rate_limit(rate_key)
    _no_store(response)
    return AuthResponse(access_token=token, user=_user_response(user))


@router.post("/change-password", response_model=LogoutResponse)
def change_current_password(
    body: ChangePasswordRequest,
    user: SessionUser = Depends(current_user),
) -> LogoutResponse:
    try:
        change_password(user.user_id, body.current_password, body.new_password, user.token_hash)
    except AuthError as exc:
        raise HTTPException(status_code=exc.status_code, detail=exc.detail) from exc
    return LogoutResponse(status="ok")


@router.post("/logout", response_model=LogoutResponse)
def logout(user: SessionUser = Depends(current_user)) -> LogoutResponse:
    revoke_session_hash(user.token_hash)
    return LogoutResponse(status="ok")


@router.get("/me", response_model=UserResponse)
def me(user: SessionUser = Depends(current_user)) -> UserResponse:
    return _user_response(user)
