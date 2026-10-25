from pydantic import BaseModel, EmailStr


class AdminLogin(BaseModel):
    email: EmailStr
    password: str


class MentorLogin(BaseModel):
    email: EmailStr
    password: str


class MentorSignup(BaseModel):
    name: str
    email: EmailStr
    phone: str | None = None
    password: str
    domains: list[str] = []


class RefreshRequest(BaseModel):
    refresh_token: str


class TokenResponse(BaseModel):
    access_token: str
    refresh_token: str
    token_type: str = "bearer"
    role: str   # for UI display only — backend never reads role from this
    name: str
