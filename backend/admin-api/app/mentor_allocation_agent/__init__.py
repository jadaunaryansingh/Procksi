"""Mentor Allocation Agent — self-contained package.

Public entrypoint: ``build_allocation_router(service_client)`` returns the FastAPI
router that admin-api mounts. All agent logic (scoring engine, endpoints, schema
migration) lives in this folder.
"""
from app.mentor_allocation_agent.agent import build_allocation_router

__all__ = ["build_allocation_router"]
