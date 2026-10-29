"""
Auth and Project Comments endpoints.
Note: Team management endpoints have been moved to teams.py router (Phase 2)
"""
from uuid import UUID
from fastapi import APIRouter, Depends, HTTPException, status
from typing import List

from src.api.backend.schemas import (
    AuthUserResponse,
    ProjectCommentRequest,
    ProjectCommentResponse,
)
from src.api.backend.crud import UserCRUD, ProjectCommentCRUD
from src.api.backend.utils.auth import get_current_user, AuthContext

router = APIRouter(prefix="/api", tags=["auth", "comments"])


@router.get("/auth/legacy-me", response_model=AuthUserResponse)
async def get_me(ctx: AuthContext = Depends(get_current_user)):
    """Return the authenticated user's profile and role."""
    profile = ctx.get("profile", {}) or {}
    return AuthUserResponse(
        user_id=UUID(str(ctx["user_id"])),
        email=ctx.get("email"),
        role=profile.get("role", "student"),
        full_name=profile.get("full_name"),
    )


@router.get("/projects/{project_id}/comments", response_model=List[ProjectCommentResponse])
async def list_project_comments(project_id: UUID, ctx: AuthContext = Depends(get_current_user)):
    """List comments for a project."""
    comments = ProjectCommentCRUD.list_comments(str(project_id))
    return [ProjectCommentResponse(**c) for c in comments]


@router.post("/project-comments", response_model=ProjectCommentResponse, status_code=status.HTTP_201_CREATED)
async def create_project_comment(payload: ProjectCommentRequest, ctx: AuthContext = Depends(get_current_user)):
    """Create a project comment. Author is the current user."""
    comment = ProjectCommentCRUD.add_comment(
        project_id=str(payload.project_id),
        user_id=str(ctx["user_id"]),
        comment=payload.comment,
        is_private=payload.is_private,
    )
    return ProjectCommentResponse(**comment)


@router.delete("/project-comments/{comment_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_project_comment(comment_id: UUID, ctx: AuthContext = Depends(get_current_user)):
    """Delete a comment if you are the owner or admin."""
    is_admin = ctx.get("role") == "admin"
    deleted = ProjectCommentCRUD.delete_comment(str(comment_id), str(ctx["user_id"]), is_admin=is_admin)
    if not deleted:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Comment not found or not permitted")
    return None

