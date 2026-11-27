"""Fixtures shared by the API test modules.

pytest finds fixtures in conftest.py by itself; importing them into a test module instead
would shadow them (ruff F811) and hide where they come from.
"""

from .test_api import api, gemini

__all__ = ["api", "gemini"]
