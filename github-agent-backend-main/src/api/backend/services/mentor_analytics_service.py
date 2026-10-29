"""
Mentor Analytics Service for admin dashboard

This service provides analytics and performance metrics for mentors,
including activity tracking, team assignments, and performance calculations.
"""
from typing import Optional, List, Dict, Any
from datetime import datetime, timedelta
from uuid import UUID
import logging

from supabase import Client
from ..database import get_supabase_admin_client

logger = logging.getLogger(__name__)

# Cache for batch rankings (batch_id -> {team_id: rank})
# Cache entries expire after 5 minutes
_batch_rankings_cache: Dict[str, Dict[str, Any]] = {}


class MentorAnalyticsService:
    """Service for calculating mentor analytics and performance metrics"""
    
    def __init__(self, supabase_client: Optional[Client] = None):
        """
        Initialize the MentorAnalyticsService
        
        Args:
            supabase_client: Optional Supabase client instance.
                           If not provided, uses the admin client.
        """
        self.supabase = supabase_client or get_supabase_admin_client()
        logger.info("MentorAnalyticsService initialized")
    
    async def get_mentor_list(
        self,
        sort_by: str = "last_login",
        sort_order: str = "desc",
        online_status: Optional[bool] = None,
        search: Optional[str] = None,
        page: int = 1,
        page_size: int = 20
    ) -> Dict[str, Any]:
        """
        Retrieve paginated list of mentors with activity and performance data
        
        Args:
            sort_by: Field to sort by (default: "last_login")
            sort_order: Sort direction "asc" or "desc" (default: "desc")
            online_status: Filter by online status (optional)
            search: Search by mentor name or email (optional)
            page: Page number, 1-indexed (default: 1)
            page_size: Items per page, max 100 (default: 20)
        
        Returns:
            Dictionary containing:
                - mentors: List of mentor analytics items
                - total: Total count of mentors
                - page: Current page number
                - page_size: Items per page
                - total_pages: Total number of pages
        
        Raises:
            ValueError: If invalid parameters provided
        """
        import time
        start_time = time.time()
        
        logger.info(
            f"get_mentor_list called with sort_by={sort_by}, "
            f"sort_order={sort_order}, online_status={online_status}, "
            f"search={search}, page={page}, page_size={page_size}"
        )
        
        # Validate pagination parameters
        if page < 1:
            error_msg = f"Invalid page parameter: {page}. Must be >= 1"
            logger.warning(error_msg)
            raise ValueError(error_msg)
        
        if page_size < 1 or page_size > 100:
            error_msg = f"Invalid page_size parameter: {page_size}. Must be between 1 and 100"
            logger.warning(error_msg)
            raise ValueError(error_msg)
        
        try:
            # Start building the query for mentors (role='mentor' OR is_mentor=true)
            # This includes both dedicated mentors and admins with mentor access
            try:
                query = self.supabase.table("users").select(
                    "id, email, full_name, role, last_login, last_logout, is_online, total_time_spent, weekly_time_spent, week_start_date"
                ).or_("role.eq.mentor,is_mentor.eq.true")
                
                # Apply online_status filter if provided
                if online_status is not None:
                    query = query.eq("is_online", online_status)
                    logger.debug(f"Applied online_status filter: {online_status}")
                
                # Execute query to get all mentors matching filters
                response = query.execute()
                mentors = response.data
            except Exception as db_error:
                logger.error(f"Database query failed: {str(db_error)}", exc_info=True)
                from fastapi import HTTPException
                raise HTTPException(
                    status_code=503,
                    detail="Database service unavailable. Please try again later."
                )
            
            logger.debug(f"Retrieved {len(mentors)} mentors before search filter")
            
            # Apply search filter (case-insensitive) on full_name or email
            if search:
                search_lower = search.lower()
                mentors = [
                    mentor for mentor in mentors
                    if (mentor.get('full_name') and search_lower in mentor['full_name'].lower()) or
                       (mentor.get('email') and search_lower in mentor['email'].lower())
                ]
                logger.debug(f"After search filter '{search}': {len(mentors)} mentors")
            
            # Enrich each mentor with calculated fields
            # Optimization: Batch query all teams for all mentors to avoid N+1 queries
            from datetime import timezone
            current_time = datetime.now(timezone.utc)
            enriched_mentors = []
            
            # Extract all mentor IDs
            mentor_ids = [mentor['id'] for mentor in mentors]
            
            # Batch query all teams for all mentors in a single query
            teams_by_mentor = {}
            if mentor_ids:
                try:
                    all_teams_response = self.supabase.table("teams").select(
                        "id, team_name, total_score, mentor_id, batch_id"
                    ).in_("mentor_id", mentor_ids).execute()
                    
                    all_teams = all_teams_response.data
                    
                    # Group teams by mentor_id
                    for team in all_teams:
                        mentor_id = team.get('mentor_id')
                        if mentor_id not in teams_by_mentor:
                            teams_by_mentor[mentor_id] = []
                        teams_by_mentor[mentor_id].append(team)
                    
                    logger.debug(f"Batch queried {len(all_teams)} teams for {len(mentor_ids)} mentors")
                except Exception as teams_error:
                    logger.warning(f"Failed to batch query teams: {str(teams_error)}")
                    teams_by_mentor = {}
            
            # Calculate batch rankings once for all batches
            batch_rankings_cache = {}
            
            for mentor in mentors:
                try:
                    # Parse timestamps and ensure timezone-aware
                    last_login = None
                    last_logout = None
                    
                    if mentor.get('last_login'):
                        if isinstance(mentor['last_login'], str):
                            from dateutil import parser
                            last_login = parser.parse(mentor['last_login'])
                        else:
                            last_login = mentor['last_login']
                        
                        # Ensure timezone-aware
                        if last_login and last_login.tzinfo is None:
                            from datetime import timezone
                            last_login = last_login.replace(tzinfo=timezone.utc)
                    
                    if mentor.get('last_logout'):
                        if isinstance(mentor['last_logout'], str):
                            from dateutil import parser
                            last_logout = parser.parse(mentor['last_logout'])
                        else:
                            last_logout = mentor['last_logout']
                        
                        # Ensure timezone-aware
                        if last_logout and last_logout.tzinfo is None:
                            from datetime import timezone
                            last_logout = last_logout.replace(tzinfo=timezone.utc)
                    
                    # Calculate weekly time spent using accumulated value from database
                    # Parse weekly_time_spent INTERVAL from database
                    weekly_time_spent_seconds = 0
                    weekly_time_db = mentor.get('weekly_time_spent')
                    
                    if weekly_time_db:
                        # Parse PostgreSQL INTERVAL format (e.g., "01:30:00" or "2 days 01:30:00")
                        weekly_time_spent_seconds = self._parse_interval_to_seconds(weekly_time_db)
                    
                    # If user is currently online, add current session time to accumulated weekly time
                    if mentor.get('is_online', False) and last_login:
                        current_session_seconds = self.calculate_weekly_time_spent(
                            last_login=last_login,
                            last_logout=last_logout,
                            is_online=True,
                            current_time=current_time
                        )
                        weekly_time_spent_seconds += current_session_seconds
                    
                    # Convert total_time_spent to seconds
                    total_time_spent = mentor.get('total_time_spent', 0)
                    if isinstance(total_time_spent, (int, float)):
                        total_time_spent_seconds = int(total_time_spent)
                    else:
                        total_time_spent_seconds = 0
                    
                    # Get teams for this mentor from batched data
                    mentor_teams = teams_by_mentor.get(mentor['id'], [])
                    
                    # Calculate performance metrics from batched team data
                    teams_with_scores = [
                        team for team in mentor_teams 
                        if team.get('total_score') is not None
                    ]
                    
                    # Calculate average team score
                    average_team_score = None
                    best_performing_team = None
                    worst_performing_team = None
                    
                    if teams_with_scores:
                        total_score = sum(team['total_score'] for team in teams_with_scores)
                        average_team_score = total_score / len(teams_with_scores)
                        
                        # Sort teams by score descending, then by team_id ascending for deterministic tie-breaking
                        sorted_teams = sorted(
                            teams_with_scores,
                            key=lambda t: (-t['total_score'], t['id'])
                        )
                        
                        # Best performing team
                        best_team = sorted_teams[0]
                        best_performing_team = {
                            'team_id': best_team['id'],
                            'team_name': best_team['team_name'],
                            'score': best_team['total_score']
                        }
                        
                        # Worst performing team
                        worst_sorted = sorted(
                            teams_with_scores,
                            key=lambda t: (t['total_score'], t['id'])
                        )
                        worst_team = worst_sorted[0]
                        worst_performing_team = {
                            'team_id': worst_team['id'],
                            'team_name': worst_team['team_name'],
                            'score': worst_team['total_score']
                        }
                    
                    # Calculate teams in top 10
                    teams_in_top_10 = 0
                    if teams_with_scores:
                        # Group teams by batch_id
                        teams_by_batch = {}
                        for team in teams_with_scores:
                            batch_id = team['batch_id']
                            if batch_id not in teams_by_batch:
                                teams_by_batch[batch_id] = []
                            teams_by_batch[batch_id].append(team)
                        
                        # Calculate rankings for each batch and count top 10 teams
                        for batch_id, batch_teams in teams_by_batch.items():
                            # Get or calculate rankings for this batch
                            if batch_id not in batch_rankings_cache:
                                try:
                                    batch_uuid = UUID(batch_id) if isinstance(batch_id, str) else batch_id
                                    rankings = await self.calculate_team_rankings(batch_uuid)
                                    batch_rankings_cache[batch_id] = rankings
                                except Exception as rank_error:
                                    logger.warning(f"Failed to calculate rankings for batch {batch_id}: {str(rank_error)}")
                                    batch_rankings_cache[batch_id] = {}
                            
                            rankings = batch_rankings_cache[batch_id]
                            
                            # Count how many of mentor's teams in this batch are in top 10
                            for team in batch_teams:
                                team_uuid = UUID(team['id']) if isinstance(team['id'], str) else team['id']
                                rank = rankings.get(team_uuid)
                                
                                if rank is not None and rank <= 10:
                                    teams_in_top_10 += 1
                    
                    # Determine actual online status: if mentor is marked online but session has timed out, mark as offline
                    # Session timeout is 30 minutes of inactivity
                    is_actually_online = mentor.get('is_online', False)
                    SESSION_TIMEOUT_MINUTES = 30
                    
                    if is_actually_online and last_login:
                        # Check if session has been idle (no activity for SESSION_TIMEOUT_MINUTES)
                        last_activity = last_logout if last_logout else last_login
                        if last_activity:
                            time_since_activity = current_time - last_activity
                            if time_since_activity > timedelta(minutes=SESSION_TIMEOUT_MINUTES):
                                # Session timed out - mark as offline
                                is_actually_online = False
                                logger.info(
                                    f"Marking mentor {mentor['id']} as offline due to session timeout. "
                                    f"Last activity: {last_activity}, Timeout: {SESSION_TIMEOUT_MINUTES} minutes"
                                )
                    
                    # Build enriched mentor object
                    enriched_mentor = {
                        'mentor_id': mentor['id'],
                        'full_name': mentor.get('full_name'),
                        'email': mentor.get('email', ''),
                        'role': mentor.get('role', 'mentor'),  # Include role to show admin+mentor
                        'last_login': mentor.get('last_login'),
                        'last_logout': mentor.get('last_logout'),
                        'is_online': is_actually_online,
                        'total_time_spent_seconds': total_time_spent_seconds,
                        'weekly_time_spent_seconds': weekly_time_spent_seconds,
                        'number_of_teams': len(mentor_teams),
                        'average_team_score': average_team_score,
                        'best_performing_team': best_performing_team,
                        'worst_performing_team': worst_performing_team,
                        'teams_in_top_10': teams_in_top_10
                    }
                    
                    enriched_mentors.append(enriched_mentor)
                    
                except Exception as mentor_error:
                    # Log error but continue with other mentors
                    logger.warning(
                        f"Failed to enrich mentor {mentor.get('id')}: {str(mentor_error)}. "
                        f"Skipping this mentor."
                    )
                    continue
            
            logger.debug(f"Successfully enriched {len(enriched_mentors)} mentors")
            mentors = enriched_mentors
            
            # Validate sort_by parameter
            allowed_sort_fields = [
                "last_login", 
                "total_time_spent", 
                "weekly_time_spent", 
                "average_team_score", 
                "number_of_teams"
            ]
            
            if sort_by not in allowed_sort_fields:
                error_msg = (
                    f"Invalid sort_by parameter: '{sort_by}'. "
                    f"Allowed values: {', '.join(allowed_sort_fields)}"
                )
                logger.warning(error_msg)
                raise ValueError(error_msg)
            
            # Validate sort_order parameter
            if sort_order not in ["asc", "desc"]:
                error_msg = (
                    f"Invalid sort_order parameter: '{sort_order}'. "
                    f"Allowed values: 'asc', 'desc'"
                )
                logger.warning(error_msg)
                raise ValueError(error_msg)
            
            # Apply sorting
            def get_sort_key(mentor):
                """Extract the sort key value from a mentor record"""
                if sort_by == "last_login":
                    # Handle None values by treating them as earliest possible time
                    value = mentor.get('last_login')
                    if value is None:
                        # Use timezone-aware datetime.min for UTC
                        from datetime import timezone
                        return datetime.min.replace(tzinfo=timezone.utc)
                    # Convert string to datetime if needed
                    if isinstance(value, str):
                        try:
                            from dateutil import parser
                            parsed = parser.parse(value)
                            # Ensure timezone-aware
                            if parsed.tzinfo is None:
                                from datetime import timezone
                                parsed = parsed.replace(tzinfo=timezone.utc)
                            return parsed
                        except:
                            from datetime import timezone
                            return datetime.min.replace(tzinfo=timezone.utc)
                    # Ensure timezone-aware
                    if value.tzinfo is None:
                        from datetime import timezone
                        value = value.replace(tzinfo=timezone.utc)
                    return value
                elif sort_by == "total_time_spent":
                    return mentor.get('total_time_spent_seconds', 0)
                elif sort_by == "weekly_time_spent":
                    return mentor.get('weekly_time_spent_seconds', 0)
                elif sort_by == "average_team_score":
                    # Handle None values by treating them as lowest score
                    return mentor.get('average_team_score') or -1
                elif sort_by == "number_of_teams":
                    return mentor.get('number_of_teams', 0)
                else:
                    return None
            
            # Sort mentors
            reverse = (sort_order == "desc")
            try:
                mentors = sorted(mentors, key=get_sort_key, reverse=reverse)
                logger.debug(f"Sorted {len(mentors)} mentors by {sort_by} {sort_order}")
            except Exception as sort_error:
                logger.error(f"Error sorting mentors: {str(sort_error)}", exc_info=True)
                raise ValueError(f"Failed to sort mentors by {sort_by}: {str(sort_error)}")
            
            # Calculate total count before pagination
            total_count = len(mentors)
            
            # Calculate total pages
            total_pages = (total_count + page_size - 1) // page_size if total_count > 0 else 0
            
            # Apply pagination
            start_idx = (page - 1) * page_size
            end_idx = start_idx + page_size
            paginated_mentors = mentors[start_idx:end_idx]
            
            logger.debug(
                f"Pagination applied: page={page}, page_size={page_size}, "
                f"total={total_count}, total_pages={total_pages}, "
                f"returned={len(paginated_mentors)} mentors"
            )
            
            # Log performance metrics
            elapsed_time = time.time() - start_time
            logger.info(f"get_mentor_list completed in {elapsed_time:.3f}s")
            if elapsed_time > 1.0:
                logger.warning(f"Slow query detected: get_mentor_list took {elapsed_time:.3f}s")
            
            # Return paginated results with metadata
            return {
                "mentors": paginated_mentors,
                "total": total_count,
                "page": page,
                "page_size": page_size,
                "total_pages": total_pages
            }
            
        except ValueError as ve:
            # Re-raise ValueError for parameter validation
            logger.warning(f"Parameter validation error: {str(ve)}")
            raise
        except Exception as e:
            logger.error(
                f"Error retrieving mentor list: {str(e)}",
                exc_info=True
            )
            from fastapi import HTTPException
            raise HTTPException(
                status_code=500,
                detail=f"Failed to retrieve mentor analytics: {str(e)}"
            )
    
    async def get_mentor_detail(self, mentor_id: UUID) -> Dict[str, Any]:
        """
        Retrieve detailed analytics for a specific mentor
        
        Args:
            mentor_id: UUID of the mentor
        
        Returns:
            Dictionary containing:
                - mentor_id: UUID of the mentor
                - full_name: Mentor's full name
                - email: Mentor's email
                - last_login: Last login timestamp
                - last_logout: Last logout timestamp
                - is_online: Current online status
                - total_time_spent_seconds: Total time spent in seconds
                - weekly_time_spent_seconds: Weekly time spent in seconds
                - teams: List of team details
                - performance_summary: Performance metrics summary
        
        Raises:
            ValueError: If mentor_id is invalid
            LookupError: If mentor not found (should return 404)
        """
        import time
        start_time = time.time()
        
        logger.info(f"get_mentor_detail called for mentor_id={mentor_id}")
        
        try:
            # Query users table for specific mentor (role='mentor' OR is_mentor=true)
            try:
                mentor_response = self.supabase.table("users").select(
                    "id, email, full_name, role, last_login, last_logout, is_online, total_time_spent, weekly_time_spent, week_start_date"
                ).eq("id", str(mentor_id)).or_("role.eq.mentor,is_mentor.eq.true").execute()
            except Exception as db_error:
                logger.error(f"Database query failed for mentor {mentor_id}: {str(db_error)}", exc_info=True)
                from fastapi import HTTPException
                raise HTTPException(
                    status_code=503,
                    detail="Database service unavailable. Please try again later."
                )
            
            # Validate mentor exists
            if not mentor_response.data or len(mentor_response.data) == 0:
                logger.warning(f"Mentor not found: {mentor_id}")
                raise LookupError(f"Mentor with id {mentor_id} not found")
            
            mentor = mentor_response.data[0]
            logger.debug(f"Found mentor: {mentor.get('email')}")
            
            # Parse timestamps
            last_login = None
            last_logout = None
            
            if mentor.get('last_login'):
                if isinstance(mentor['last_login'], str):
                    from dateutil import parser
                    last_login = parser.parse(mentor['last_login'])
                else:
                    last_login = mentor['last_login']
            
            if mentor.get('last_logout'):
                if isinstance(mentor['last_logout'], str):
                    from dateutil import parser
                    last_logout = parser.parse(mentor['last_logout'])
                else:
                    last_logout = mentor['last_logout']
            
            # Calculate weekly time spent using accumulated value from database
            # Parse weekly_time_spent INTERVAL from database
            weekly_time_spent_seconds = 0
            weekly_time_db = mentor.get('weekly_time_spent')
            
            if weekly_time_db:
                # Parse PostgreSQL INTERVAL format
                weekly_time_spent_seconds = self._parse_interval_to_seconds(weekly_time_db)
            
            # If user is currently online, add current session time to accumulated weekly time
            from datetime import timezone as tz
            current_time = datetime.now(tz.utc)
            if mentor.get('is_online', False) and last_login:
                current_session_seconds = self.calculate_weekly_time_spent(
                    last_login=last_login,
                    last_logout=last_logout,
                    is_online=True,
                    current_time=current_time
                )
                weekly_time_spent_seconds += current_session_seconds
            
            # Convert total_time_spent to seconds
            total_time_spent = mentor.get('total_time_spent', 0)
            if isinstance(total_time_spent, (int, float)):
                total_time_spent_seconds = int(total_time_spent)
            else:
                # Handle interval type if needed
                total_time_spent_seconds = 0
            
            # Query all teams for mentor with batch and student data
            try:
                teams_response = self.supabase.table("teams").select(
                    "id, team_name, batch_id, total_score, last_activity, "
                    "batches(id, name)"
                ).eq("mentor_id", str(mentor_id)).execute()
                
                teams_data = teams_response.data
            except Exception as db_error:
                logger.error(f"Failed to query teams for mentor {mentor_id}: {str(db_error)}", exc_info=True)
                from fastapi import HTTPException
                raise HTTPException(
                    status_code=503,
                    detail="Database service unavailable. Please try again later."
                )
            logger.debug(f"Found {len(teams_data)} teams for mentor {mentor_id}")
            
            # Build team details list with rankings
            teams = []
            for team in teams_data:
                # Get batch information
                batch_info = team.get('batches')
                batch_id = team.get('batch_id')
                batch_name = batch_info.get('name') if batch_info else None
                
                # Calculate team rank using calculate_team_rankings()
                rank_in_batch = None
                if batch_id and team.get('total_score') is not None:
                    try:
                        batch_uuid = UUID(batch_id) if isinstance(batch_id, str) else batch_id
                        rankings = await self.calculate_team_rankings(batch_uuid)
                        team_uuid = UUID(team['id']) if isinstance(team['id'], str) else team['id']
                        rank_in_batch = rankings.get(team_uuid)
                    except Exception as rank_error:
                        logger.warning(
                            f"Failed to calculate rank for team {team['id']}: {str(rank_error)}"
                        )
                
                # Query student count for this team
                try:
                    students_response = self.supabase.table("students").select(
                        "id", count="exact"
                    ).eq("team_id", team['id']).execute()
                    
                    student_count = students_response.count if students_response.count is not None else 0
                except Exception as student_error:
                    logger.warning(
                        f"Failed to query student count for team {team['id']}: {str(student_error)}"
                    )
                    student_count = 0
                
                # Parse last_activity timestamp
                last_activity = None
                if team.get('last_activity'):
                    if isinstance(team['last_activity'], str):
                        from dateutil import parser
                        last_activity = parser.parse(team['last_activity'])
                    else:
                        last_activity = team['last_activity']
                
                # Build team detail
                team_detail = {
                    "team_id": team['id'],
                    "team_name": team['team_name'],
                    "batch_id": batch_id,
                    "batch_name": batch_name,
                    "total_score": team.get('total_score'),
                    "rank_in_batch": rank_in_batch,
                    "student_count": student_count,
                    "last_activity": last_activity
                }
                
                teams.append(team_detail)
            
            # Calculate performance summary
            performance_metrics = await self.calculate_mentor_performance(mentor_id)
            
            # Calculate teams in top 10
            teams_in_top_10 = await self.calculate_teams_in_top_10(mentor_id)
            
            # Build performance summary
            performance_summary = {
                "average_team_score": performance_metrics.get('average_team_score'),
                "best_performing_team": performance_metrics.get('best_performing_team'),
                "worst_performing_team": performance_metrics.get('worst_performing_team'),
                "teams_in_top_10": teams_in_top_10
            }
            
            logger.info(
                f"Successfully retrieved detail for mentor {mentor_id}: "
                f"{len(teams)} teams, avg_score={performance_summary['average_team_score']}"
            )
            
            # Log performance metrics
            elapsed_time = time.time() - start_time
            logger.info(f"get_mentor_detail completed in {elapsed_time:.3f}s")
            if elapsed_time > 1.0:
                logger.warning(f"Slow query detected: get_mentor_detail took {elapsed_time:.3f}s")
            
            return {
                "mentor_id": str(mentor_id),
                "full_name": mentor.get('full_name'),
                "email": mentor.get('email', ''),
                "last_login": last_login,
                "last_logout": last_logout,
                "is_online": mentor.get('is_online', False),
                "total_time_spent_seconds": total_time_spent_seconds,
                "weekly_time_spent_seconds": weekly_time_spent_seconds,
                "teams": teams,
                "performance_summary": performance_summary
            }
            
        except LookupError:
            # Re-raise LookupError for 404 handling
            raise
        except Exception as e:
            logger.error(
                f"Error retrieving mentor detail for {mentor_id}: {str(e)}",
                exc_info=True
            )
            from fastapi import HTTPException
            raise HTTPException(
                status_code=500,
                detail=f"Failed to retrieve mentor detail: {str(e)}"
            )
    
    def _parse_interval_to_seconds(self, interval_str: str) -> int:
        """
        Parse PostgreSQL INTERVAL string to seconds.
        
        Handles formats like:
        - "01:30:00" (1 hour 30 minutes)
        - "2 days 01:30:00" (2 days, 1 hour, 30 minutes)
        - "00:00:00" (0 seconds)
        
        Args:
            interval_str: PostgreSQL INTERVAL string
        
        Returns:
            Total seconds as integer
        """
        if not interval_str:
            return 0
        
        try:
            total_seconds = 0
            
            # Check for days component
            if 'day' in interval_str:
                parts = interval_str.split()
                days = int(parts[0])
                total_seconds += days * 86400  # 86400 seconds in a day
                # Get the time part after "days"
                time_part = parts[-1]
            else:
                time_part = interval_str.strip()
            
            # Parse time part (HH:MM:SS)
            if ':' in time_part:
                time_components = time_part.split(':')
                if len(time_components) == 3:
                    hours = int(time_components[0])
                    minutes = int(time_components[1])
                    seconds = float(time_components[2])
                    
                    total_seconds += hours * 3600
                    total_seconds += minutes * 60
                    total_seconds += int(seconds)
            
            return total_seconds
        except Exception as e:
            logger.warning(f"Failed to parse interval '{interval_str}': {str(e)}")
            return 0
    
    def calculate_weekly_time_spent(
        self,
        last_login: Optional[datetime],
        last_logout: Optional[datetime],
        is_online: bool,
        current_time: datetime
    ) -> int:
        """
        Calculate time spent in seconds during the current calendar week.
        
        Week boundaries: Sunday 00:00:00 to Saturday 23:59:59
        
        Args:
            last_login: Last login timestamp
            last_logout: Last logout timestamp
            is_online: Whether user is currently online
            current_time: Current timestamp for calculation
        
        Returns:
            Time spent in seconds during current week (non-negative integer)
        
        Examples:
            >>> # Mentor logged in this week and is still online
            >>> service.calculate_weekly_time_spent(
            ...     last_login=datetime(2024, 1, 15, 10, 0),  # Monday
            ...     last_logout=None,
            ...     is_online=True,
            ...     current_time=datetime(2024, 1, 15, 12, 0)  # Monday
            ... )
            7200  # 2 hours in seconds
            
            >>> # Mentor logged in and logged out this week
            >>> service.calculate_weekly_time_spent(
            ...     last_login=datetime(2024, 1, 15, 10, 0),
            ...     last_logout=datetime(2024, 1, 15, 12, 0),
            ...     is_online=False,
            ...     current_time=datetime(2024, 1, 15, 14, 0)
            ... )
            7200  # 2 hours in seconds
        """
        # If no login data, return 0
        if not last_login:
            return 0
        
        # Ensure all datetimes are timezone-aware
        from datetime import timezone as tz
        
        if current_time.tzinfo is None:
            current_time = current_time.replace(tzinfo=tz.utc)
        
        if last_login.tzinfo is None:
            last_login = last_login.replace(tzinfo=tz.utc)
        
        if last_logout and last_logout.tzinfo is None:
            last_logout = last_logout.replace(tzinfo=tz.utc)
        
        # Get current week boundaries (Sunday to Saturday)
        # weekday() returns 0=Monday, 6=Sunday
        # We need to adjust to get Sunday as start of week
        days_since_sunday = (current_time.weekday() + 1) % 7
        week_start = current_time - timedelta(days=days_since_sunday)
        week_start = week_start.replace(hour=0, minute=0, second=0, microsecond=0)
        week_end = week_start + timedelta(days=7) - timedelta(microseconds=1)
        
        # Determine session end time
        if is_online:
            session_end = current_time
        elif last_logout:
            session_end = last_logout
        else:
            # Logged in but not online and no logout - shouldn't happen
            return 0
        
        # Clip session to week boundaries
        session_start = max(last_login, week_start)
        session_end = min(session_end, week_end)
        
        # If session is outside current week, return 0
        if session_start > week_end or session_end < week_start:
            return 0
        
        # Calculate duration in seconds
        duration = (session_end - session_start).total_seconds()
        return max(0, int(duration))
    
    async def calculate_mentor_performance(
        self,
        mentor_id: UUID
    ) -> Dict[str, Any]:
        """
        Calculate performance metrics based on assigned team scores.
        
        This method queries teams assigned to the mentor and calculates:
        - Average team score (excluding null scores)
        - Best performing team (max score)
        - Worst performing team (min score)
        - Deterministic tie-breaking by team_id ascending
        
        Args:
            mentor_id: UUID of the mentor
        
        Returns:
            Dictionary containing:
                - average_team_score: float or None (arithmetic mean of non-null scores)
                - best_performing_team: dict or None with team_id, team_name, score
                - worst_performing_team: dict or None with team_id, team_name, score
                - teams_in_top_10: int (placeholder, requires batch ranking logic)
                - total_teams: int (count of all teams)
                - teams_with_scores: int (count of teams with non-null scores)
        
        Examples:
            >>> # Mentor with multiple teams
            >>> await service.calculate_mentor_performance(mentor_id)
            {
                'average_team_score': 75.5,
                'best_performing_team': {
                    'team_id': 'uuid-1',
                    'team_name': 'Team A',
                    'score': 90.0
                },
                'worst_performing_team': {
                    'team_id': 'uuid-2',
                    'team_name': 'Team B',
                    'score': 61.0
                },
                'teams_in_top_10': 0,
                'total_teams': 3,
                'teams_with_scores': 2
            }
        """
        logger.info(f"Calculating performance metrics for mentor_id={mentor_id}")
        
        try:
            # Query teams assigned to this mentor
            try:
                response = self.supabase.table("teams").select(
                    "id, team_name, total_score"
                ).eq("mentor_id", str(mentor_id)).execute()
                
                teams = response.data
            except Exception as db_error:
                logger.error(f"Database query failed for mentor {mentor_id}: {str(db_error)}", exc_info=True)
                from fastapi import HTTPException
                raise HTTPException(
                    status_code=503,
                    detail="Database service unavailable. Please try again later."
                )
            total_teams = len(teams)
            
            logger.debug(f"Found {total_teams} teams for mentor {mentor_id}")
            
            # Filter teams with non-null scores
            teams_with_scores = [
                team for team in teams 
                if team.get('total_score') is not None
            ]
            
            teams_with_scores_count = len(teams_with_scores)
            
            # If no teams with scores, return null metrics
            if teams_with_scores_count == 0:
                logger.debug(f"No teams with scores for mentor {mentor_id}")
                return {
                    'average_team_score': None,
                    'best_performing_team': None,
                    'worst_performing_team': None,
                    'teams_in_top_10': 0,
                    'total_teams': total_teams,
                    'teams_with_scores': 0
                }
            
            # Calculate average team score
            total_score = sum(team['total_score'] for team in teams_with_scores)
            average_score = total_score / teams_with_scores_count
            
            # Sort teams by score descending, then by team_id ascending for deterministic tie-breaking
            sorted_teams = sorted(
                teams_with_scores,
                key=lambda t: (-t['total_score'], t['id'])
            )
            
            # Best performing team (highest score, lowest team_id if tied)
            best_team = sorted_teams[0]
            best_performing_team = {
                'team_id': best_team['id'],
                'team_name': best_team['team_name'],
                'score': best_team['total_score']
            }
            
            # Worst performing team (lowest score, lowest team_id if tied)
            # Sort by score ascending, then by team_id ascending
            worst_sorted = sorted(
                teams_with_scores,
                key=lambda t: (t['total_score'], t['id'])
            )
            worst_team = worst_sorted[0]
            worst_performing_team = {
                'team_id': worst_team['id'],
                'team_name': worst_team['team_name'],
                'score': worst_team['total_score']
            }
            
            logger.info(
                f"Performance calculated for mentor {mentor_id}: "
                f"avg={average_score:.2f}, best={best_team['team_name']}, "
                f"worst={worst_team['team_name']}"
            )
            
            return {
                'average_team_score': average_score,
                'best_performing_team': best_performing_team,
                'worst_performing_team': worst_performing_team,
                'teams_in_top_10': 0,  # TODO: Implement in separate task
                'total_teams': total_teams,
                'teams_with_scores': teams_with_scores_count
            }
            
        except Exception as e:
            logger.error(
                f"Error calculating performance for mentor {mentor_id}: {str(e)}",
                exc_info=True
            )
            from fastapi import HTTPException
            raise HTTPException(
                status_code=500,
                detail=f"Failed to calculate mentor performance: {str(e)}"
            )

    async def calculate_team_rankings(
        self,
        batch_id: UUID
    ) -> Dict[UUID, int]:
        """
        Calculate team rankings within a batch based on total_score.
        
        Teams are ranked by total_score in descending order. Teams with
        identical scores receive the same rank. Teams with null scores
        are excluded from rankings.
        
        This method implements caching to avoid recalculating rankings
        for the same batch multiple times. Cache entries expire after 5 minutes.
        
        Args:
            batch_id: UUID of the batch
        
        Returns:
            Dictionary mapping team_id (UUID) to rank (1-indexed integer).
            Teams with null scores are not included in the dictionary.
        
        Examples:
            >>> # Batch with 3 teams: scores 90, 85, 85
            >>> await service.calculate_team_rankings(batch_id)
            {
                UUID('team-1'): 1,  # score 90
                UUID('team-2'): 2,  # score 85
                UUID('team-3'): 2   # score 85 (tied)
            }
            
            >>> # Batch with null scores excluded
            >>> await service.calculate_team_rankings(batch_id)
            {
                UUID('team-1'): 1,  # score 90
                UUID('team-2'): 2   # score 85, team-3 has null score
            }
        """
        import time
        start_time = time.time()
        
        logger.info(f"Calculating team rankings for batch_id={batch_id}")
        
        # Check cache first
        batch_id_str = str(batch_id)
        current_time = datetime.utcnow()
        
        if batch_id_str in _batch_rankings_cache:
            cache_entry = _batch_rankings_cache[batch_id_str]
            expires_at = cache_entry.get('expires_at')
            
            # Check if cache is still valid (not expired)
            if expires_at and current_time < expires_at:
                logger.debug(f"Using cached rankings for batch {batch_id}")
                return cache_entry['rankings']
            else:
                logger.debug(f"Cache expired for batch {batch_id}, recalculating")
                del _batch_rankings_cache[batch_id_str]
        
        try:
            # Query all teams in the batch with non-null scores
            try:
                response = self.supabase.table("teams").select(
                    "id, total_score"
                ).eq("batch_id", str(batch_id)).not_.is_("total_score", "null").order(
                    "total_score", desc=True
                ).execute()
                
                teams = response.data
            except Exception as db_error:
                logger.error(f"Database query failed for batch {batch_id}: {str(db_error)}", exc_info=True)
                from fastapi import HTTPException
                raise HTTPException(
                    status_code=503,
                    detail="Database service unavailable. Please try again later."
                )
            logger.debug(f"Found {len(teams)} teams with scores in batch {batch_id}")
            
            # Build rankings dictionary with tie handling
            rankings = {}
            current_rank = 1
            prev_score = None
            
            for idx, team in enumerate(teams):
                score = team['total_score']
                
                # If score changed, update rank to current position
                if score != prev_score:
                    current_rank = idx + 1
                
                # Convert team id string to UUID
                team_uuid = UUID(team['id']) if isinstance(team['id'], str) else team['id']
                rankings[team_uuid] = current_rank
                prev_score = score
            
            # Cache the rankings for 5 minutes
            expires_at = current_time + timedelta(minutes=5)
            _batch_rankings_cache[batch_id_str] = {
                'rankings': rankings,
                'expires_at': expires_at
            }
            
            # Log performance metrics
            elapsed_time = time.time() - start_time
            logger.info(
                f"Rankings calculated and cached for batch {batch_id}: "
                f"{len(rankings)} teams ranked (expires at {expires_at.isoformat()}) "
                f"in {elapsed_time:.3f}s"
            )
            if elapsed_time > 1.0:
                logger.warning(f"Slow ranking calculation: batch {batch_id} took {elapsed_time:.3f}s")
            
            return rankings
            
        except Exception as e:
            logger.error(
                f"Error calculating rankings for batch {batch_id}: {str(e)}",
                exc_info=True
            )
            from fastapi import HTTPException
            raise HTTPException(
                status_code=500,
                detail=f"Failed to calculate team rankings: {str(e)}"
            )

    async def calculate_teams_in_top_10(
        self,
        mentor_id: UUID
    ) -> int:
        """
        Calculate how many of a mentor's teams are in the top 10 within their batches.
        
        This method:
        1. Retrieves all teams assigned to the mentor
        2. Groups teams by batch_id
        3. Calculates rankings for each batch separately
        4. Counts teams with rank <= 10
        
        Args:
            mentor_id: UUID of the mentor
        
        Returns:
            Integer count of teams ranked in top 10 within their respective batches.
            Teams with null scores are excluded from ranking and not counted.
        
        Examples:
            >>> # Mentor with 3 teams: 2 in top 10, 1 outside top 10
            >>> await service.calculate_teams_in_top_10(mentor_id)
            2
            
            >>> # Mentor with teams in multiple batches
            >>> # Batch A: team ranked 5, Batch B: team ranked 15
            >>> await service.calculate_teams_in_top_10(mentor_id)
            1  # Only the team ranked 5 counts
        """
        logger.info(f"Calculating teams in top 10 for mentor_id={mentor_id}")
        
        try:
            # Query all teams assigned to this mentor
            try:
                response = self.supabase.table("teams").select(
                    "id, batch_id, total_score"
                ).eq("mentor_id", str(mentor_id)).execute()
                
                teams = response.data
            except Exception as db_error:
                logger.error(f"Database query failed for mentor {mentor_id}: {str(db_error)}", exc_info=True)
                from fastapi import HTTPException
                raise HTTPException(
                    status_code=503,
                    detail="Database service unavailable. Please try again later."
                )
            logger.debug(f"Found {len(teams)} teams for mentor {mentor_id}")
            
            # Filter out teams with null scores (they won't be ranked)
            teams_with_scores = [
                team for team in teams 
                if team.get('total_score') is not None
            ]
            
            if not teams_with_scores:
                logger.debug(f"No teams with scores for mentor {mentor_id}")
                return 0
            
            # Group teams by batch_id
            teams_by_batch: Dict[str, List[Dict[str, Any]]] = {}
            for team in teams_with_scores:
                batch_id = team['batch_id']
                if batch_id not in teams_by_batch:
                    teams_by_batch[batch_id] = []
                teams_by_batch[batch_id].append(team)
            
            logger.debug(
                f"Mentor {mentor_id} has teams in {len(teams_by_batch)} batches"
            )
            
            # Calculate rankings for each batch and count top 10 teams
            top_10_count = 0
            
            for batch_id, batch_teams in teams_by_batch.items():
                # Get rankings for this batch
                batch_uuid = UUID(batch_id) if isinstance(batch_id, str) else batch_id
                rankings = await self.calculate_team_rankings(batch_uuid)
                
                # Count how many of mentor's teams in this batch are in top 10
                for team in batch_teams:
                    team_uuid = UUID(team['id']) if isinstance(team['id'], str) else team['id']
                    rank = rankings.get(team_uuid)
                    
                    if rank is not None and rank <= 10:
                        top_10_count += 1
                        logger.debug(
                            f"Team {team['id']} ranked {rank} in batch {batch_id}"
                        )
            
            logger.info(
                f"Mentor {mentor_id} has {top_10_count} teams in top 10"
            )
            
            return top_10_count
            
        except Exception as e:
            logger.error(
                f"Error calculating teams in top 10 for mentor {mentor_id}: {str(e)}",
                exc_info=True
            )
            from fastapi import HTTPException
            raise HTTPException(
                status_code=500,
                detail=f"Failed to calculate teams in top 10: {str(e)}"
            )

    def export_to_csv(self, mentors: List[Dict[str, Any]]) -> str:
        """
        Convert mentor analytics data to CSV format.
        
        Args:
            mentors: List of mentor analytics items (dictionaries)
        
        Returns:
            CSV string with headers and data rows
        
        Examples:
            >>> mentors = [
            ...     {
            ...         'full_name': 'John Doe',
            ...         'email': 'john@example.com',
            ...         'last_login': datetime(2024, 1, 15, 10, 0),
            ...         'last_logout': datetime(2024, 1, 15, 12, 0),
            ...         'is_online': False,
            ...         'total_time_spent_seconds': 7200,
            ...         'weekly_time_spent_seconds': 3600,
            ...         'number_of_teams': 3,
            ...         'average_team_score': 75.5,
            ...         'best_performing_team': {
            ...             'team_name': 'Team A',
            ...             'score': 90.0
            ...         },
            ...         'worst_performing_team': {
            ...             'team_name': 'Team B',
            ...             'score': 61.0
            ...         },
            ...         'teams_in_top_10': 2
            ...     }
            ... ]
            >>> csv_output = service.export_to_csv(mentors)
            >>> 'mentor_name,email,last_login' in csv_output
            True
        """
        import csv
        from io import StringIO
        
        logger.info(f"Exporting {len(mentors)} mentors to CSV")
        
        output = StringIO()
        writer = csv.writer(output)
        
        # Write header
        writer.writerow([
            'mentor_name',
            'email',
            'last_login',
            'last_logout',
            'online_status',
            'total_time_spent_hours',
            'weekly_time_spent_hours',
            'number_of_teams',
            'average_team_score',
            'best_team_name',
            'best_team_score',
            'worst_team_name',
            'worst_team_score',
            'teams_in_top_10'
        ])
        
        # Write data rows
        for mentor in mentors:
            # Format timestamps as ISO 8601 or empty string
            last_login = ''
            if mentor.get('last_login'):
                login_val = mentor['last_login']
                if isinstance(login_val, str):
                    last_login = login_val
                else:
                    last_login = login_val.isoformat()
            
            last_logout = ''
            if mentor.get('last_logout'):
                logout_val = mentor['last_logout']
                if isinstance(logout_val, str):
                    last_logout = logout_val
                else:
                    last_logout = logout_val.isoformat()
            
            # Convert online status to string
            online_status = 'online' if mentor.get('is_online', False) else 'offline'
            
            # Convert time from seconds to hours
            total_hours = round(mentor.get('total_time_spent_seconds', 0) / 3600, 2)
            weekly_hours = round(mentor.get('weekly_time_spent_seconds', 0) / 3600, 2)
            
            # Format average score
            avg_score = ''
            if mentor.get('average_team_score') is not None:
                avg_score = round(mentor['average_team_score'], 2)
            
            # Extract best team info
            best_team_name = ''
            best_team_score = ''
            if mentor.get('best_performing_team'):
                best = mentor['best_performing_team']
                best_team_name = best.get('team_name', '')
                if best.get('score') is not None:
                    best_team_score = round(best['score'], 2)
            
            # Extract worst team info
            worst_team_name = ''
            worst_team_score = ''
            if mentor.get('worst_performing_team'):
                worst = mentor['worst_performing_team']
                worst_team_name = worst.get('team_name', '')
                if worst.get('score') is not None:
                    worst_team_score = round(worst['score'], 2)
            
            writer.writerow([
                mentor.get('full_name', ''),
                mentor.get('email', ''),
                last_login,
                last_logout,
                online_status,
                total_hours,
                weekly_hours,
                mentor.get('number_of_teams', 0),
                avg_score,
                best_team_name,
                best_team_score,
                worst_team_name,
                worst_team_score,
                mentor.get('teams_in_top_10', 0)
            ])
        
        csv_content = output.getvalue()
        logger.info(f"CSV export completed: {len(csv_content)} bytes")
        
        return csv_content
