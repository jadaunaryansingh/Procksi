import sqlalchemy as sa

AdminRole = sa.Enum("ADMIN", "SUPER_ADMIN", name="admin_role", create_type=True)
StudentStatus = sa.Enum("active", "inactive", "graduated", name="student_status", create_type=True)
ProposalStatus = sa.Enum("pending", "approved", "rejected", "revision", name="proposal_status", create_type=True)
TeamRole = sa.Enum("LEADER", "MEMBER", name="team_role", create_type=True)
EvaluationType = sa.Enum("proposal", "mid", "final", name="evaluation_type", create_type=True)
DeadlineType = sa.Enum("proposal", "team", "evaluation", name="deadline_type", create_type=True)
TeamStatus = sa.Enum("valid", "pending", "invalid", name="team_status", create_type=True)
SemesterType = sa.Enum("odd", "even", name="semester_type", create_type=True)
