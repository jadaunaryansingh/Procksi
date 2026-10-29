"""
Mentor Analytics Router
Provides admin-facing analytics endpoints for mentor activity and performance tracking
"""
from fastapi import APIRouter, Depends, HTTPException, Query, Path
from typing import Optional
from uuid import UUID
import logging

from ..schemas import (
    MentorAnalyticsListResponse,
    MentorAnalyticsDetailResponse
)
from ..middleware import get_current_user, RoleChecker, AuthUser
from ..services.mentor_analytics_service import MentorAnalyticsService
from ..database import get_supabase_admin_client

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/admin/mentor-analytics", tags=["Mentor Analytics"])


@router.get("", response_model=MentorAnalyticsListResponse, dependencies=[Depends(RoleChecker(["admin"]))])
async def get_mentor_analytics_list(
    sort_by: str = Query("last_login", description="Field to sort by"),
    sort_order: str = Query("desc", description="Sort direction: asc or desc"),
    online_status: Optional[bool] = Query(None, description="Filter by online status"),
    search: Optional[str] = Query(None, description="Search by mentor name or email"),
    page: int = Query(1, ge=1, description="Page number (1-indexed)"),
    page_size: int = Query(20, ge=1, le=100, description="Items per page"),
    current_user: AuthUser = Depends(get_current_user)
):
    """
    Get paginated list of mentors with activity and performance analytics.
    
    Admin only endpoint that returns:
    - Login/logout activity and time tracking
    - Team assignments and performance metrics
    - Sortable and filterable data
    
    Args:
        sort_by: Field to sort by (last_login, total_time_spent, weekly_time_spent, 
                 average_team_score, number_of_teams)
        sort_order: Sort direction (asc or desc)
        online_status: Filter by online status (true/false)
        search: Search by mentor name or email (case-insensitive)
        page: Page number (1-indexed)
        page_size: Items per page (max 100)
        current_user: Authenticated admin user
    
    Returns:
        MentorAnalyticsListResponse with mentors array and pagination metadata
    
    Raises:
        HTTPException 400: Invalid query parameters
        HTTPException 403: User is not an admin
        HTTPException 500: Database or calculation error
    """
    logger.info(
        f"Admin {current_user.user_id} requesting mentor analytics list: "
        f"sort_by={sort_by}, sort_order={sort_order}, page={page}"
    )
    
    try:
        # Initialize service
        supabase = get_supabase_admin_client()
        service = MentorAnalyticsService(supabase)
        
        # Get mentor list with analytics
        result = await service.get_mentor_list(
            sort_by=sort_by,
            sort_order=sort_order,
            online_status=online_status,
            search=search,
            page=page,
            page_size=page_size
        )
        
        logger.info(
            f"Successfully retrieved {len(result['mentors'])} mentors "
            f"(page {result['page']} of {result['total_pages']})"
        )
        
        return MentorAnalyticsListResponse(**result)
        
    except ValueError as e:
        # Invalid parameters
        logger.warning(f"Invalid parameters: {str(e)}")
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        # Unexpected error
        logger.error(f"Error retrieving mentor analytics: {str(e)}", exc_info=True)
        raise HTTPException(
            status_code=500,
            detail=f"Failed to retrieve mentor analytics: {str(e)}"
        )


