import os
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, text

from app.api.deps import get_db, get_current_mentor
from app.core import rest_db
from app.core.auth import (
    hash_password,
    verify_password,
    create_access_token,
    generate_refresh_token,
    store_refresh_token,
    store_refresh_token_rest,
    verify_refresh_token,
    revoke_refresh_token,
    blacklist_jti,
)
from app.models.mentor import Mentor
from app.models.student import Student
from app.models.user import User
from app.schemas.auth import MentorLogin, MentorSignup, RefreshRequest, TokenResponse
from app.schemas.common import ok


def _allowed_email_suffix() -> str:
    """'@' + ALLOWED_EMAIL_DOMAIN. Unset rejects every address (fail closed)."""
    return "@" + os.getenv("ALLOWED_EMAIL_DOMAIN", "").strip().lstrip("@").lower()


router = APIRouter(prefix="/auth", tags=["Auth"])


def normalize_email(value) -> str:
    """Canonical form used for EVERY email comparison and every stored email.

    The student/mentor guards below decide who may register on this portal by
    looking the address up in the `students` table. That lookup is an exact
    match, so it must be fed a canonical value: previously the domain check
    lowercased the address but the lookup used the raw input, which meant a
    student could register as a mentor just by capitalising a letter of their
    own email — 'Samarth.Verma_cs.aiml24@example.edu' passed the domain rule and
    missed the students table entirely.

    Every address already in students/mentors is stored stripped + lowercase, so
    normalising the input makes the exact match both correct and complete.
    """
    return str(value or "").strip().lower()


PENDING_APPROVAL_MESSAGE = (
    "Your registration is pending administrator approval. You can log in once approved."
)


def _forbidden(message: str) -> HTTPException:
    return HTTPException(
        status_code=status.HTTP_403_FORBIDDEN,
        detail={"success": False, "error": {"code": "AUTH_FORBIDDEN", "message": message}},
    )


def _account_not_found() -> HTTPException:
    return HTTPException(
        status_code=status.HTTP_404_NOT_FOUND,
        detail={
            "success": False,
            "error": {"code": "AUTH_NOT_FOUND", "message": "No account found with this email."},
        },
    )


async def assert_resettable_account(db: AsyncSession, email: str) -> None:
    """Guard the password-reset flow, or raise.

    Same two questions login asks — is this a student, and does the account
    exist — and, like signup, answered over PostgREST when it is configured.
    The SQLAlchemy-only version turned a blocked tcp/5432 into a 60-second
    500 before the reset mail was ever attempted.
    """
    if rest_db.is_configured():
        try:
            if await rest_db.select_one("students", columns="id", eq={"email": email}):
                raise _forbidden("Students cannot reset password via the Mentor portal.")
            mentor = await rest_db.select_one("mentors", columns="id", eq={"email": email})
            user = await rest_db.select_one("users", columns="id", eq={"email": email})
            if not mentor and not user:
                raise _account_not_found()
            return
        except HTTPException:
            raise
        except Exception as rest_err:
            print(f"REST account lookup failed, falling back to DB: {rest_err}")

    student_res = await db.execute(select(Student).where(Student.email == email))
    if student_res.scalars().first():
        raise _forbidden("Students cannot reset password via the Mentor portal.")

    mentor_res = await db.execute(select(Mentor).where(Mentor.email == email))
    user_res = await db.execute(select(User).where(User.email == email))
    if not mentor_res.scalar_one_or_none() and not user_res.scalar_one_or_none():
        raise _account_not_found()


def _email_taken() -> HTTPException:
    return HTTPException(
        status_code=status.HTTP_400_BAD_REQUEST,
        detail={
            "success": False,
            "error": {
                "code": "EMAIL_ALREADY_EXISTS",
                "message": "A mentor with this email already exists",
            },
        },
    )


