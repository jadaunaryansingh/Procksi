import os
from fastapi import APIRouter, Depends, Header, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from app.api.deps import get_db, get_current_admin
from app.core import rest_db
from app.core.auth import (
    verify_password,
    create_access_token,
    generate_refresh_token,
    store_refresh_token,
    store_refresh_token_rest,
    verify_refresh_token,
    revoke_refresh_token,
    blacklist_jti,
)
from app.models.admin import Admin
from app.schemas.auth import AdminLogin, TokenResponse, RefreshRequest
from app.schemas.common import ok


def _allowed_email_suffix() -> str:
    """'@' + ALLOWED_EMAIL_DOMAIN. Unset rejects every address (fail closed)."""
    return "@" + os.getenv("ALLOWED_EMAIL_DOMAIN", "").strip().lstrip("@").lower()


def _master_admin_email() -> str:
    return os.getenv("MASTER_ADMIN_EMAIL", "").strip().lower()


router = APIRouter(prefix="/api/admin", tags=["Auth"])


@router.post("/login")
async def admin_login(payload: AdminLogin):
    email_clean = payload.email.strip().lower()
    if not email_clean.endswith(_allowed_email_suffix()) and email_clean != _master_admin_email():
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail={
                "success": False,
                "error": {
                    "code": "AUTH_FORBIDDEN",
                    "message": f"Only {_allowed_email_suffix()} email addresses are permitted.",
                },
            },
        )
    admin = await rest_db.select_one("admins", eq={"email": payload.email})

    if not admin or not verify_password(payload.password, admin.get("password") or ""):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail={
                "success": False,
                "error": {
                    "code": "AUTH_INVALID_CREDENTIALS",
                    "message": "Invalid email or password",
                },
            },
        )

    # Issue tokens — role stays in DB, not in the token
    admin_id = str(admin.get("id"))
    access_token, _jti = create_access_token(admin_id)
    raw_refresh, hashed_refresh = generate_refresh_token()

    await store_refresh_token_rest(admin_id, hashed_refresh)

    return ok(
        data=TokenResponse(
            access_token=access_token,
            refresh_token=raw_refresh,
            token_type="bearer",
            role=admin.get("role"),   # for UI display only — backend never trusts this
            name=admin.get("name"),
        ).model_dump(),
        message="Login successful",
    )


@router.post("/refresh")
async def refresh_access_token(payload: RefreshRequest, db: AsyncSession = Depends(get_db)):
    """
    Exchange a valid refresh token for a new access token.
    Issues a new refresh token as well (token rotation — old one is invalidated).
    """
    admin = await verify_refresh_token(db, payload.refresh_token)

    # Rotate: delete old refresh token, issue a new one
    await revoke_refresh_token(db, payload.refresh_token)
    new_access, _jti = create_access_token(str(admin.id))
    new_raw_refresh, new_hashed_refresh = generate_refresh_token()
    await store_refresh_token(db, admin.id, new_hashed_refresh)
    await db.commit()

    return ok(
        data=TokenResponse(
            access_token=new_access,
            refresh_token=new_raw_refresh,
            token_type="bearer",
            role=admin.role,
            name=admin.name,
        ).model_dump(),
        message="Token refreshed",
    )


@router.post("/logout")
async def logout(admin=Depends(get_current_admin), db: AsyncSession = Depends(get_db)):
    """
    Invalidate the current access token (via JTI blacklist) and delete the refresh token.
    After this call, neither token can be used.
    """
    from sqlalchemy import delete
    from app.models.refresh_token import RefreshToken

    # Blacklist current access token's JTI until its natural expiry
    await blacklist_jti(db, admin._jti, admin._token_exp)

    # Delete all active refresh tokens for this admin
    await db.execute(delete(RefreshToken).where(RefreshToken.admin_id == admin.id))
    await db.commit()

    return ok(message="Logged out successfully")


from app.models.student import Student
from pydantic import BaseModel

student_auth_router = APIRouter(prefix="/api/auth", tags=["StudentAuth"])

class StudentForgotPasswordRequest(BaseModel):
    email: str

class StudentResetPasswordRequest(BaseModel):
    token: str
    password: str

from fastapi.responses import JSONResponse

