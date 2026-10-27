import os
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, status

from app.deps import get_current_user
from app.supabase_client import get_supabase_service
from app.schemas import LoginRequest, SignupRequest, Token, UserPublic
from app.security import create_access_token, verify_password, hash_password


def _allowed_email_suffix() -> str:
    """'@' + ALLOWED_EMAIL_DOMAIN. Unset rejects every address (fail closed)."""
    return "@" + os.getenv("ALLOWED_EMAIL_DOMAIN", "").strip().lstrip("@").lower()


router = APIRouter(prefix="/auth", tags=["auth"])


def normalize_email(value) -> str:
    """Canonical form used for EVERY email comparison and every stored email.

    The student guard below decides who may register on this portal by looking
    the address up in the `students` table. That lookup is an exact match, so it
    must be fed a canonical value: previously the domain check lowercased the
    address but the lookup used the raw input, so a student could register as a
    panel member just by capitalising a letter of their own email.

    Every address already in students/mentors is stored stripped + lowercase, so
    normalising the input makes the exact match both correct and complete.
    """
    return str(value or "").strip().lower()


def _get_mentor_name(client, panel_id: str | None) -> str | None:
    """Fetch the display name for a panel/mentor from the panels table."""
    if not panel_id:
        return None
    try:
        res = client.table("panels").select("name").eq("id", panel_id).execute()
        if res.data:
            return res.data[0]["name"]
    except Exception:
        pass
    return None


@router.post("/signup")
def signup(body: SignupRequest):
    email_clean = normalize_email(body.email)
    if not email_clean.endswith(_allowed_email_suffix()):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=f"Only {_allowed_email_suffix()} email addresses are permitted."
        )

    client = get_supabase_service()
    if client is None:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Supabase not configured")

    # 1. Check if the email belongs to a student
    student_res = client.table("students").select("email").eq("email", email_clean).execute()
    if student_res.data:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Students are not allowed to register or log in on this portal.",
        )

    # 2. Check if a mentor or user with the same email already exists
    mentor_res = client.table("mentors").select("email").eq("email", email_clean).execute()
    user_res = client.table("users").select("email").eq("email", email_clean).execute()
    if mentor_res.data or user_res.data:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="An account with this email already exists.",
        )

    # 3. Generate the next sequential mentor ID of form M-XXX
    res = client.table("mentors").select("id").execute()
    mentor_ids = [row["id"] for row in res.data or []]
    max_num = 0
    for m_id in mentor_ids:
        if m_id and m_id.startswith("M-"):
            try:
                num = int(m_id.split("-")[1])
                if num > max_num:
                    max_num = num
            except (ValueError, IndexError):
                pass
    next_id = f"M-{max_num + 1:03d}"

    # 4. Create the new inactive mentor
    hashed = hash_password(body.password)
    insert_res = client.table("mentors").insert({
        "id": next_id,
        "name": body.name,
        "email": email_clean,
        "phone": body.phone,
        "password_hash": hashed,
        "domains": body.domains,
        "skills": [],
        "experience_years": 0,
        "max_teams": 3,
        "current_teams": 0,
        "is_active": False,
    }).execute()

    if not insert_res.data:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to register account."
        )

    return {
        "success": True,
        "status": "pending",
        "message": "Your registration is pending administrator approval. You can log in once approved."
    }