def next_mentor_id(existing_ids) -> str:
    """Next sequential mentor ID (M-001, M-002, ...)."""
    max_num = 0
    for m_id in existing_ids or []:
        if m_id and str(m_id).startswith("M-"):
            try:
                max_num = max(max_num, int(str(m_id).split("-")[1]))
            except (ValueError, IndexError):
                pass
    return f"M-{max_num + 1:03d}"


def _not_on_roster():
    """Signup refused because the coordinator has not uploaded this mentor."""
    return HTTPException(
        status_code=status.HTTP_403_FORBIDDEN,
        detail={
            "success": False,
            "error": {
                "code": "MENTOR_NOT_PRE_REGISTERED",
                "message": "Your email is not registered as a mentor. Please contact the project coordinator to be added.",
            },
        },
    )


def claim_mentor_row(payload, email: str) -> dict:
    """Fields a mentor supplies when claiming their uploaded roster row.

    Deliberately narrow: it sets the password and the mentor's own profile
    details, and never touches id, email or is_active. Those belong to the
    coordinator who created the row.
    """
    row = {"password_hash": hash_password(payload.password)}
    if getattr(payload, "name", None):
        row["name"] = payload.name
    if getattr(payload, "phone", None):
        row["phone"] = payload.phone
    if getattr(payload, "domains", None):
        row["domains"] = payload.domains
    return row


def new_mentor_row(mentor_id: str, payload, email: str) -> dict:
    """Column values for a self-registered mentor.

    ``is_active`` is False on purpose: registering must not grant access, only
    request it. An administrator flips this.
    """
    return {
        "id": mentor_id,
        "name": payload.name,
        # Store the canonical form, so future lookups match regardless of how
        # the address was typed at signup.
        "email": email,
        "phone": payload.phone,
        "password_hash": hash_password(payload.password),
        "domains": payload.domains,
        "skills": [],
        "experience_years": 0,
        "max_teams": 3,
        "current_teams": 0,
        "is_active": False,
    }


async def _signup_rest(payload, email: str):
    """Register over PostgREST.

    Signup used to be SQLAlchemy-only, so on any network that blocks tcp/5432
    it hung for a minute and returned 500 — nobody could register at all. The
    guards here are the same two the SQL path applies, in the same order.
    """
    if await rest_db.select_one("students", columns="id", eq={"email": email}):
        raise _forbidden("Students are not allowed to register or log in on this portal.")

    # Mentors are roster-gated, the same way students are: the coordinator
    # uploads the mentor first, and signup claims that row rather than creating
    # one. A row with no password_hash is an uploaded-but-unclaimed mentor.
    existing = await rest_db.select_one("mentors", eq={"email": email})
    if not existing:
        raise _not_on_roster()

    if existing.get("password_hash"):
        raise _email_taken()

    # Claim the roster row. is_active is left untouched: whether signing up
    # grants access is the coordinator's decision, recorded at upload time.
    await rest_db.update(
        "mentors", {"id": existing["id"]}, claim_mentor_row(payload, email)
    )
    return ok(data={"status": "pending"}, message=PENDING_APPROVAL_MESSAGE)


@router.post("/signup")
async def signup(payload: MentorSignup, db: AsyncSession = Depends(get_db)):
    """
    Register a new mentor. The account will be created with `is_active=False`
    and must be approved by an administrator before they can log in.
    """
    email = normalize_email(payload.email)
    if not email.endswith(_allowed_email_suffix()):
        raise _forbidden(f"Only {_allowed_email_suffix()} email addresses are permitted.")

    if rest_db.is_configured():
        try:
            return await _signup_rest(payload, email)
        except HTTPException:
            raise
        except Exception as rest_err:
            print(f"REST signup failed, falling back to DB: {rest_err}")

    # Check if the email belongs to a student
    student_res = await db.execute(select(Student.id).where(Student.email == email))
    if student_res.scalars().first():
        raise _forbidden("Students are not allowed to register or log in on this portal.")

    # Same roster gate as the REST path above: the mentor must already have been
    # uploaded by the coordinator, and signup claims that row. Keeping the two
    # paths identical matters — this fallback runs whenever REST is unreachable,
    # and a laxer rule here would be a way around the gate.
    result = await db.execute(select(Mentor).where(Mentor.email == email))
    existing = result.scalar_one_or_none()
    if not existing:
        raise _not_on_roster()

    if existing.password_hash:
        raise _email_taken()

    for field, value in claim_mentor_row(payload, email).items():
        setattr(existing, field, value)
    await db.commit()

    return ok(data={"status": "pending"}, message=PENDING_APPROVAL_MESSAGE)


