from fastapi import APIRouter

from app.api.routes import admin_users, auth, health, owners, users

api_router = APIRouter()
api_router.include_router(health.router)
api_router.include_router(auth.router)
api_router.include_router(users.router)
api_router.include_router(owners.router)
api_router.include_router(admin_users.router)