@student_auth_router.post("/forgot-password")
async def forgot_password(body: StudentForgotPasswordRequest, db: AsyncSession = Depends(get_db)):
    import time
    import smtplib
    import httpx
    from email.mime.text import MIMEText
    from email.mime.multipart import MIMEMultipart
    from jose import jwt
    from app.core.config import settings

    email_clean = body.email.strip().lower()

    if not email_clean.endswith(_allowed_email_suffix()):
        return JSONResponse(
            status_code=200,
            content={
                "success": False,
                "error": {
                    "code": "AUTH_FORBIDDEN",
                    "message": f"Only {_allowed_email_suffix()} email addresses are permitted.",
                },
            },
        )

    # 1. Check if student exists in local DB
    student_res = await db.execute(select(Student).where(Student.email == email_clean))
    student = student_res.scalars().first()
    if not student:
        return JSONResponse(
            status_code=200,
            content={
                "success": False,
                "error": {
                    "code": "AUTH_NOT_FOUND",
                    "message": "No student found with this email.",
                },
            },
        )

    # 2. Generate signed token (15 mins expiry)
    JWT_SECRET = settings.SECRET_KEY
    JWT_ALGORITHM = getattr(settings, "ALGORITHM", "HS256")
    expiration = int(time.time() + 900)
    token_payload = {"email": email_clean, "portal": "student", "exp": expiration}
    token = jwt.encode(token_payload, JWT_SECRET, algorithm=JWT_ALGORITHM)

    # Send email
    student_base_url = (os.getenv("STUDENT_PORTAL_URL") or getattr(settings, "STUDENT_PORTAL_URL", None) or "https://student.procksi.in").rstrip("/")
    reset_link = f"{student_base_url}/student/reset-password?token={token}"
    html_content = f"""
<div style="font-family: Arial, sans-serif; max-width: 600px; margin: auto; padding: 20px; border: 1px solid #e0e0e0; border-radius: 10px; background-color: #ffffff;">
    <div style="text-align: center; margin-bottom: 20px;">
        <h2 style="color: #4f46e5; margin: 0;">Procksi</h2>
        <p style="color: #6b7280; font-size: 14px; margin: 5px 0 0 0;">Project Management System (Student Portal)</p>
    </div>
    <div style="padding: 20px; background-color: #f9fafb; border-radius: 8px;">
        <h3 style="color: #111827; margin-top: 0;">Password Reset Request</h3>
        <p style="color: #374151; font-size: 16px; line-height: 1.5;">You requested to reset your password for the Student Portal of Procksi. Click the button below to set a new password. This link is valid for 15 minutes.</p>
        <div style="text-align: center; margin: 30px 0;">
            <a href="{reset_link}" style="background-color: #4f46e5; color: #ffffff; padding: 12px 24px; border-radius: 6px; text-decoration: none; font-weight: bold; font-size: 16px; display: inline-block;">Reset Password</a>
        </div>
        <p style="color: #6b7280; font-size: 14px; line-height: 1.5;">If the button doesn't work, copy and paste this link in your browser:</p>
        <p style="color: #4f46e5; font-size: 13px; word-break: break-all; margin: 5px 0 0 0;">{reset_link}</p>
    </div>
    <div style="text-align: center; margin-top: 20px; color: #9ca3af; font-size: 12px;">
        <p style="margin: 0;">This is an automated email. Please do not reply.</p>
    </div>
</div>
    """

    mail_server = (settings.MAIL_SERVER or "smtp.gmail.com").strip()
    mail_port = int(settings.MAIL_PORT or 587)
    mail_username = (settings.MAIL_USERNAME or os.getenv("MASTER_ADMIN_EMAIL") or "").strip()
    mail_password = (settings.MAIL_PASSWORD or os.getenv("MAIL_PASSWORD") or "").replace(" ", "").strip()
    mail_from = (settings.MAIL_FROM or mail_username).strip()

    msg = MIMEMultipart("alternative")
    msg["Subject"] = "Student Password Reset - Project Management System"
    msg["From"] = mail_from
    msg["To"] = email_clean
    msg.attach(MIMEText(html_content, "html"))

    try:
        with smtplib.SMTP(mail_server, mail_port, timeout=15) as server:
            server.starttls()
            server.login(mail_username, mail_password)
            server.sendmail(mail_from, [email_clean], msg.as_string())
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail={
                "success": False,
                "error": {
                    "code": "SMTP_ERROR",
                    "message": f"Failed to send email: {str(e)}",
                },
            },
        )

    return {"success": True, "message": "Password reset link has been sent to your email."}