@router.post("/login")
async def login(payload: MentorLogin, db: AsyncSession = Depends(get_db)):
    """
    Authenticate a mentor or panel member and return a short-lived access token + long-lived refresh token.
    Uses Supabase REST if configured, otherwise falls back to direct database queries.
    """
    email = normalize_email(payload.email)
    if not email.endswith(_allowed_email_suffix()):
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
    if rest_db.is_configured():
        try:
            # 1. Check if the email belongs to a student
            if await rest_db.select_one("students", columns="id", eq={"email": email}):
                raise HTTPException(
                    status_code=status.HTTP_403_FORBIDDEN,
                    detail={
                        "success": False,
                        "error": {
                            "code": "AUTH_FORBIDDEN",
                            "message": "Students are not allowed to log in to this portal.",
                        },
                    },
                )

            # 2. Check if the user is in users table (shared panel users)
            user = await rest_db.select_one("users", eq={"email": email})

            mentor = None
            if user:
                if not verify_password(payload.password, user.get("hashed_password") or ""):
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
                
                # A `users` row (shared panel account) authenticates the person,
                # but it does not make them a mentor. Mentors are roster-gated:
                # the coordinator uploads them first. This used to auto-create a
                # mentors row here, which would now be a way straight past that
                # gate, so it only ever claims an existing roster row.
                mentor = await rest_db.select_one("mentors", eq={"email": email})
                if not mentor:
                    raise _not_on_roster()

                # Keep the password in step with the shared account, so changing
                # it in one place does not lock the other out.
                if user.get("hashed_password") and mentor.get("password_hash") != user.get("hashed_password"):
                    updated = await rest_db.update(
                        "mentors", {"id": mentor["id"]},
                        {"password_hash": user.get("hashed_password")},
                    )
                    if updated:
                        mentor = updated[0]

            # 3. Check mentors table if not a users table record
            if not mentor:
                mentor = await rest_db.select_one("mentors", eq={"email": email})
                if (
                    not mentor
                    or not mentor.get("password_hash")
                    or not verify_password(payload.password, mentor["password_hash"])
                ):
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

            # 4. Check is_active status
            if not mentor.get("is_active"):
                raise HTTPException(
                    status_code=status.HTTP_403_FORBIDDEN,
                    detail={
                        "success": False,
                        "error": {
                            "code": "AUTH_PENDING_APPROVAL",
                            "message": "Your registration is pending administrator approval. You can log in once approved.",
                        },
                    },
                )

            # Issue tokens
            access_token, _jti = create_access_token(mentor["id"])
            raw_refresh, hashed_refresh = generate_refresh_token()

            try:
                await store_refresh_token_rest(mentor["id"], hashed_refresh)
            except Exception as e:
                print(f"store_refresh_token_rest failed: {e}")

            role_label = (user.get("role") or "mentor").upper() if user else "MENTOR"

            return ok(
                data={
                    "access_token": access_token,
                    "refresh_token": raw_refresh,
                    "token_type": "bearer",
                    "role": role_label,
                    "name": mentor.get("name"),
                    "user": {
                        "id": mentor.get("id"),
                        "name": mentor.get("name"),
                        "email": mentor.get("email"),
                        "domains": mentor.get("domains"),
                    }
                },
                message="Login successful",
            )
        except HTTPException:
            raise
        except Exception as rest_err:
            print(f"REST login failed, falling back to DB: {rest_err}")

    # Fallback to direct DB query using SQLAlchemy
    try:
        # 1. Check student forbidden
        st_res = await db.execute(text("SELECT id FROM students WHERE email = :email"), {"email": email})
        if st_res.first():
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail={
                    "success": False,
                    "error": {
                        "code": "AUTH_FORBIDDEN",
                        "message": "Students are not allowed to log in to this portal.",
                    },
                },
            )

        # 2. Check mentors table directly
        m_res = await db.execute(text("SELECT id, name, email, password_hash, is_active, domains FROM mentors WHERE email = :email"), {"email": email})
        m_row = m_res.mappings().first()

        if not m_row or not m_row["password_hash"] or not verify_password(payload.password, m_row["password_hash"]):
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

        if not m_row["is_active"]:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail={
                    "success": False,
                    "error": {
                        "code": "AUTH_PENDING_APPROVAL",
                        "message": "Your registration is pending administrator approval. You can log in once approved.",
                    },
                },
            )

        access_token, _jti = create_access_token(m_row["id"])
        raw_refresh, hashed_refresh = generate_refresh_token()
        try:
            await store_refresh_token(db, m_row["id"], hashed_refresh)
            await db.commit()
        except Exception as e:
            print(f"store_refresh_token DB failed: {e}")

        return ok(
            data={
                "access_token": access_token,
                "refresh_token": raw_refresh,
                "token_type": "bearer",
                "role": "MENTOR",
                "name": m_row["name"],
                "user": {
                    "id": m_row["id"],
                    "name": m_row["name"],
                    "email": m_row["email"],
                    "domains": m_row["domains"],
                }
            },
            message="Login successful",
        )
    except HTTPException:
        raise
    except Exception as db_err:
        print(f"Database authentication error: {db_err}")
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail={
                "success": False,
                "error": {
                    "code": "AUTH_INVALID_CREDENTIALS",
                    "message": "Invalid email or password or database connection timeout.",
                },
            },
        )