@router.post("/login", response_model=Token)
def login(body: LoginRequest):
    email_clean = normalize_email(body.email)
    if not email_clean.endswith(_allowed_email_suffix()):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=f"Only {_allowed_email_suffix()} email addresses are permitted."
        )

    client = get_supabase_service()
    if client is None:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Supabase not configured")

    # 1. Check if email belongs to a student
    student_res = client.table("students").select("email").eq("email", email_clean).execute()
    if student_res.data:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Students are not allowed to log in to this portal."
        )

    # 2. Fetch users and mentors data
    res_user = client.table("users").select("*").eq("email", email_clean).execute()
    user = res_user.data[0] if res_user.data else None

    res_mentor = client.table("mentors").select("*").eq("email", email_clean).execute()
    mentor = res_mentor.data[0] if res_mentor.data else None

    if not user and not mentor:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid credentials")

    # 3. If mentor is found
    if mentor:
        # Check active status
        if not mentor.get("is_active"):
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Your registration is pending administrator approval. You can log in once approved."
            )

        # Verify password
        is_verified = False
        if mentor.get("password_hash") and verify_password(body.password, mentor["password_hash"]):
            is_verified = True
        elif user and user.get("hashed_password") and verify_password(body.password, user["hashed_password"]):
            is_verified = True

        if not is_verified:
            raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid credentials")

        # Get panel_id: use existing user panel_id if available, otherwise match by panel name
        panel_id = user["panel_id"] if (user and user.get("panel_id")) else None
        if not panel_id:
            try:
                panel_res = client.table("panels").select("id").eq("name", mentor["name"]).execute()
                if panel_res.data:
                    panel_id = panel_res.data[0]["id"]
            except Exception:
                pass

        # Symmetrically auto-provision or sync user record
        if not user:
            insert_res = client.table("users").insert({
                "email": mentor["email"],
                "hashed_password": mentor.get("password_hash") or hash_password(body.password),
                "role": "mentor",
                "panel_id": panel_id
            }).execute()
            user = insert_res.data[0] if insert_res.data else None
        else:
            # Sync password and panel_id if they differ
            update_data = {}
            if mentor.get("password_hash") and user.get("hashed_password") != mentor.get("password_hash"):
                update_data["hashed_password"] = mentor["password_hash"]
            if user.get("panel_id") != panel_id:
                update_data["panel_id"] = panel_id
            
            if update_data:
                update_res = client.table("users").update(update_data).eq("email", mentor["email"]).execute()
                if update_res.data:
                    user = update_res.data[0]

    # 4. If normal user (not mentor)
    else:
        if not verify_password(body.password, user["hashed_password"]):
            raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid credentials")

    mentor_name = mentor["name"] if mentor else _get_mentor_name(client, user["panel_id"])

    token = create_access_token(
        sub=user["email"],
        extra={"role": user["role"], "panel_id": user["panel_id"]},
    )
    return Token(
        access_token=token,
        panel_id=user["panel_id"],
        role=user["role"],
        mentor_name=mentor_name,
    )


@router.get("/me", response_model=UserPublic)
def me(current: Annotated[dict, Depends(get_current_user)]):
    client = get_supabase_service()
    mentor_name = _get_mentor_name(client, current.get("panel_id")) if client else None
    return UserPublic(
        email=current["email"],
        role=current["role"],
        panel_id=current["panel_id"],
        mentor_name=mentor_name,
    )


from pydantic import BaseModel

class ForgotPasswordRequest(BaseModel):
    email: str

class ResetPasswordRequest(BaseModel):
    token: str
    password: str

