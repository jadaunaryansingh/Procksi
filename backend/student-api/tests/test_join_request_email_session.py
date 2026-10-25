import ast
from pathlib import Path
import unittest


SOURCE_PATH = Path(__file__).parents[1] / "app" / "api" / "student_portal.py"


class JoinRequestEmailSessionTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tree = ast.parse(SOURCE_PATH.read_text(encoding="utf-8"))

    def test_background_email_helper_owns_its_database_session(self):
        helper = next(
            node
            for node in ast.walk(self.tree)
            if isinstance(node, ast.AsyncFunctionDef)
            and node.name == "trigger_join_request_accepted_emails"
        )

        self.assertEqual(
            [argument.arg for argument in helper.args.args],
            ["invitee_id", "leader_id", "team_id"],
        )
        self.assertTrue(
            any(
                isinstance(node, ast.AsyncWith)
                and any(
                    isinstance(item.context_expr, ast.Call)
                    and isinstance(item.context_expr.func, ast.Name)
                    and item.context_expr.func.id == "async_session_factory"
                    for item in node.items
                )
                for node in ast.walk(helper)
            ),
            "background helper must create a fresh session with async_session_factory",
        )

    def test_accept_handler_does_not_pass_request_session_to_background_task(self):
        accept_handler = next(
            node
            for node in ast.walk(self.tree)
            if isinstance(node, ast.AsyncFunctionDef)
            and node.name == "accept_join_request"
        )
        email_calls = [
            node
            for node in ast.walk(accept_handler)
            if isinstance(node, ast.Call)
            and isinstance(node.func, ast.Name)
            and node.func.id == "trigger_join_request_accepted_emails"
        ]

        self.assertEqual(len(email_calls), 1)
        self.assertEqual(len(email_calls[0].args), 3)


if __name__ == "__main__":
    unittest.main()