@router.post("/refresh")
async def refresh_access_token(payload: RefreshRequest, db: AsyncSession = Depends(get_db)):
    """
    Exchange a valid refresh token for a new access token and rotate the refresh token.
    """
    mentor = await verify_refresh_token(db, payload.refresh_token)

    # Rotate refresh token
    await revoke_refresh_token(db, payload.refresh_token)
    new_access, _jti = create_access_token(mentor.id)
    new_raw_refresh, new_hashed_refresh = generate_refresh_token()
    await store_refresh_token(db, mentor.id, new_hashed_refresh)
    await db.commit()

    return ok(
        data={
            "access_token": new_access,
            "refresh_token": new_raw_refresh,
            "token_type": "bearer",
            "role": "MENTOR",
            "name": mentor.name,
            "user": {
                "id": mentor.id,
                "name": mentor.name,
                "email": mentor.email,
                "domains": mentor.domains,
            }
        },
        message="Token refreshed",
    )


@router.post("/logout")
async def logout(mentor=Depends(get_current_mentor), db: AsyncSession = Depends(get_db)):
    """
    Invalidate current access token (blacklist) and delete the refresh token.
    """
    from sqlalchemy import delete
    from app.models.refresh_token import RefreshToken

    # Blacklist the current access token
    await blacklist_jti(db, mentor._jti, mentor._token_exp)

    # Drop the cached identity for this token. get_current_mentor consults a 30s
    # cache before any revocation logic, so without this the blacklisted token
    # would keep authenticating until that entry expired.
    from app.core.cache import invalidate
    invalidate(f"auth_mentor:{mentor.id}:{mentor._jti}")

    # Revoke all active refresh tokens for this mentor
    await db.execute(delete(RefreshToken).where(RefreshToken.mentor_id == mentor.id))
    await db.commit()

    return ok(message="Logged out successfully")


@router.get("/me")
async def get_me(mentor=Depends(get_current_mentor)):
    """
    Return the authenticated mentor's details.
    """
    return ok(
        data={
            "user": {
                "id": mentor.id,
                "name": mentor.name,
                "email": mentor.email,
                "domains": mentor.domains,
            }
        }
    )