@student_auth_router.post("/reset-password")
async def reset_password(body: StudentResetPasswordRequest, db: AsyncSession = Depends(get_db)):
    from jose import jwt, JWTError
    import httpx
    from app.core.config import settings

    JWT_SECRET = settings.SECRET_KEY
    JWT_ALGORITHM = getattr(settings, "ALGORITHM", "HS256")

    try:
        token_payload = jwt.decode(body.token, JWT_SECRET, algorithms=[JWT_ALGORITHM])
        email = token_payload.get("email")
        portal = token_payload.get("portal")
        
        if not email or portal != "student":
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail={
                    "success": False,
                    "error": {
                        "code": "AUTH_INVALID_TOKEN",
                        "message": "Invalid token details.",
                    },
                },
            )

        # 1. Search for user ID in Supabase Auth (checking pages) or provision if missing
        users_url = f"{settings.SUPABASE_URL.rstrip('/')}/auth/v1/admin/users"
        headers = {
            "apikey": settings.SUPABASE_SERVICE_KEY,
            "Authorization": f"Bearer {settings.SUPABASE_SERVICE_KEY}",
        }

        user_id = None
        page = 1
        per_page = 50
        
        async with httpx.AsyncClient(timeout=10.0) as client:
            while page <= 10:
                try:
                    resp = await client.get(f"{users_url}?page={page}&per_page={per_page}", headers=headers)
                    if not resp.is_success:
                        break
                    users_data = resp.json()
                    users_list = users_data.get("users", []) if isinstance(users_data, dict) else (users_data if isinstance(users_data, list) else [])
                    if not users_list:
                        break
                    for u in users_list:
                        u_email = u.get("email", "")
                        if u_email and u_email.strip().lower() == email.strip().lower():
                            user_id = u.get("id")
                            break
                    if user_id:
                        break
                    page += 1
                except Exception:
                    break

            if user_id:
                # Update existing user's password in Supabase Auth
                update_url = f"{users_url}/{user_id}"
                resp = await client.put(update_url, headers=headers, json={"password": body.password})
                resp.raise_for_status()
            else:
                # Provision account in Supabase Auth with the new password
                create_payload = {
                    "email": email.strip().lower(),
                    "password": body.password,
                    "email_confirm": True,
                }
                resp = await client.post(users_url, headers=headers, json=create_payload)
                resp.raise_for_status()

        return {"success": True, "message": "Password has been reset successfully. You can now log in."}

    except JWTError:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail={
                "success": False,
                "error": {
                    "code": "AUTH_EXPIRED_TOKEN",
                    "message": "Invalid or expired reset link.",
                },
            },
        )
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail={
                "success": False,
                "error": {
                    "code": "AUTH_UPDATE_FAILED",
                    "message": f"Failed to reset password: {str(e)}",
                },
            },
        )


class StudentSignupRequest(BaseModel):
    email: str
    password: str


@student_auth_router.post("/signup")
async def signup(body: StudentSignupRequest, db: AsyncSession = Depends(get_db)):
    import httpx
    from app.core.config import settings

    email_clean = body.email.strip().lower()

    if not email_clean.endswith(_allowed_email_suffix()):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail={
                "success": False,
                "error": {
                    "code": "INVALID_DOMAIN",
                    "message": f"Only {_allowed_email_suffix()} email addresses are permitted.",
                },
            },
        )

    # 1. Verify that student exists in the students table
    student_res = await db.execute(select(Student).where(Student.email == email_clean))
    student = student_res.scalars().first()
    if not student:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail={
                "success": False,
                "error": {
                    "code": "STUDENT_NOT_PRE_REGISTERED",
                    "message": "Your email is not registered in the system database. Please contact your coordinator to request upload.",
                },
            },
        )

    # 2. Check if student already exists in Supabase Auth (GoTrue)
    users_url = f"{settings.SUPABASE_URL.rstrip('/')}/auth/v1/admin/users"
    headers = {
        "apikey": settings.SUPABASE_SERVICE_KEY,
        "Authorization": f"Bearer {settings.SUPABASE_SERVICE_KEY}",
    }

    try:
        # Paginated: GoTrue caps a page at 50 users, so an unpaginated read stopped
        # detecting existing accounts once the project grew past the first page —
        # the same loop reset_password already uses.
        users_list_all = []
        async with httpx.AsyncClient(timeout=10.0) as client:
            for page in range(1, 11):
                resp = await client.get(users_url, headers=headers, params={"page": page, "per_page": 200})
                resp.raise_for_status()
                page_users = (resp.json() or {}).get("users", [])
                if not page_users:
                    break
                users_list_all.extend(page_users)
        users_data = {"users": users_list_all}
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail={
                "success": False,
                "error": {
                    "code": "AUTH_SERVICE_UNAVAILABLE",
                    "message": f"Auth service connection failure: {str(e)}",
                },
            },
        )

    users_list = users_data.get("users", [])
    user_id = None
    for u in users_list:
        u_email = u.get("email", "")
        if u_email and u_email.strip().lower() == email_clean:
            user_id = u.get("id")
            break

    if user_id:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail={
                "success": False,
                "error": {
                    "code": "AUTH_ALREADY_EXISTS",
                    "message": "An authentication account already exists for this email. Please log in or use Forgot Password.",
                },
            },
        )

    # 3. Provision the student account in Supabase Auth.
    #
    # This used to call the *admin* create endpoint with email_confirm: True, which
    # suppresses verification entirely. Membership of the pre-registration roster is
    # not proof of mailbox ownership, so anyone who could guess an institutional
    # address — the format is predictable — could claim a classmate's account before
    # they onboarded, and the real student was then permanently locked out.
    #
    # The public signup endpoint creates an *unconfirmed* user and sends Supabase's
    # confirmation mail, so the account only becomes usable once the person holding
    # the mailbox follows the link.
    signup_url = f"{settings.SUPABASE_URL.rstrip('/')}/auth/v1/signup"
    signup_headers = {"apikey": settings.SUPABASE_KEY or settings.SUPABASE_SERVICE_KEY}
    try:
        create_payload = {
            "email": email_clean,
            "password": body.password,
        }
        async with httpx.AsyncClient(timeout=10.0) as client:
            resp = await client.post(signup_url, headers=signup_headers, json=create_payload)
            resp.raise_for_status()
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail={
                "success": False,
                "error": {
                    "code": "AUTH_PROVISION_FAILED",
                    "message": f"Failed to provision student login: {str(e)}",
                },
            },
        )

    try:
        from app.services.email_service import build_professional_email_wrapper, send_html_email_async
        student_base_url = (os.getenv("STUDENT_PORTAL_URL") or getattr(settings, "STUDENT_PORTAL_URL", None) or "https://student.procksi.in").rstrip("/")
        subject = "Confirm your Procksi account"
        body = f"""
        <p>A student account was created for this address on Procksi.</p>
        <p><strong>One step remains:</strong> open the confirmation email Supabase has just sent you and click the link. Your account becomes active once confirmed.</p>
        <p>If you did not request this, you can ignore both emails — the account cannot be used until the link is followed.</p>
        """
        html_body = build_professional_email_wrapper(
            title="Confirm Your Account",
            recipient_greeting=f"Dear {student.name or 'Student'},",
            main_html=body,
            badge_text="ACTION REQUIRED",
            action_text="Go to Student Portal",
            action_url=f"{student_base_url}/student/login"
        )
        send_html_email_async(subject, [email_clean], html_body)
    except Exception as mail_err:
        print(f"Failed to send signup welcome email: {mail_err}")

    return {
        "success": True,
        "message": "Almost done — check your inbox and click the confirmation link to activate your account.",
        "requires_email_confirmation": True,
    }


