from fastapi import FastAPI
from tortoise.contrib.fastapi import register_tortoise
from models import User
from passlib.context import CryptContext
import uuid, asyncio
from fastapi.middleware.cors import CORSMiddleware
import models, os
print("▶️ Loading models from:", models.__file__)
from routers import auth, users, meter_data, billing
pwd_ctx = CryptContext(schemes=["bcrypt"], deprecated="auto")

app = FastAPI(title="SDI Admin API")

# Add this CORS middleware before you include your routers:
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173"],  # your React dev server
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
    expose_headers=["Content-Range", "X-Total-Count"],
)

app.include_router(auth.router)
app.include_router(users.router)
app.include_router(meter_data.router)
app.include_router(billing.router)

register_tortoise(
    app,
    db_url="sqlite://./db.sqlite3",
    modules={"models": ["models"]},
    generate_schemas=True,
    add_exception_handlers=True,
)
@app.on_event("startup")
async def seed_admin():
    if not await User.exists():
        await User.create(
            id=uuid.uuid4(),
            username="admin",
            email="admin@example.com",
            hashed_password=pwd_ctx.hash("password123"),
            is_admin=True,
        )

import models
@app.on_event("startup")
async def inspect_models():
    print("Billing attributes:", [attr for attr in dir(models.Billing) if not attr.startswith("_")])

@app.on_event("startup")
async def debug_billing_fields():
    # Print out exactly which field names Tortoise knows about
    print("🧐 Billing._meta.fields_map keys:", list(models.Billing._meta.fields_map.keys()))