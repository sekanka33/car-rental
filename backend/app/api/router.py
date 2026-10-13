from fastapi import APIRouter

from app.api.routes import (
    admin_users,
    admin_vehicles,
    admin_verifications,
    auth,
    customers,
    health,
    marketplace,
    owner_vehicles,
    owners,
    users,
)

api_router = APIRouter()
api_router.include_router(health.router)
api_router.include_router(auth.router)
api_router.include_router(users.router)
api_router.include_router(owners.router)
api_router.include_router(admin_users.router)
api_router.include_router(customers.router)
api_router.include_router(admin_verifications.router)
api_router.include_router(owner_vehicles.router)
api_router.include_router(admin_vehicles.router)
api_router.include_router(marketplace.router)