@student_auth_router.get("/verify")
async def verify_registered(authorization: str = Header(default="")):
    """Tell the frontend whether the signed-in account is a pre-registered student.

    The student App.jsx calls this right after a Google sign-in (the OAuth gate).

    Design note — why this always answers with 200 + a true/false flag:
    The frontend must be able to tell "this account is genuinely NOT a student"
    apart from "the check couldn't run" (server down, route missing, bad token).
    If we signalled "not a student" with an error status, a missing route or an
    outage would look identical to a real rejection and could lock people out.
    So instead:
      * token OK + e-mail found in students  -> 200 {registered: true}
      * token OK + e-mail NOT found          -> 200 {registered: false}   <-- the only case the gate blocks on
      * token missing/invalid                -> 401
      * Supabase / DB unreachable            -> 503
    The frontend only signs the user out on an explicit {registered: false};
    everything else it lets through (fails open).

    The e-mail is taken from the verified token, never from the client, so it
    can't be spoofed by sending someone else's address.
    """
    import httpx
    from app.core.config import settings
    from app.core.supabase_client import supabase_client

    # 1. Pull the bearer token out of the Authorization header.
    token = authorization[7:].strip() if authorization.lower().startswith("bearer ") else ""
    if not token:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Missing bearer token")

    # 2. Verify the token with Supabase and read the account's e-mail from it.
    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            resp = await client.get(
                f"{settings.SUPABASE_URL.rstrip('/')}/auth/v1/user",
                headers={"Authorization": f"Bearer {token}", "apikey": settings.SUPABASE_KEY},
            )
    except Exception as e:
        # Couldn't reach Supabase — report an outage so the frontend fails open.
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail={"success": False, "error": {"code": "AUTH_SERVICE_UNAVAILABLE", "message": str(e)}},
        )
    if resp.status_code != 200:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid or expired session")
    email = (resp.json() or {}).get("email")
    if not email:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid or expired session")

    # 3. Is that e-mail in the students master data? (Supabase REST — works even
    #    on networks that block the direct Postgres port.)
    try:
        student = await supabase_client.get_student_by_email(email)
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail={"success": False, "error": {"code": "DB_UNAVAILABLE", "message": str(e)}},
        )

    # Found = registered. (An inactive student still counts as registered here;
    # the gate only cares whether the account belongs to a real student.)
    return ok(data={"registered": bool(student), "email": email}, message="ok")
