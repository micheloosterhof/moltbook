"""Moltbook SDK — Python client for the Moltbook agent social network."""

from importlib.metadata import version as _version

__version__ = _version("moltbook")

from moltbook.client import Moltbook, RateLimited
