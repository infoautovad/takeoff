from fastapi import APIRouter

from app.api.routes import (
    admin,
    ai,
    auth,
    bid,
    boq,
    cad,
    compare,
    cost,
    dashboard,
    documents,
    notifications,
    projects,
    reports,
    search,
)

api_router = APIRouter(prefix="/api")
api_router.include_router(auth.router, prefix="/auth", tags=["auth"])
api_router.include_router(projects.router, prefix="/projects", tags=["projects"])
api_router.include_router(documents.router, prefix="/documents", tags=["documents"])
api_router.include_router(dashboard.router, prefix="/dashboard", tags=["dashboard"])
api_router.include_router(ai.router, prefix="/ai", tags=["ai"])
api_router.include_router(boq.router, prefix="/boq", tags=["boq"])
api_router.include_router(bid.router, prefix="/bid", tags=["bid"])
api_router.include_router(cost.router, prefix="/cost", tags=["cost"])
api_router.include_router(compare.router, prefix="/compare", tags=["compare"])
api_router.include_router(reports.router, prefix="/reports", tags=["reports"])
api_router.include_router(notifications.router, prefix="/notifications", tags=["notifications"])
api_router.include_router(search.router, prefix="/search", tags=["search"])
api_router.include_router(admin.router, prefix="/admin", tags=["admin"])
api_router.include_router(cad.router, prefix="/cad", tags=["cad"])
