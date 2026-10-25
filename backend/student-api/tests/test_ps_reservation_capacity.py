import unittest
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

from app.api.student_portal import (
    PS_TEAM_CAPACITY,
    get_problem_statements,
    get_project_title_counts,
    is_ps_reservation_allowed,
    reserve_ps_atomically,
)


class PsReservationCapacityTests(unittest.TestCase):
    def test_capacity_decision_boundaries_and_current_holder(self):
        self.assertTrue(is_ps_reservation_allowed(0, None, "Smart Grid"))
        self.assertTrue(is_ps_reservation_allowed(1, None, "Smart Grid"))
        self.assertFalse(is_ps_reservation_allowed(2, None, "Smart Grid"))
        self.assertTrue(is_ps_reservation_allowed(2, " smart grid ", "Smart Grid"))


class ProjectTitleCountsTests(unittest.IsolatedAsyncioTestCase):
    async def test_deduplicates_approved_proposal_already_represented_by_team_uid(self):
        async def fake_request(path, method="GET", body=None, headers=None):
            if path == "teams_validation?select=id,uid,title":
                return [
                    {"id": "team-1", "uid": "uid-1", "title": "Smart Grid"},
                    {"id": "team-2", "uid": "uid-2", "title": " smart grid "},
                    {"id": "team-12", "uid": "uid-12", "title": "Team 12"},
                ]
            if path == "proposals?status=eq.Approved&select=id,teamId,team_uid,title":
                return [
                    {"id": "proposal-1", "teamId": "team-1", "team_uid": "uid-1", "title": "Smart Grid"},
                    {"id": "proposal-3", "teamId": "missing-team", "team_uid": None, "title": "Other Topic"},
                ]
            return []

        with patch("app.core.supabase_client.supabase_client._request", new=AsyncMock(side_effect=fake_request)):
            counts = await get_project_title_counts()

        self.assertEqual(counts["smart grid"], 2)
        self.assertEqual(counts["other topic"], 1)
        self.assertNotIn("team 12", counts)

    async def test_atomic_reservation_calls_rpc_with_immutable_ids_and_capacity(self):
        client = SimpleNamespace(_request=AsyncMock(return_value=[{"team_count": 2, "held_by_current_team": True}]))

        result = await reserve_ps_atomically(client, "team-1", "ps-7")

        self.assertEqual(result, {"team_count": 2, "held_by_current_team": True})
        client._request.assert_awaited_once_with(
            "rpc/reserve_problem_statement_atomic",
            method="POST",
            body={"p_team_id": "team-1", "p_problem_statement_id": "ps-7", "p_capacity": PS_TEAM_CAPACITY},
        )

    async def test_problem_statement_response_separates_full_from_held_by_current_team(self):
        student = SimpleNamespace(
            year=3,
            team_membership=SimpleNamespace(team=SimpleNamespace(project_title="Smart Grid")),
        )
        statements = [
            {"id": "ps-1", "title": "Smart Grid", "year": 3, "domain": "IoT"},
            {"id": "ps-2", "title": "Other Topic", "year": 3, "domain": "Web"},
        ]
        with patch("app.core.supabase_client.supabase_client.get_problem_statements", new=AsyncMock(return_value=statements)), patch(
            "app.api.student_portal.get_project_title_counts", new=AsyncMock(return_value={"smart grid": 1, "other topic": 2})
        ):
            response = await get_problem_statements(student)

        by_id = {item["id"]: item for item in response["data"]}
        self.assertTrue(by_id["ps-1"]["is_held_by_current_team"])
        self.assertFalse(by_id["ps-1"]["is_allocated"])
        self.assertFalse(by_id["ps-2"]["is_held_by_current_team"])
        self.assertTrue(by_id["ps-2"]["is_allocated"])


if __name__ == "__main__":
    unittest.main()
