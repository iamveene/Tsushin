"""
Public API v1 Router Aggregator
Combines all v1 sub-routers into a single router for registration in app.py.
"""

from fastapi import APIRouter

from .routes_oauth import router as oauth_router
from .routes_agents import router as agents_router
from .routes_chat import router as chat_router
from .routes_resources import router as resources_router
from .routes_flows import router as flows_router
from .routes_hub import router as hub_router
from .routes_studio import router as studio_router

v1_router = APIRouter(tags=["Public API v1"])
v1_router.include_router(oauth_router, tags=["OAuth"])
v1_router.include_router(agents_router, tags=["Agents API"])
v1_router.include_router(chat_router, tags=["Chat API"])
v1_router.include_router(resources_router, tags=["Resources API"])
v1_router.include_router(flows_router, tags=["Flows API"])
v1_router.include_router(hub_router, tags=["Hub API"])
v1_router.include_router(studio_router, tags=["Studio API"])
