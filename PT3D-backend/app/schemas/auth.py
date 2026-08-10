from pydantic import BaseModel, field_validator

from app.services.auth_service import AuthError, validate_password, validate_user_id


def _as_value_error(func, value: str) -> str:
    try:
        return func(value)
    except AuthError as exc:
        raise ValueError(exc.detail) from exc


class UserResponse(BaseModel):
    user_id: str
    display_name: str
    created_at: str


class RegisterRequest(BaseModel):
    user_id: str
    password: str
    display_name: str | None = None

    @field_validator("user_id")
    @classmethod
    def user_id_valid(cls, value: str) -> str:
        return _as_value_error(validate_user_id, value)

    @field_validator("password")
    @classmethod
    def password_valid(cls, value: str) -> str:
        return _as_value_error(validate_password, value)

    @field_validator("display_name")
    @classmethod
    def display_name_valid(cls, value: str | None) -> str | None:
        if value is None:
            return value
        value = value.strip()
        if len(value) > 80:
            raise ValueError("Display name must be 80 characters or fewer.")
        return value or None


class LoginRequest(BaseModel):
    user_id: str
    password: str

    @field_validator("user_id")
    @classmethod
    def user_id_valid(cls, value: str) -> str:
        return _as_value_error(validate_user_id, value)

class ChangePasswordRequest(BaseModel):
    current_password: str
    new_password: str

    @field_validator("new_password")
    @classmethod
    def password_valid(cls, value: str) -> str:
        return _as_value_error(validate_password, value)

class AuthResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    user: UserResponse


class LogoutResponse(BaseModel):
    status: str