# Approved technical/mentoring domains. Problem-statement and preference
# domains are free text and often compound (e.g. "Environmental Engineering /
# Data Science"), mixing academic disciplines with tech fields. Each stored
# value is split on "/" and only atoms on this allowlist are surfaced — academic
# disciplines and any other unrecognized terms are hidden. Keys are lowercase
# for case-insensitive matching (with a few aliases); values are the canonical
# display label. Add new mentoring domains here as they become relevant.
_ALLOWED_DOMAINS: dict[str, str] = {
    "artificial intelligence": "Artificial Intelligence",
    "ai": "Artificial Intelligence",
    "machine learning": "Machine Learning",
    "ml": "Machine Learning",
    "data science": "Data Science",
    "data analytics": "Data Analytics",
    "analytics": "Data Analytics",
    "web development": "Web Development",
    "mobile app development": "Mobile App Development",
    "cloud computing": "Cloud Computing",
    "cybersecurity": "Cybersecurity",
    "blockchain": "Blockchain",
    "devops": "DevOps",
    "iot": "IoT",
    "iot (internet of things)": "IoT",
    "internet of things": "IoT",
    "software engineering": "Software Engineering",
    "game development": "Game Development",
    "ar/vr": "AR/VR",
}


@router.get("/domains")
async def get_domains(fresh: bool = False):
    """Domains offered on the mentor signup form.

    Read from the curated `domains` catalogue. It previously derived the list
    from the distinct `domain` values on teams_validation, but that column is
    free text written by an uploaded document's `Domain:` line and by an OpenAI
    enrichment step, so it offered 116 unvalidated labels — project descriptions
    among them — and only listed a domain once a team had been allocated it.
    `?fresh=1` bypasses the TTL cache, which is what the refresh button on the
    signup page sends.

    This previously read a published Google Form CSV; that source has been
    dropped. With FORM_SHEET_CSV_URL unset it always returned [], so every
    request silently fell through to the static list below.

    That static list stays as the fallback: an empty result would leave signup
    with nothing selectable and no way to submit, which is a worse failure than
    offering a slightly stale set of domains.

    NB: called through the module (`domain_catalog.get_domains`) rather than
    imported by name, so the value is resolved per call — importing the function
    directly binds it at import time and makes it impossible to substitute.
    """
    from app.services import domain_catalog

    domains_list = await domain_catalog.get_domains(fresh=fresh)
    if not domains_list:
        domains_list = sorted(set(_ALLOWED_DOMAINS.values()), key=str.lower)
    return ok(data=domains_list)


from pydantic import BaseModel

class ForgotPasswordRequest(BaseModel):
    email: str

class ResetPasswordRequest(BaseModel):
    token: str
    password: str

