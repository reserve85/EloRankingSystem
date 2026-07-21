"""Password management schemas."""

from pydantic import BaseModel, Field


class PasswordChangeRequest(BaseModel):
    """Schema for user changing their own password."""
    current_password: str = Field(..., min_length=1)
    new_password: str = Field(..., min_length=8, max_length=128)
    confirm_new_password: str = Field(..., min_length=8, max_length=128)


class PasswordResetRequest(BaseModel):
    """Schema for admin resetting a user's password."""
    user_id: int
    new_password: str = Field(..., min_length=8, max_length=128)
    confirm_new_password: str = Field(..., min_length=8, max_length=128)


class PasswordResponse(BaseModel):
    """Schema for password operation response."""
    success: bool
    message: str
    errors: list[str] = []