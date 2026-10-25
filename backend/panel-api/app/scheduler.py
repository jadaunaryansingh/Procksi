"""
Scheduler Service for Panel Portal
Implements reminder system, slot activation, and auto-lock functionality
using Supabase instead of SQLAlchemy.
"""

import asyncio
from datetime import datetime, timedelta, timezone
from typing import List, Optional

from app.supabase_client import get_supabase_service


class SchedulerService:
    def __init__(self):
        self.running = False
        self.task = None
    
    async def start(self):
        """Start the scheduler service"""
        if self.running:
            return
        
        self.running = True
        self.task = asyncio.create_task(self._scheduler_loop())
        print("Scheduler service started")
    
    async def stop(self):
        """Stop the scheduler service"""
        self.running = False
        if self.task:
            self.task.cancel()
            try:
                await self.task
            except asyncio.CancelledError:
                pass
        print("Scheduler service stopped")
    
    async def _scheduler_loop(self):
        """Main scheduler loop - runs every minute"""
        while self.running:
            try:
                await self._process_reminders()
                await self._check_missed_submissions()
                await self._activate_slots()
                await asyncio.sleep(60)  # Check every minute
            except asyncio.CancelledError:
                break
            except Exception as e:
                print(f"Scheduler error: {e}")
                await asyncio.sleep(60)
    
    async def _process_reminders(self):
        """Send reminders during active slots"""
        client = get_supabase_service()
        if client is None:
            return
            
        now = datetime.now(timezone.utc)
        
        # Get active slots
        res_slots = client.table("slots").select("*").eq("status", "Active").execute()
        active_slots = res_slots.data
        
        for slot in active_slots:
            ws_val = datetime.fromisoformat(slot["window_start"].replace("Z", "+00:00"))
            we_val = datetime.fromisoformat(slot["window_end"].replace("Z", "+00:00"))
            if not (ws_val <= now <= we_val):
                continue
                
            # Check if evaluation has been submitted
            res_eval = client.table("evaluations").select("id")\
                .eq("team_id", slot["team_id"])\
                .eq("panel_id", slot["panel_id"])\
                .execute()
                
            if not res_eval.data:
                await self._send_reminder(client, slot, now)
    
    def _get_clean_team_name(self, client, team_id: str) -> str:
        if not team_id:
            return "Team"
        text_id = str(team_id).strip()
        try:
            res_team = client.table("teams").select("name").eq("id", team_id).execute()
            if res_team.data and res_team.data[0].get("name"):
                name = str(res_team.data[0]["name"]).strip()
                if not re.search(r"^[0-9a-fA-F]{8}-[0-9a-fA-F]{4}", name):
                    return name
        except Exception:
            pass

        m = re.search(r"[-_]?[Tt](?:eam)?[-_]?\s*(\d+)", text_id, re.IGNORECASE) or re.search(r"(\d+)", text_id)
        if m:
            return f"Team {m.group(1)}"

        clean = re.sub(r"[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}[-_]?", "", text_id).strip()
        return clean if clean else "Team"

    async def _send_reminder(self, client, slot, now: datetime):
        """Send reminder to panel for pending evaluation"""
        # Check if reminder was already sent in the last 30 minutes
        cutoff = (now - timedelta(minutes=30)).isoformat()
        res_recent = client.table("alerts").select("id")\
            .eq("team_id", slot["team_id"])\
            .eq("panel_id", slot["panel_id"])\
            .eq("alert_type", "reminder")\
            .gte("created_at", cutoff)\
            .is_("acknowledged_at", "null")\
            .execute()
            
        if res_recent.data:
            return
            
        # Get clean team name
        team_name = self._get_clean_team_name(client, slot["team_id"])
        
        we_val = datetime.fromisoformat(slot["window_end"].replace("Z", "+00:00"))
        # Create reminder alert
        client.table("alerts").insert({
            "team_id": slot["team_id"],
            "panel_id": slot["panel_id"],
            "alert_type": "reminder",
            "title": f"Evaluation Reminder - {team_name}",
            "body": f"Please submit evaluation for {team_name} before {we_val.strftime('%I:%M %p')}",
            "created_at": now.isoformat()
        }).execute()
        
        print(f"Reminder sent for {team_name} to Panel {slot['panel_id']}")
    
    async def _check_missed_submissions(self):
        """Mark missed submissions and notify admin"""
        client = get_supabase_service()
        if client is None:
            return
            
        now = datetime.now(timezone.utc)
        
        # Get slots that ended in the last hour and are still Active
        cutoff = (now - timedelta(hours=1)).isoformat()
        res_slots = client.table("slots").select("*")\
            .eq("status", "Active")\
            .lte("window_end", now.isoformat())\
            .gte("window_end", cutoff)\
            .execute()
            
        for slot in res_slots.data:
            # Check if evaluation was submitted
            res_eval = client.table("evaluations").select("id")\
                .eq("team_id", slot["team_id"])\
                .eq("panel_id", slot["panel_id"])\
                .execute()
                
            if not res_eval.data:
                await self._mark_missed_submission(client, slot, now)
    
    async def _mark_missed_submission(self, client, slot, now: datetime):
        """Mark evaluation as missed and notify admin"""
        team_name = self._get_clean_team_name(client, slot["team_id"])
        
        we_val = datetime.fromisoformat(slot["window_end"].replace("Z", "+00:00"))
        # Create missed submission alert
        client.table("alerts").insert({
            "team_id": slot["team_id"],
            "panel_id": slot["panel_id"],
            "alert_type": "missed",
            "title": f"Missed Submission - {team_name}",
            "body": f"Evaluation for {team_name} was not submitted by deadline {we_val.strftime('%I:%M %p')}",
            "created_at": now.isoformat()
        }).execute()
        
        # Update slot status
        client.table("slots").update({"status": "Missed"}).eq("id", slot["id"]).execute()
        print(f"Missed submission marked for {team_name}")
    
    async def _activate_slots(self):
        """Activate all upcoming slots whose window has started"""
        client = get_supabase_service()
        if client is None:
            return
            
        now = datetime.now(timezone.utc)
        
        # Activate any upcoming slot whose window_start is in the past and window_end in the future
        res_slots = client.table("slots").select("*")\
            .eq("status", "Upcoming")\
            .lte("window_start", now.isoformat())\
            .gte("window_end", now.isoformat())\
            .execute()
            
        for slot in res_slots.data:
            client.table("slots").update({"status": "Active"}).eq("id", slot["id"]).execute()
            await self._send_activation_notification(client, slot, now)
    
    async def _send_activation_notification(self, client, slot, now: datetime):
        team_name = self._get_clean_team_name(client, slot["team_id"])
        
        client.table("alerts").insert({
            "team_id": slot["team_id"],
            "panel_id": slot["panel_id"],
            "alert_type": "activation",
            "title": f"Evaluation Slot Active - {team_name}",
            "body": f"Evaluation slot for {team_name} is now active. You can submit the evaluation.",
            "created_at": now.isoformat()
        }).execute()
        print(f"Slot activated for {team_name}")


# Global scheduler instance
scheduler = SchedulerService()


# Background task to start scheduler
async def start_scheduler():
    await scheduler.start()


# Function to get active reminders for a panel
def get_panel_reminders(panel_id: str) -> List[dict]:
    client = get_supabase_service()
    if client is None:
        return []
    res = client.table("alerts").select("*")\
        .eq("panel_id", panel_id)\
        .is_("acknowledged_at", "null")\
        .order("created_at", desc=True)\
        .execute()
    return res.data


# Function to mark alert as read
def mark_alert_read(alert_id: int, panel_id: str) -> bool:
    client = get_supabase_service()
    if client is None:
        return False
    res = client.table("alerts").update({"acknowledged_at": datetime.now(timezone.utc).isoformat()})\
        .eq("id", alert_id)\
        .eq("panel_id", panel_id)\
        .execute()
    return bool(res.data)
