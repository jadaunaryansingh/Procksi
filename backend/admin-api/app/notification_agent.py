import json
from app.main import service_client
from app.email_notifier import (
    trigger_proposal_email,
    trigger_mentor_assigned_email,
    trigger_team_created_email,
    trigger_team_approved_email,
    trigger_evaluation_submitted_email,
    trigger_results_published_email,
    trigger_ps_released_email,
    trigger_student_welcome_email,
    trigger_ps_allocated_email,
    trigger_slot_scheduled_email,
    trigger_extra_activity_email,
    trigger_absent_email,
    trigger_all_deadlines_email
)

def _existing_deadline_notice_keys(candidates: list) -> set:
    """Notices already in the table for the titles we are about to send.

    Scoped to the titles in this batch rather than scanning the whole table. On
    any lookup failure this returns an empty set, so a transient error means a
    possible duplicate rather than a silently dropped notification — the safer
    direction for something students rely on.
    """
    from app.deadline_notice_core import notice_key

    titles = sorted({c.get("title") for c in candidates if c.get("title")})
    if not titles:
        return set()
    try:
        res = (
            service_client.table("notifications")
            .select("recipient_email,title,message")
            .in_("title", titles)
            .execute()
        )
        return {notice_key(r) for r in (res.data or [])}
    except Exception as exc:
        print(f"Deadline notice dedup lookup failed ({exc}); sending without it.")
        return set()


