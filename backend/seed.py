"""Seed initial data: a tenant, branch, shift, and admin user. Employees are added via the dashboard."""
import asyncio
from datetime import time
from sqlalchemy import select
from app.db.base import AsyncSessionLocal, engine, Base
from app.models import Tenant, Branch, Shift, User
from app.core.security import hash_password


async def seed():
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    async with AsyncSessionLocal() as db:
        existing = (await db.execute(select(Tenant).where(Tenant.slug == "demo"))).scalar_one_or_none()
        if existing:
            print("Demo tenant already exists.")
            return

        tenant = Tenant(name="Demo Corp", slug="demo", plan="pro",
                        max_employees=500, max_cameras=20)
        db.add(tenant); await db.flush()

        branch = Branch(tenant_id=tenant.id, name="Dhaka HQ", code="DHK",
                        timezone="Asia/Dhaka")
        db.add(branch); await db.flush()

        shift = Shift(tenant_id=tenant.id, branch_id=branch.id, name="General",
                      start_time=time(9, 0), end_time=time(18, 0),
                      grace_in_min=10, early_out_min=15)
        db.add(shift); await db.flush()

        admin = User(tenant_id=tenant.id, email="admin@demo.com",
                     hashed_password=hash_password("admin123"),
                     full_name="System Admin", role="super_admin")
        db.add(admin)

        await db.commit()
        print(f"Seeded tenant={tenant.id}  login=admin@demo.com / admin123")
        print("No demo employees created. Add real employees via the dashboard.")


if __name__ == "__main__":
    asyncio.run(seed())
