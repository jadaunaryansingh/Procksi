import unittest

from sqlalchemy import Integer, String

from app.core.supabase_client import SupabaseRESTClient
from app.models.team import Team


class TeamModelSchemaTests(unittest.TestCase):
    def test_team_identifiers_match_the_live_database_schema(self):
        self.assertIsInstance(Team.__table__.c.id.type, Integer)
        self.assertIsNone(Team.__table__.c.id.default)
        self.assertIsInstance(Team.__table__.c.mentor_id.type, String)
        self.assertIsInstance(Team.__table__.c.semester_id.type, String)


class UnassignedStudentSyncTests(unittest.IsolatedAsyncioTestCase):
    async def test_sync_uses_one_idempotent_upsert_without_delete_insert_race(self):
        client = object.__new__(SupabaseRESTClient)
        calls = []

        async def request(path, method="GET", body=None, headers=None):
            calls.append((path, method, body, headers))
            if path == "students":
                return [{
                    "id": "student-1",
                    "student_id": "ROLL-1",
                    "name": "Student One",
                    "branch": "CSE",
                    "semester_id": "semester-1",
                }]
            if path == "teams_validation":
                return []
            return []

        client._request = request

        result = await client.sync_unassigned_students()

        self.assertEqual(result[0]["id"], "student-1")
        writes = [call for call in calls if call[1] != "GET"]
        self.assertEqual(len(writes), 1)
        path, method, body, headers = writes[0]
        self.assertEqual(path, "unassigned_students?on_conflict=id")
        self.assertEqual(method, "POST")
        self.assertEqual(body[0]["semester_id"], "semester-1")
        self.assertEqual(headers, {"Prefer": "resolution=merge-duplicates"})


if __name__ == "__main__":
    unittest.main()