@router.post("/forgot-password")
def forgot_password(body: ForgotPasswordRequest):
    email_clean = normalize_email(body.email)
    if not email_clean.endswith(_allowed_email_suffix()):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=f"Only {_allowed_email_suffix()} email addresses are permitted."
        )
    import os
    import time
    import smtplib
    from email.mime.text import MIMEText
    from email.mime.multipart import MIMEMultipart
    from jose import jwt
    from app.config import settings
    
    client = get_supabase_service()
    if client is None:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Supabase not configured")


    # 1. Check if email belongs to a student
    student_res = client.table("students").select("email").eq("email", email_clean).execute()
    if student_res.data:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Students cannot reset password via the Panel portal."
        )

    # 2. Check if a mentor or user with the same email exists
    mentor_res = client.table("mentors").select("email").eq("email", email_clean).execute()
    user_res = client.table("users").select("email").eq("email", email_clean).execute()
    
    if not mentor_res.data and not user_res.data:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="No account found with this email."
        )

    # 3. Generate signed token (15 mins expiry)
    JWT_SECRET = settings.secret_key
    JWT_ALGORITHM = getattr(settings, "algorithm", "HS256")
    expiration = int(time.time() + 900)
    token_payload = {"email": email_clean, "portal": "panel", "exp": expiration}
    token = jwt.encode(token_payload, JWT_SECRET, algorithm=JWT_ALGORITHM)

    # Send email
    panel_base_url = (os.getenv("PANEL_PORTAL_URL") or getattr(settings, "panel_portal_url", None) or "").rstrip("/")
    reset_link = f"{panel_base_url}/reset-password?token={token}"
    html_content = f"""
<div style="font-family: Arial, sans-serif; max-width: 600px; margin: auto; padding: 20px; border: 1px solid #e0e0e0; border-radius: 10px; background-color: #ffffff;">
    <div style="text-align: center; margin-bottom: 20px;">
        <h2 style="color: #10b981; margin: 0;">Procksi</h2>
        <p style="color: #6b7280; font-size: 14px; margin: 5px 0 0 0;">Project Management System (Panel Portal)</p>
    </div>
    <div style="padding: 20px; background-color: #f9fafb; border-radius: 8px;">
        <h3 style="color: #111827; margin-top: 0;">Password Reset Request</h3>
        <p style="color: #374151; font-size: 16px; line-height: 1.5;">You requested to reset your password for the Panel/Mentor Portal of Procksi. Click the button below to set a new password. This link is valid for 15 minutes.</p>
        <div style="text-align: center; margin: 30px 0;">
            <a href="{reset_link}" style="background-color: #10b981; color: #ffffff; padding: 12px 24px; border-radius: 6px; text-decoration: none; font-weight: bold; font-size: 16px; display: inline-block;">Reset Password</a>
        </div>
        <p style="color: #6b7280; font-size: 14px; line-height: 1.5;">If the button doesn't work, copy and paste this link in your browser:</p>
        <p style="color: #10b981; font-size: 13px; word-break: break-all; margin: 5px 0 0 0;">{reset_link}</p>
    </div>
    <div style="text-align: center; margin-top: 20px; color: #9ca3af; font-size: 12px;">
        <p style="margin: 0;">This is an automated email. Please do not reply.</p>
    </div>
</div>
    """

    mail_server = (os.getenv("MAIL_SERVER") or getattr(settings, "mail_server", None) or "smtp.gmail.com").strip()
    mail_port = int(os.getenv("MAIL_PORT") or getattr(settings, "mail_port", None) or 587)
    # Falls back to settings: pydantic loads .env into the settings object but
    # does NOT populate os.environ, so a bare os.getenv() is empty when the
    # value comes from a .env file. An empty username makes Gmail answer 535,
    # which is indistinguishable from a wrong password.
    mail_username = (os.getenv("MAIL_USERNAME") or getattr(settings, "mail_username", None) or os.getenv("MASTER_ADMIN_EMAIL") or "").strip()
    mail_password = (os.getenv("MAIL_PASSWORD") or getattr(settings, "mail_password", None) or "").replace(" ", "").strip()
    mail_from = (os.getenv("MAIL_FROM") or mail_username).strip()

    msg = MIMEMultipart("alternative")
    msg["Subject"] = "Panel/Mentor Password Reset - Project Management System"
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
            detail=f"Failed to send email: {str(e)}"
        )

    return {"success": True, "message": "Password reset link has been sent to your email."}


@router.post("/reset-password")
def reset_password(body: ResetPasswordRequest):
    from jose import jwt, JWTError
    from app.config import settings
    
    client = get_supabase_service()
    if client is None:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Supabase not configured")

    JWT_SECRET = settings.secret_key
    JWT_ALGORITHM = getattr(settings, "algorithm", "HS256")

    try:
        token_payload = jwt.decode(body.token, JWT_SECRET, algorithms=[JWT_ALGORITHM])
        email = token_payload.get("email")
        portal = token_payload.get("portal")
        
        if not email or portal != "panel":
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid token details.")

        hashed_pass = hash_password(body.password)

        # Update in users table if exists
        user_res = client.table("users").select("email").eq("email", email).execute()
        if user_res.data:
            client.table("users").update({"hashed_password": hashed_pass}).eq("email", email).execute()

        # Update in mentors table if exists
        mentor_res = client.table("mentors").select("email").eq("email", email).execute()
        if mentor_res.data:
            client.table("mentors").update({"password_hash": hashed_pass}).eq("email", email).execute()

        return {"success": True, "message": "Password has been reset successfully. You can now log in."}

    except JWTError:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid or expired reset link.")
    except Exception as e:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=f"Failed to reset password: {str(e)}")