@router.post("/forgot-password")
async def forgot_password(body: ForgotPasswordRequest, db: AsyncSession = Depends(get_db)):
    import time
    import smtplib
    from email.mime.text import MIMEText
    from email.mime.multipart import MIMEMultipart
    from jose import jwt
    from app.core.config import settings

    email_clean = normalize_email(body.email)

    if not email_clean.endswith(_allowed_email_suffix()):
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

    # 1-2. Students are refused; unknown addresses 404.
    await assert_resettable_account(db, email_clean)

    # 3. Generate signed token (15 mins expiry)
    JWT_SECRET = settings.SECRET_KEY
    JWT_ALGORITHM = getattr(settings, "ALGORITHM", "HS256")
    expiration = int(time.time() + 900)
    token_payload = {"email": email_clean, "portal": "mentor", "exp": expiration}
    token = jwt.encode(token_payload, JWT_SECRET, algorithm=JWT_ALGORITHM)

    # Send email
    mentor_base_url = (os.getenv("MENTOR_PORTAL_URL") or getattr(settings, "MENTOR_PORTAL_URL", None) or "").rstrip("/")
    reset_link = f"{mentor_base_url}/reset-password?token={token}"
    html_content = f"""
<div style="font-family: Arial, sans-serif; max-width: 600px; margin: auto; padding: 20px; border: 1px solid #e0e0e0; border-radius: 10px; background-color: #ffffff;">
    <div style="text-align: center; margin-bottom: 20px;">
        <h2 style="color: #4f46e5; margin: 0;">Procksi</h2>
        <p style="color: #6b7280; font-size: 14px; margin: 5px 0 0 0;">Project Management System (Mentor Portal)</p>
    </div>
    <div style="padding: 20px; background-color: #f9fafb; border-radius: 8px;">
        <h3 style="color: #111827; margin-top: 0;">Password Reset Request</h3>
        <p style="color: #374151; font-size: 16px; line-height: 1.5;">You requested to reset your password for the Mentor Portal of Procksi. Click the button below to set a new password. This link is valid for 15 minutes.</p>
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

    mail_server = (os.getenv("MAIL_SERVER") or getattr(settings, "MAIL_SERVER", None) or "smtp.gmail.com").strip()
    mail_port = int(os.getenv("MAIL_PORT") or getattr(settings, "MAIL_PORT", None) or 587)
    # Falls back to settings: pydantic loads .env into the settings object but
    # does NOT populate os.environ, so a bare os.getenv() is empty when the
    # value comes from a .env file. An empty username makes Gmail answer 535,
    # which is indistinguishable from a wrong password.
    mail_username = (os.getenv("MAIL_USERNAME") or getattr(settings, "MAIL_USERNAME", None) or os.getenv("MASTER_ADMIN_EMAIL") or "").strip()
    mail_password = (os.getenv("MAIL_PASSWORD") or getattr(settings, "MAIL_PASSWORD", None) or "").replace(" ", "").strip()
    mail_from = (os.getenv("MAIL_FROM") or mail_username).strip()

    # Without credentials smtplib fails deep inside login() with an opaque
    # message, which surfaces as a generic error and looks like the account is
    # at fault. Say plainly that the server cannot send mail.
    if not mail_username or not mail_password:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail={
                "success": False,
                "error": {
                    "code": "SMTP_NOT_CONFIGURED",
                    "message": (
                        "Email delivery is not configured on this server, so the reset "
                        "link could not be sent. Set MAIL_USERNAME and MAIL_PASSWORD, "
                        "or ask an administrator to reset the password directly."
                    ),
                },
            },
        )

    msg = MIMEMultipart("alternative")
    msg["Subject"] = "Mentor Password Reset - Project Management System"
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


@router.post("/reset-password")
async def reset_password(body: ResetPasswordRequest, db: AsyncSession = Depends(get_db)):
    from jose import jwt, JWTError
    from app.core.config import settings

    JWT_SECRET = settings.SECRET_KEY
    JWT_ALGORITHM = getattr(settings, "ALGORITHM", "HS256")

    try:
        token_payload = jwt.decode(body.token, JWT_SECRET, algorithms=[JWT_ALGORITHM])
        email = token_payload.get("email")
        portal = token_payload.get("portal")
        
        if not email or portal != "mentor":
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

        hashed_pass = hash_password(body.password)

        # Update in User table if exists
        user_res = await db.execute(select(User).where(User.email == email))
        user = user_res.scalar_one_or_none()
        if user:
            user.hashed_password = hashed_pass
            db.add(user)

        # Update in Mentor table if exists
        mentor_res = await db.execute(select(Mentor).where(Mentor.email == email))
        mentor = mentor_res.scalar_one_or_none()
        if mentor:
            mentor.password_hash = hashed_pass
            db.add(mentor)

        await db.commit()
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
                    "code": "DATABASE_ERROR",
                    "message": f"Failed to reset password: {str(e)}",
                },
            },
        )


# NOTE: the mentor-signup domain list is served by the get_domains handler
# above, which sources domains from student project preferences. The former
# Google-Form-backed duplicate handler was removed (it was unreachable — FastAPI
# matches the first route registered for a path — and the Form CSV source was
# never configured).
