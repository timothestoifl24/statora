from fastapi import APIRouter

from . import auth_providers, incidents, media, monitors, public, status_pages, users

router = APIRouter(prefix="/api/v1")
router.include_router(users.auth)
router.include_router(users.me)
router.include_router(monitors.router)
router.include_router(status_pages.router)
router.include_router(incidents.incidents)
router.include_router(incidents.maintenances)
router.include_router(users.users)
router.include_router(auth_providers.router)
router.include_router(media.router)
router.include_router(public.router)