@router.get("/{mentor_id}", response_model=MentorAnalyticsDetailResponse, dependencies=[Depends(RoleChecker(["admin"]))])
async def get_mentor_analytics_detail(
    mentor_id: UUID = Path(..., description="Mentor user ID"),
    current_user: AuthUser = Depends(get_current_user)
):
    """
    Get detailed analytics for a specific mentor.
    
    Admin only endpoint that returns:
    - Complete mentor activity summary
    - All assigned teams with batch information
    - Team rankings and performance metrics
    - Student counts per team
    
    Args:
        mentor_id: UUID of the mentor
        current_user: Authenticated admin user
    
    Returns:
        MentorAnalyticsDetailResponse with complete mentor data
    
    Raises:
        HTTPException 404: Mentor not found
        HTTPException 403: User is not an admin
        HTTPException 500: Database or calculation error
    """
    logger.info(
        f"Admin {current_user.user_id} requesting detail for mentor {mentor_id}"
    )
    
    try:
        # Initialize service
        supabase = get_supabase_admin_client()
        service = MentorAnalyticsService(supabase)
        
        # Get mentor detail
        result = await service.get_mentor_detail(mentor_id)
        
        logger.info(
            f"Successfully retrieved detail for mentor {mentor_id}: "
            f"{len(result['teams'])} teams"
        )
        
        return MentorAnalyticsDetailResponse(**result)
        
    except LookupError as e:
        # Mentor not found
        logger.warning(f"Mentor not found: {mentor_id}")
        raise HTTPException(status_code=404, detail=str(e))
    except Exception as e:
        # Unexpected error
        logger.error(
            f"Error retrieving mentor detail for {mentor_id}: {str(e)}",
            exc_info=True
        )
        raise HTTPException(
            status_code=500,
            detail=f"Failed to retrieve mentor detail: {str(e)}"
        )


@router.get("/export", dependencies=[Depends(RoleChecker(["admin"]))])
async def export_mentor_analytics(
    sort_by: str = Query("last_login", description="Field to sort by"),
    sort_order: str = Query("desc", description="Sort direction: asc or desc"),
    online_status: Optional[bool] = Query(None, description="Filter by online status"),
    search: Optional[str] = Query(None, description="Search by mentor name or email"),
    current_user: AuthUser = Depends(get_current_user)
):
    """
    Export mentor analytics data to CSV format.
    
    Admin only endpoint that exports all mentor data (no pagination) with:
    - Same filtering and sorting options as list endpoint
    - CSV format with proper headers
    - Timestamps formatted as ISO 8601
    - Null values represented as empty strings
    - Time values converted from seconds to hours
    
    Args:
        sort_by: Field to sort by (last_login, total_time_spent, weekly_time_spent, 
                 average_team_score, number_of_teams)
        sort_order: Sort direction (asc or desc)
        online_status: Filter by online status (true/false)
        search: Search by mentor name or email (case-insensitive)
        current_user: Authenticated admin user
    
    Returns:
        CSV file with Content-Type: text/csv and timestamped filename
    
    Raises:
        HTTPException 400: Invalid query parameters
        HTTPException 403: User is not an admin
        HTTPException 500: Database or export error
    """
    from fastapi.responses import Response
    from datetime import datetime
    
    logger.info(
        f"Admin {current_user.user_id} requesting mentor analytics CSV export: "
        f"sort_by={sort_by}, sort_order={sort_order}"
    )
    
    try:
        # Initialize service
        supabase = get_supabase_admin_client()
        service = MentorAnalyticsService(supabase)
        
        # Get all mentor data (no pagination)
        result = await service.get_mentor_list(
            sort_by=sort_by,
            sort_order=sort_order,
            online_status=online_status,
            search=search,
            page=1,
            page_size=10000  # Large page size to get all mentors
        )
        
        # Convert to CSV
        csv_content = service.export_to_csv(result['mentors'])
        
        # Generate timestamped filename
        timestamp = datetime.utcnow().strftime("%Y%m%d_%H%M%S")
        filename = f"mentor_analytics_{timestamp}.csv"
        
        logger.info(
            f"Successfully exported {len(result['mentors'])} mentors to CSV "
            f"({len(csv_content)} bytes)"
        )
        
        # Return CSV response with proper headers
        return Response(
            content=csv_content,
            media_type="text/csv",
            headers={
                "Content-Disposition": f'attachment; filename="{filename}"'
            }
        )
        
    except ValueError as e:
        # Invalid parameters
        logger.warning(f"Invalid parameters for export: {str(e)}")
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        # Unexpected error
        logger.error(f"Error exporting mentor analytics: {str(e)}", exc_info=True)
        raise HTTPException(
            status_code=500,
            detail=f"Failed to export mentor analytics: {str(e)}"
        )
