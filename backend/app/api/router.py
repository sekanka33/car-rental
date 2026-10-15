from fastapi import APIRouter

from app.api.routes import (
    admin_bookings,
    admin_deliveries,
    admin_payments,
    admin_reports,
    admin_users,
    admin_vehicles,
    admin_verifications,
    auth,
    bookings,
    customers,
    dashboards,
    health,
    live,
    marketplace,
    owner_deliveries,
    owner_vehicles,
    owners,
    payments,
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
api_router.include_router(bookings.router)
api_router.include_router(admin_bookings.router)
api_router.include_router(payments.router)
api_router.include_router(admin_payments.router)
api_router.include_router(owner_deliveries.router)
api_router.include_router(admin_deliveries.router)
api_router.include_router(admin_reports.router)
api_router.include_router(live.router)
api_router.include_router(dashboards.router)