def trigger_admin_upsert_notifications(table_name: str, rows: list):
    try:
        from app.email_notifier import (
            get_student_emails_in_team,
            get_student_email_by_roll,
            get_mentor_emails,
            get_all_student_emails,
            get_all_mentor_emails,
        )
        notifications = []
        if table_name == "proposals":
            for row in rows:
                team_id = row.get("teamId") or row.get("team_id") or row.get("team")
                status = str(row.get("status") or "").strip().lower()
                title = row.get("title") or row.get("project_title") or "Project Proposal"
                
                if team_id and status in ("approved", "accepted", "rejected", "revision_requested"):
                    try:
                        trigger_proposal_email(str(team_id), status, title)
                    except Exception as e_err:
                        print(f"Failed to trigger proposal email: {e_err}")
                
                if team_id:
                    student_emails = get_student_emails_in_team(str(team_id))
                    
                    if status in ("approved", "accepted"):
                        for email in student_emails:
                            notifications.append({
                                "recipient_email": email,
                                "recipient_role": "student",
                                "title": "Proposal Approved",
                                "message": f"Your proposal '{title}' has been approved.",
                                "type": "approval",
                                "read": False
                            })
                        notifications.append({
                            "recipient_role": "admin",
                            "audience": "admin",
                            "title": "Proposal Approved",
                            "message": f"Proposal '{title}' has been marked as approved.",
                            "type": "approval",
                            "read": False
                        })
                    elif status == "rejected":
                        for email in student_emails:
                            notifications.append({
                                "recipient_email": email,
                                "recipient_role": "student",
                                "title": "Proposal Rejected",
                                "message": f"Your proposal '{title}' was rejected.",
                                "type": "workflow",
                                "read": False
                            })
                        notifications.append({
                            "recipient_role": "admin",
                            "audience": "admin",
                            "title": "Proposal Rejected",
                            "message": f"Proposal '{title}' has been marked as rejected.",
                            "type": "workflow",
                            "read": False
                        })
                    elif status == "revision_requested":
                        for email in student_emails:
                            notifications.append({
                                "recipient_email": email,
                                "recipient_role": "student",
                                "title": "Proposal Revision Requested",
                                "message": f"Your proposal '{title}' requires revision.",
                                "type": "workflow",
                                "read": False
                            })

        elif table_name in ("teams_validation", "results"):
            for row in rows:
                mentor = row.get("mentor")
                team_id = str(row.get("id") or row.get("team_id") or row.get("teamId") or row.get("team") or "")
                title = row.get("title") or row.get("project_title") or row.get("name") or f"Team {team_id}"
                validation_status = str(row.get("validationStatus") or row.get("status") or "").strip().lower()
                
                # Send Team Formed email ONLY when explicitly marked as a newly created team
                if row.get("is_new_team") == True:
                    try:
                        trigger_team_created_email(team_id, title)
                    except Exception as t_err:
                        print(f"Failed to trigger team created email: {t_err}")

                student_emails = get_student_emails_in_team(team_id)

                # Send team approved email only if explicitly flagged for team validation approval and not skipping
                if not row.get("_skip_emails") and (validation_status in ("approved", "valid", "verified") or row.get("isValid") == True):
                    if row.get("_explicit_team_approval") == True:
                        try:
                            trigger_team_approved_email(team_id, title)
                        except Exception as ta_err:
                            print(f"Failed to trigger team approved email: {ta_err}")
                    
                    description = row.get("description") or ""
                    domain = row.get("domain") or ""
                    if row.get("_explicit_ps_allocation") == True and title and not title.lower().startswith("team"):
                        try:
                            trigger_ps_allocated_email(team_id, title, description, domain)
                        except Exception as ps_err:
                            print(f"Failed to trigger ps allocated email: {ps_err}")
                
                if mentor and str(mentor).strip() not in ("[]", "null", "", "None"):
                    mentor_list = []
                    if isinstance(mentor, list):
                        mentor_list = mentor
                    elif isinstance(mentor, str):
                        try:
                            parsed = json.loads(mentor)
                            if isinstance(parsed, list):
                                mentor_list = parsed
                            else:
                                mentor_list = [parsed]
                        except Exception:
                            mentor_list = [mentor]
                    else:
                        mentor_list = [mentor]

                    mentor_names = []
                    for m in mentor_list:
                        if isinstance(m, dict):
                            m_name = m.get('name') or m.get('mentor_name') or m.get('id')
                        else:
                            m_name = str(m).strip()
                        if m_name and m_name not in ("null", "None", ""):
                            mentor_names.append(m_name)

                    mentor_emails = get_mentor_emails(mentor_names)
                    for m_email in mentor_emails:
                        notifications.append({
                            "recipient_email": m_email,
                            "recipient_role": "mentor",
                            "title": "New Team Assigned",
                            "message": f"You have been assigned to mentor team '{title}'.",
                            "type": "allocation",
                            "read": False
                        })
                    
                    if mentor_names:
                        try:
                            # No automatic mentor-facing email here by design: an
                            # admin sends those manually, once, via the "Mass
                            # Email Mentors" button once allocation is finalized
                            # (see build_communication_router's
                            # /send-mentor-assignment-emails), grouped into one
                            # email per mentor covering every assigned team. This
                            # call still handles the per-team student email.
                            trigger_mentor_assigned_email(team_id, title, mentor_names, notify_mentor=False)
                        except Exception as ma_err:
                            print(f"Failed to trigger mentor assigned email: {ma_err}")

                    for email in student_emails:
                        notifications.append({
                            "recipient_email": email,
                            "recipient_role": "student",
                            "title": "Mentor Assigned",
                            "message": f"Mentor {', '.join(mentor_names)} has been assigned to your team.",
                            "type": "allocation",
                            "read": False
                        })
                    
                    notifications.append({
                        "recipient_role": "admin",
                        "audience": "admin",
                        "title": "Mentor Allocated",
                        "message": f"Mentor {', '.join(mentor_names)} successfully allocated to team '{title}'.",
                        "type": "allocation",
                        "read": False
                    })

        elif table_name == "schedule_slots":
            for row in rows:
                team_id = row.get("team") or row.get("team_id") or row.get("teamId")
                date = row.get("date") or row.get("slot_date")
                time = row.get("time") or row.get("slot_time")
                room = row.get("room") or row.get("venue") or "Main Hall"
                meet_link = row.get("meetLink") or row.get("meet_link") or row.get("meet_url")
                if team_id:
                    try:
                        trigger_slot_scheduled_email(str(team_id), str(date or ""), str(time or ""), str(room or "Main Hall"), meet_link)
                    except Exception as s_err:
                        print(f"Failed to trigger slot scheduled email: {s_err}")
                    
                    is_online = str(room or "").strip().lower() in ("", "online", "google meet", "meet")
                    if is_online and meet_link:
                        where = f"online — join at {meet_link}"
                    elif is_online:
                        where = "online (meeting link to follow)"
                    else:
                        where = f"in {room}"
                    student_emails = get_student_emails_in_team(str(team_id))
                    for email in student_emails:
                        notifications.append({
                            "recipient_email": email,
                            "recipient_role": "student",
                            "title": "Presentation Scheduled",
                            "message": f"Your presentation has been scheduled on {date} at {time} {where}.",
                            "type": "allocation",
                            "read": False
                        })

        elif table_name == "extra_activities":
            for row in rows:
                student_roll = row.get("student_id") or row.get("student_roll") or row.get("roll") or row.get("roll_number")
                activity_title = row.get("title") or row.get("activity_title") or row.get("activity") or "Extra Activity"
                status = str(row.get("status") or "").strip().lower()
                points = row.get("points") or row.get("marks") or 0
                if student_roll and status in ("approved", "rejected"):
                    try:
                        trigger_extra_activity_email(str(student_roll), str(activity_title), str(status), int(points))
                    except Exception as ea_err:
                        print(f"Failed to trigger extra activity email: {ea_err}")
                    
                    student_emails = get_student_email_by_roll(str(student_roll))
                    for email in student_emails:
                        notifications.append({
                            "recipient_email": email,
                            "recipient_role": "student",
                            "title": f"Extra Activity {status.capitalize()}",
                            "message": f"Your extra activity '{activity_title}' submission has been {status} (Points: {points}).",
                            "type": "workflow",
                            "read": False
                        })

        elif table_name == "absent_students":
            for row in rows:
                student_roll = row.get("roll") or row.get("student_id") or row.get("student_roll") or row.get("roll_number")
                student_name = row.get("name") or row.get("student_name") or "Student"
                team_id = row.get("team") or row.get("team_id") or row.get("teamId") or ""
                reason = row.get("reason") or row.get("remarks") or "Absence"
                status = str(row.get("status") or "Pending")
                if student_roll:
                    try:
                        trigger_absent_email(str(student_roll), str(student_name), str(team_id), str(reason), str(status))
                    except Exception as ab_err:
                        print(f"Failed to trigger absent email: {ab_err}")
                    
                    student_emails = get_student_email_by_roll(str(student_roll))
                    for email in student_emails:
                        notifications.append({
                            "recipient_email": email,
                            "recipient_role": "student",
                            "title": f"Absence Alert: {status}",
                            "message": f"Your absence status for team evaluation has been updated to {status}.",
                            "type": "workflow",
                            "read": False
                        })

        elif table_name == "problem_statements":
            # Automatic PS released email dispatch disabled (triggered manually via admin action button)
            pass


        elif table_name == "presentation_cycles":
            for row in rows:
                title = row.get("title", "Presentation Cycle")
                deadline = row.get("deadline", "TBD")
                
                student_emails = get_all_student_emails()
                mentor_emails = get_all_mentor_emails()
                
                for email in student_emails:
                    notifications.append({
                        "recipient_email": email,
                        "recipient_role": "student",
                        "title": "New Evaluation Cycle",
                        "message": f"A new evaluation cycle '{title}' has been scheduled. Deadline: {deadline}",
                        "type": "workflow",
                        "read": False
                    })
                for email in mentor_emails:
                    notifications.append({
                        "recipient_email": email,
                        "recipient_role": "mentor",
                        "title": "New Evaluation Cycle",
                        "message": f"A new evaluation cycle '{title}' has been scheduled.",
                        "type": "workflow",
                        "read": False
                    })

        elif table_name == "presentation_evaluations":
            for row in rows:
                team_id = row.get("team_id") or row.get("teamId") or row.get("team")
                score = row.get("total_score") or row.get("score")
                
                if team_id:
                    try:
                        trigger_evaluation_submitted_email(str(team_id), float(score))
                    except Exception as ev_err:
                        print(f"Failed to trigger evaluation email: {ev_err}")

                    student_emails = get_student_emails_in_team(str(team_id))
                    for email in student_emails:
                        notifications.append({
                            "recipient_email": email,
                            "recipient_role": "student",
                            "title": "Evaluation Submitted",
                            "message": f"Your team has been evaluated. Score: {score}/100",
                            "type": "evaluation",
                            "read": False
                        })

        elif table_name == "semester_config":
            for row in rows:
                if row.get("results_published") == True:
                    try:
                        trigger_results_published_email()
                    except Exception as res_err:
                        print(f"Failed to trigger results email: {res_err}")

                    student_emails = get_all_student_emails()
                    mentor_emails = get_all_mentor_emails()
                    
                    for email in student_emails:
                        notifications.append({
                            "recipient_email": email,
                            "recipient_role": "student",
                            "title": "Results Published",
                            "message": "Final semester results have been published by the administration.",
                            "type": "workflow",
                            "read": False
                        })
                    for email in mentor_emails:
                        notifications.append({
                            "recipient_email": email,
                            "recipient_role": "mentor",
                            "title": "Results Published",
                            "message": "Final semester results have been published by the administration.",
                            "type": "workflow",
                            "read": False
                        })

                if row.get("status") == "active" and row.get("is_active") == True:
                    try:
                        trigger_ps_released_email()
                    except Exception as ps_err:
                        print(f"Failed to trigger ps released email: {ps_err}")

        elif table_name == "students":
            student_list = [{"email": row.get("email"), "name": row.get("name", "Student")} for row in rows if row.get("email")]
            if student_list:
                try:
                    from app.email_notifier import trigger_batch_student_welcome_emails
                    trigger_batch_student_welcome_emails(student_list)
                except Exception as welcome_err:
                    print(f"Failed to trigger batch student welcome emails: {welcome_err}")

        elif table_name == "mentors":
            mentor_list = [{"email": row.get("email"), "name": row.get("name", "Mentor")} for row in rows if row.get("email")]
            if mentor_list:
                try:
                    from app.email_notifier import trigger_batch_mentor_welcome_emails
                    trigger_batch_mentor_welcome_emails(mentor_list)
                except Exception as welcome_err:
                    print(f"Failed to trigger batch mentor welcome emails: {welcome_err}")
            
            for row in rows:
                email = row.get("email")
                
                if email:
                    notifications.append({
                        "recipient_email": email,
                        "recipient_role": "mentor",
                        "title": "Assigned as Mentor",
                        "message": f"You have been successfully registered and assigned as a Mentor in the system.",
                        "type": "workflow",
                        "read": False
                    })

        elif table_name == "deadlines":
            from app.deadline_notice_core import build_deadline_update_rows, drop_already_sent

            # Fetched once, not once per row — the admin portal re-upserts every
            # deadline on every publish, so `rows` is the whole set.
            student_emails = get_all_student_emails()
            mentor_emails = get_all_mentor_emails()

            candidates = build_deadline_update_rows(rows, student_emails, mentor_emails)
            notifications.extend(
                drop_already_sent(candidates, _existing_deadline_notice_keys(candidates))
            )

            # Automatic deadline email dispatch disabled (triggered manually via admin action button)
            pass


        if notifications:
            try:
                service_client.table("notifications").insert(notifications).execute()
            except Exception as notif_err:
                print(f"Failed to insert notifications table rows: {notif_err}")
            
    except Exception as e:
        print(f"Failed to trigger notifications: {e}")
