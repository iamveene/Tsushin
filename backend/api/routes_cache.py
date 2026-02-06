"""
Phase 6.11.3: Cache Management API

Provides endpoints for cache statistics and manual cache clearing.

Security: HIGH-010 fix - All endpoints require org.settings.write permission (2026-02-02)
Cache operations are system-wide admin operations.
"""

from fastapi import APIRouter, Depends
from datetime import datetime
import logging

from models_rbac import User
from auth_dependencies import require_permission

logger = logging.getLogger(__name__)

router = APIRouter()


@router.get("/api/cache/contacts/stats")
async def get_contact_cache_stats(
    current_user: User = Depends(require_permission("org.settings.write"))
):
    """
    Get contact cache statistics.

    Requires: org.settings.write permission (admin only)
    """
    try:
        from app import app
        if hasattr(app.state, 'contact_service'):
            return app.state.contact_service.get_cache_stats()
        return {"error": "Contact cache not initialized"}
    except Exception as e:
        logger.error(f"Error getting contact cache stats: {e}", exc_info=True)
        return {"error": str(e)}


@router.post("/api/cache/contacts/clear")
async def clear_contact_cache(
    current_user: User = Depends(require_permission("org.settings.write"))
):
    """
    Manually clear contact cache.

    Requires: org.settings.write permission (admin only)
    """
    try:
        from app import app
        if hasattr(app.state, 'contact_service'):
            app.state.contact_service.clear_cache()
            logger.info(f"Contact cache cleared by user {current_user.id} ({current_user.email})")
            return {"message": "Contact cache cleared successfully"}
        return {"error": "Contact cache not initialized"}
    except Exception as e:
        logger.error(f"Error clearing contact cache: {e}", exc_info=True)
        return {"error": str(e)}


@router.get("/api/cache/stats")
async def get_all_cache_stats(
    current_user: User = Depends(require_permission("org.settings.write"))
):
    """
    Get all cache statistics.

    Requires: org.settings.write permission (admin only)
    """
    try:
        from app import app
        stats = {}

        # Contact cache stats
        if hasattr(app.state, 'contact_service'):
            stats['contact_cache'] = app.state.contact_service.get_cache_stats()

        # Semantic cache stats (will be added in next task)
        # if hasattr(app.state, 'semantic_cache'):
        #     stats['semantic_cache'] = app.state.semantic_cache.get_cache_stats()

        stats['timestamp'] = datetime.utcnow().isoformat() + 'Z'

        return stats
    except Exception as e:
        logger.error(f"Error getting cache stats: {e}", exc_info=True)
        return {"error": str(e)}


@router.post("/api/cache/clear-all")
async def clear_all_caches(
    current_user: User = Depends(require_permission("org.settings.write"))
):
    """
    Clear all caches.

    Requires: org.settings.write permission (admin only)
    """
    try:
        from app import app
        cleared = []

        # Clear contact cache
        if hasattr(app.state, 'contact_service'):
            app.state.contact_service.clear_cache()
            cleared.append("contact_cache")

        # Clear semantic cache (will be added in next task)
        # if hasattr(app.state, 'semantic_cache'):
        #     app.state.semantic_cache.clear_cache()
        #     cleared.append("semantic_cache")

        logger.info(f"All caches cleared by user {current_user.id} ({current_user.email}): {cleared}")
        return {
            "message": "Caches cleared successfully",
            "cleared": cleared
        }
    except Exception as e:
        logger.error(f"Error clearing all caches: {e}", exc_info=True)
        return {"error": str(e)}
