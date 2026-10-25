from fastapi import APIRouter, Depends

from statora.web.deps import verify_csrf

from . import incidents, media, monitors, pages, users

router = APIRouter(prefix="/admin", include_in_schema=False, dependencies=[Depends(verify_csrf)])
router.add_api_route("", monitors.dashboard, methods=["GET"])
router.include_router(monitors.router)
router.include_router(pages.router)
router.include_router(incidents.router)
router.include_router(users.router)
router.include_router(media.router)
