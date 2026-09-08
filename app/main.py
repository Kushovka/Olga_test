import asyncio
import contextlib
import json
import os
import random
import secrets
from contextlib import asynccontextmanager
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import AsyncIterator, Literal

from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import FileResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field
from sqlalchemy import DateTime, ForeignKey, Integer, String, UniqueConstraint, func, select, text
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column

DATABASE_URL = os.getenv("DATABASE_URL", "postgresql+asyncpg://game_store:game_store@localhost:5432/game_store")
engine = create_async_engine(DATABASE_URL, pool_pre_ping=True)
Session = async_sessionmaker(engine, expire_on_commit=False)
ROOT = Path(__file__).resolve().parent.parent
RESERVATION_SECONDS = max(30, int(os.getenv("RESERVATION_SECONDS", "180")))
catalog_subscribers: set[asyncio.Queue[str]] = set()


class Base(DeclarativeBase):
    pass


class Product(Base):
    __tablename__ = "products"
    sku: Mapped[str] = mapped_column(String(64), primary_key=True)
    name: Mapped[str] = mapped_column(String(180))
    price: Mapped[int] = mapped_column(Integer)
    kind: Mapped[str] = mapped_column(String(32), default="key")
    cover: Mapped[str] = mapped_column(String(32), default="violet")


class InventoryKey(Base):
    __tablename__ = "inventory_keys"
    id: Mapped[int] = mapped_column(primary_key=True)
    sku: Mapped[str] = mapped_column(ForeignKey("products.sku"), index=True)
    code: Mapped[str] = mapped_column(String(128), unique=True)
    state: Mapped[str] = mapped_column(String(20), default="available", index=True)
    order_id: Mapped[str | None] = mapped_column(String(64), nullable=True, unique=True)


class Order(Base):
    __tablename__ = "orders"
    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    sku: Mapped[str] = mapped_column(ForeignKey("products.sku"))
    amount: Mapped[int] = mapped_column(Integer)
    status: Mapped[str] = mapped_column(String(32), default="reserved", index=True)
    promo_code: Mapped[str | None] = mapped_column(String(32), nullable=True)
    reserved_key_id: Mapped[int | None] = mapped_column(ForeignKey("inventory_keys.id"), nullable=True, unique=True)
    reservation_expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True, index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), onupdate=lambda: datetime.now(timezone.utc))


class PaymentEvent(Base):
    __tablename__ = "payment_events"
    event_id: Mapped[str] = mapped_column(String(80), primary_key=True)
    order_id: Mapped[str] = mapped_column(String(64), index=True)
    status: Mapped[str] = mapped_column(String(20))
    amount: Mapped[int] = mapped_column(Integer)
    currency: Mapped[str] = mapped_column(String(8), default="RUB")
    applied_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    received_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))


class Delivery(Base):
    __tablename__ = "deliveries"
    __table_args__ = (UniqueConstraint("order_id", name="one_delivery_per_order"),)
    id: Mapped[int] = mapped_column(primary_key=True)
    order_id: Mapped[str] = mapped_column(ForeignKey("orders.id"), unique=True)
    provider_request_id: Mapped[str] = mapped_column(String(100), unique=True)
    inventory_key_id: Mapped[int] = mapped_column(ForeignKey("inventory_keys.id"), unique=True)
    code: Mapped[str] = mapped_column(String(128))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))


class SupplierRequest(Base):
    __tablename__ = "supplier_requests"
    request_id: Mapped[str] = mapped_column(String(100), primary_key=True)
    provider: Mapped[str] = mapped_column(String(1))
    order_id: Mapped[str] = mapped_column(String(64), index=True)
    sku: Mapped[str] = mapped_column(String(64))
    outcome: Mapped[str] = mapped_column(String(32))
    code: Mapped[str | None] = mapped_column(String(128), nullable=True)
    inventory_key_id: Mapped[int | None] = mapped_column(Integer, nullable=True)


class ProviderConfig(Base):
    __tablename__ = "provider_config"
    provider: Mapped[str] = mapped_column(String(1), primary_key=True)
    mode: Mapped[str] = mapped_column(String(32), default="success")
    error_rate: Mapped[int] = mapped_column(Integer, default=0)
    timeout_rate: Mapped[int] = mapped_column(Integer, default=0)
    delay_ms: Mapped[int] = mapped_column(Integer, default=0)


class Promocode(Base):
    __tablename__ = "promocodes"
    code: Mapped[str] = mapped_column(String(32), primary_key=True)
    discount_type: Mapped[str] = mapped_column(String(16))
    value: Mapped[int] = mapped_column(Integer)
    max_uses: Mapped[int] = mapped_column(Integer)
    used_count: Mapped[int] = mapped_column(Integer, default=0)


class PromoUse(Base):
    __tablename__ = "promo_uses"
    __table_args__ = (UniqueConstraint("order_id", name="one_promo_per_order"),)
    id: Mapped[int] = mapped_column(primary_key=True)
    order_id: Mapped[str] = mapped_column(String(64), unique=True)
    code: Mapped[str] = mapped_column(String(32))


CATALOG = [
    ("STEAM-TOPUP-500", "Пополнение Steam 500 ₽", 500, "topup", "steam"),
    ("KEY-CS2-PRIME", "CS2 Prime Status", 1290, "key", "cyan"),
    ("KEY-GTA5", "GTA V: ключ активации", 1990, "key", "sunset"),
    ("KEY-EFT", "Escape from Tarkov", 3490, "key", "forest"),
    ("SUB-DISCORD-1M", "Discord Nitro • 1 месяц", 399, "subscription", "pink"),
]
PROMOS = [("WELCOME10", "percent", 10, 100), ("GG500", "amount", 500, 20), ("LIMIT3", "percent", 25, 3), ("ONCEONLY", "percent", 50, 1)]


async def seed() -> None:
    async with Session.begin() as db:
        for sku, name, price, kind, cover in CATALOG:
            await db.execute(insert(Product).values(sku=sku, name=name, price=price, kind=kind, cover=cover).on_conflict_do_nothing())
        for code, typ, value, limit in PROMOS:
            await db.execute(insert(Promocode).values(code=code, discount_type=typ, value=value, max_uses=limit).on_conflict_do_nothing())
        for provider in ("A", "B"):
            await db.execute(insert(ProviderConfig).values(provider=provider, mode="success").on_conflict_do_nothing())
        existing = (await db.execute(select(InventoryKey.id).limit(1))).first()
        if not existing:
            for sku, *_ in CATALOG:
                for n in range(12):
                    await db.execute(insert(InventoryKey).values(sku=sku, code=f"{sku[:5]}-{n:04d}-{secrets.token_hex(3).upper()}"))


async def release_expired_reservations(db: AsyncSession) -> bool:
    """Return keys from elapsed checkout reservations under row locks."""
    now = datetime.now(timezone.utc)
    orders = (await db.scalars(
        select(Order)
        .where(Order.status == "reserved", Order.reservation_expires_at.is_not(None), Order.reservation_expires_at <= now)
        .with_for_update(skip_locked=True)
    )).all()
    for order in orders:
        if order.reserved_key_id:
            key = await db.scalar(select(InventoryKey).where(InventoryKey.id == order.reserved_key_id).with_for_update())
            if key and key.order_id == order.id and key.state == "reserved":
                key.state, key.order_id = "available", None
            order.reserved_key_id = None
        order.status = "reservation_expired"
    return bool(orders)


async def release_expired_reservations_now() -> bool:
    async with Session.begin() as db:
        return await release_expired_reservations(db)


async def catalog_snapshot() -> list[dict]:
    async with Session() as db:
        stock_rows = (await db.execute(
            select(InventoryKey.sku, func.count(InventoryKey.id))
            .where(InventoryKey.state == "available")
            .group_by(InventoryKey.sku)
        )).all()
        available = {sku: count for sku, count in stock_rows}
        rows = (await db.scalars(select(Product).order_by(Product.price))).all()
        return [{"sku": p.sku, "name": p.name, "price": p.price, "kind": p.kind, "cover": p.cover,
                 "available": available.get(p.sku, 0), "in_stock": available.get(p.sku, 0) > 0} for p in rows]


async def publish_catalog() -> None:
    if not catalog_subscribers:
        return
    payload = json.dumps(await catalog_snapshot(), ensure_ascii=False)
    for queue in tuple(catalog_subscribers):
        if queue.full():
            with contextlib.suppress(asyncio.QueueEmpty):
                queue.get_nowait()
        with contextlib.suppress(asyncio.QueueFull):
            queue.put_nowait(payload)


async def reservation_reaper() -> None:
    while True:
        await asyncio.sleep(1)
        if await release_expired_reservations_now():
            await publish_catalog()


@asynccontextmanager
async def lifespan(_: FastAPI):
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
        await conn.execute(text("ALTER TABLE provider_config ADD COLUMN IF NOT EXISTS error_rate INTEGER NOT NULL DEFAULT 0"))
        await conn.execute(text("ALTER TABLE provider_config ADD COLUMN IF NOT EXISTS timeout_rate INTEGER NOT NULL DEFAULT 0"))
        await conn.execute(text("ALTER TABLE provider_config ADD COLUMN IF NOT EXISTS delay_ms INTEGER NOT NULL DEFAULT 0"))
        await conn.execute(text("ALTER TABLE orders ADD COLUMN IF NOT EXISTS reserved_key_id INTEGER UNIQUE REFERENCES inventory_keys(id)"))
        await conn.execute(text("ALTER TABLE orders ADD COLUMN IF NOT EXISTS reservation_expires_at TIMESTAMPTZ"))
    await seed()
    reaper = asyncio.create_task(reservation_reaper())
    try:
        yield
    finally:
        reaper.cancel()
        with contextlib.suppress(asyncio.CancelledError):
            await reaper
        await engine.dispose()


app = FastAPI(title="Game Market API", lifespan=lifespan)
app.mount("/assets", StaticFiles(directory=ROOT / "public"), name="assets")


class OrderInput(BaseModel):
    sku: str
    promo_code: str | None = None
    order_id: str | None = Field(default=None, pattern=r"^[A-Za-z0-9_-]{4,64}$")


class WebhookInput(BaseModel):
    event_id: str
    order_id: str
    status: Literal["paid", "failed"]
    amount: int = 0
    currency: str = "RUB"


class ProviderModeInput(BaseModel):
    mode: Literal["success", "error", "timeout_after_issue", "out_of_stock"]
    error_rate: int = Field(default=0, ge=0, le=100)
    timeout_rate: int = Field(default=0, ge=0, le=100)
    delay_ms: int = Field(default=0, ge=0, le=10_000)


class ProductUpdateInput(BaseModel):
    price: int = Field(ge=0, le=1_000_000)


async def apply_waiting_events(order_id: str) -> None:
    changed_catalog = False
    async with Session.begin() as db:
        await release_expired_reservations(db)
        order = await db.scalar(select(Order).where(Order.id == order_id).with_for_update())
        if not order:
            return
        events = (await db.scalars(select(PaymentEvent).where(PaymentEvent.order_id == order_id, PaymentEvent.applied_at.is_(None)).order_by(PaymentEvent.received_at))).all()
        for event in events:
            # A successful-looking event with another amount/currency must never
            # grant a product. It is consumed for idempotency, while a later valid
            # event may still confirm the order.
            if event.status == "paid" and event.amount == order.amount and event.currency == "RUB" and order.status == "reserved":
                order.status = "paid"
            elif event.status == "failed" and order.status == "reserved":
                order.status = "payment_failed"
                if order.reserved_key_id:
                    key = await db.scalar(select(InventoryKey).where(InventoryKey.id == order.reserved_key_id).with_for_update())
                    if key and key.order_id == order.id and key.state == "reserved":
                        key.state, key.order_id = "available", None
                        changed_catalog = True
                    order.reserved_key_id = None
            event.applied_at = datetime.now(timezone.utc)
    if changed_catalog:
        await publish_catalog()
    await schedule_delivery(order_id)


async def supplier_issue(provider: str, order_id: str, sku: str, request_id: str) -> tuple[str, str | None, int | None]:
    """A supplier is idempotent by request id. A timeout after issue keeps the issued code durable."""
    delay_ms = 0
    async with Session.begin() as db:
        old = await db.scalar(select(SupplierRequest).where(SupplierRequest.request_id == request_id).with_for_update())
        if old:
            # The first response may have been lost. A retry of the same id reveals
            # the already-issued code; it never allocates another inventory record.
            outcome = "ok" if old.outcome == "timeout_after_issue" else old.outcome
            return outcome, old.code, old.inventory_key_id
        config = await db.get(ProviderConfig, provider, with_for_update=True)
        mode = config.mode if config else "success"
        delay_ms = config.delay_ms if config else 0
        if mode == "success":
            roll = random.randrange(100)
            if config and roll < config.error_rate:
                mode = "error"
            elif config and roll < config.error_rate + config.timeout_rate:
                mode = "timeout_after_issue"
        if mode == "error":
            db.add(SupplierRequest(request_id=request_id, provider=provider, order_id=order_id, sku=sku, outcome="error"))
            result = ("error", None, None)
        elif mode == "out_of_stock":
            db.add(SupplierRequest(request_id=request_id, provider=provider, order_id=order_id, sku=sku, outcome="out_of_stock"))
            result = ("out_of_stock", None, None)
        else:
            # Normal checkout already owns a reservation. A fallback allocation is
            # kept only for old/recovery orders created before reservation support.
            key = await db.scalar(select(InventoryKey).where(InventoryKey.order_id == order_id, InventoryKey.state == "reserved").with_for_update())
            if not key:
                key = await db.scalar(select(InventoryKey).where(InventoryKey.sku == sku, InventoryKey.state == "available").order_by(InventoryKey.id).with_for_update(skip_locked=True))
            if not key:
                db.add(SupplierRequest(request_id=request_id, provider=provider, order_id=order_id, sku=sku, outcome="out_of_stock"))
                result = ("out_of_stock", None, None)
            else:
                key.state, key.order_id = "reserved", order_id
                outcome = "timeout_after_issue" if mode == "timeout_after_issue" else "ok"
                db.add(SupplierRequest(request_id=request_id, provider=provider, order_id=order_id, sku=sku, outcome=outcome, code=key.code, inventory_key_id=key.id))
                result = (outcome, key.code, key.id)
    if delay_ms:
        await asyncio.sleep(delay_ms / 1000)
    return result


async def schedule_delivery(order_id: str) -> None:
    """Claims the order under a row lock; only the winner performs supplier work."""
    async with Session.begin() as db:
        order = await db.scalar(select(Order).where(Order.id == order_id).with_for_update())
        if not order or order.status not in {"paid", "out_of_stock", "delivery_failed"}:
            return
        has_delivery = await db.scalar(select(Delivery.id).where(Delivery.order_id == order_id))
        if has_delivery:
            order.status = "delivered"
            return
        order.status = "delivering"
        sku = order.sku
    await deliver(order_id, sku)


async def next_supplier_request_id(order_id: str, provider: str) -> str:
    """Only an ambiguous timeout keeps its request id; stock/failure retries are new attempts."""
    async with Session() as db:
        timeout_request = await db.scalar(select(SupplierRequest.request_id).where(SupplierRequest.order_id == order_id, SupplierRequest.provider == provider, SupplierRequest.outcome == "timeout_after_issue"))
        if timeout_request:
            return timeout_request
        attempts = len((await db.scalars(select(SupplierRequest.request_id).where(SupplierRequest.order_id == order_id, SupplierRequest.provider == provider))).all())
        return f"issue-{order_id}-{provider}-{attempts + 1}"


async def deliver(order_id: str, sku: str) -> None:
    request_id = await next_supplier_request_id(order_id, "A")
    outcome, code, key_id = await supplier_issue("A", order_id, sku, request_id)
    if outcome == "timeout_after_issue":
        # Ambiguous result: never fall back to B. Retry the exact same request id later.
        await mark_recoverable(order_id, "delivery_failed")
        return
    if outcome == "error":
        request_id = await next_supplier_request_id(order_id, "B")
        outcome, code, key_id = await supplier_issue("B", order_id, sku, request_id)
    if outcome == "ok" and code and key_id:
        async with Session.begin() as db:
            order = await db.scalar(select(Order).where(Order.id == order_id).with_for_update())
            if not order:
                return
            exists = await db.scalar(select(Delivery.id).where(Delivery.order_id == order_id))
            if not exists:
                db.add(Delivery(order_id=order_id, provider_request_id=request_id, inventory_key_id=key_id, code=code))
                key = await db.scalar(select(InventoryKey).where(InventoryKey.id == key_id).with_for_update())
                if key:
                    key.state = "issued"
                order.status = "delivered"
        await publish_catalog()
        return
    await mark_recoverable(order_id, "out_of_stock" if outcome == "out_of_stock" else "delivery_failed")


async def mark_recoverable(order_id: str, status: str) -> None:
    async with Session.begin() as db:
        order = await db.scalar(select(Order).where(Order.id == order_id).with_for_update())
        if order and order.status != "delivered":
            order.status = status


async def view_order(db: AsyncSession, order_id: str) -> dict:
    order = await db.get(Order, order_id)
    if not order:
        raise HTTPException(404, "Заказ не найден")
    delivery = await db.scalar(select(Delivery).where(Delivery.order_id == order.id))
    product = await db.get(Product, order.sku)
    return {"id": order.id, "sku": order.sku, "status": order.status, "amount": order.amount,
            "product": product.name if product else order.sku, "code": delivery.code if delivery else None,
            "created_at": order.created_at, "reservation_expires_at": order.reservation_expires_at}


@app.get("/")
async def home():
    return FileResponse(ROOT / "public" / "index.html")


@app.get("/order.html")
async def order_page():
    return FileResponse(ROOT / "public" / "order.html")


@app.get("/admin.html")
async def admin_page():
    return FileResponse(ROOT / "public" / "admin.html")


@app.get("/admin")
async def admin_route():
    return FileResponse(ROOT / "public" / "admin.html")


@app.get("/api/products")
async def products(q: str = "", kind: str = ""):
    if await release_expired_reservations_now():
        await publish_catalog()
    rows = await catalog_snapshot()
    needle = q.strip().lower()
    return [item for item in rows if (not needle or needle in item["name"].lower()) and (not kind or item["kind"] == kind)]


@app.get("/api/events/catalog")
async def catalog_events() -> StreamingResponse:
    async def stream() -> AsyncIterator[str]:
        queue: asyncio.Queue[str] = asyncio.Queue(maxsize=1)
        catalog_subscribers.add(queue)
        try:
            yield f"event: catalog\ndata: {json.dumps(await catalog_snapshot(), ensure_ascii=False)}\n\n"
            while True:
                try:
                    payload = await asyncio.wait_for(queue.get(), timeout=15)
                    yield f"event: catalog\ndata: {payload}\n\n"
                except asyncio.TimeoutError:
                    yield ": keepalive\n\n"
        finally:
            catalog_subscribers.discard(queue)
    return StreamingResponse(stream(), media_type="text/event-stream", headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"})


@app.post("/api/orders")
async def create_order(payload: OrderInput):
    order_id = payload.order_id or f"ord_{secrets.token_urlsafe(8)}"
    created = False
    async with Session.begin() as db:
        # Serializes only calls with the same client idempotency key. The second
        # retry sees the existing order instead of racing a SELECT/INSERT pair.
        await db.execute(text("SELECT pg_advisory_xact_lock(hashtext(:order_id))"), {"order_id": order_id})
        await release_expired_reservations(db)
        product = await db.scalar(select(Product).where(Product.sku == payload.sku).with_for_update())
        if not product:
            raise HTTPException(404, "Товар не найден")
        existing = await db.get(Order, order_id)
        if existing:
            return await view_order(db, order_id)
        key = await db.scalar(
            select(InventoryKey).where(InventoryKey.sku == product.sku, InventoryKey.state == "available")
            .order_by(InventoryKey.id).with_for_update(skip_locked=True)
        )
        if not key:
            raise HTTPException(409, "Товар только что раскупили. Выберите другой товар или вернитесь к витрине.")
        amount, promo = product.price, None
        if payload.promo_code:
            promo = await db.scalar(select(Promocode).where(Promocode.code == payload.promo_code.upper()).with_for_update())
            if not promo or promo.used_count >= promo.max_uses:
                raise HTTPException(409, "Промокод недоступен")
            promo.used_count += 1
            amount = max(0, product.price - (product.price * promo.value // 100 if promo.discount_type == "percent" else promo.value))
            db.add(PromoUse(order_id=order_id, code=promo.code))
        key.state, key.order_id = "reserved", order_id
        db.add(Order(id=order_id, sku=product.sku, amount=amount, status="reserved", promo_code=promo.code if promo else None,
                     reserved_key_id=key.id, reservation_expires_at=datetime.now(timezone.utc) + timedelta(seconds=RESERVATION_SECONDS)))
        created = True
    await apply_waiting_events(order_id)
    if created:
        await publish_catalog()
    async with Session() as db:
        return await view_order(db, order_id)


@app.post("/api/webhooks/payment", status_code=200)
async def payment_webhook(payload: WebhookInput):
    async with Session.begin() as db:
        event = PaymentEvent(event_id=payload.event_id, order_id=payload.order_id, status=payload.status, amount=payload.amount, currency=payload.currency)
        result = await db.execute(insert(PaymentEvent).values(event_id=event.event_id, order_id=event.order_id, status=event.status, amount=event.amount, currency=event.currency).on_conflict_do_nothing())
        created = result.rowcount == 1
    if created:
        asyncio.create_task(apply_waiting_events(payload.order_id))
    return {"accepted": True, "duplicate": not created}


@app.post("/api/orders/{order_id}/pay")
async def emulate_payment(order_id: str, request: Request):
    data = await request.json() if request.headers.get("content-type", "").startswith("application/json") else {}
    async with Session() as db:
        order = await db.get(Order, order_id)
        if not order:
            raise HTTPException(404, "Заказ не найден")
    status = data.get("status", "paid")
    return await payment_webhook(WebhookInput(event_id=data.get("event_id", f"evt_{secrets.token_urlsafe(8)}"), order_id=order_id, status=status, amount=order.amount))


@app.get("/api/orders/{order_id}")
async def get_order(order_id: str):
    if await release_expired_reservations_now():
        await publish_catalog()
    async with Session() as db:
        return await view_order(db, order_id)


@app.get("/api/admin/recovery")
async def recovery_orders():
    async with Session() as db:
        rows = (await db.scalars(select(Order).where(Order.status.in_(["out_of_stock", "delivery_failed"])).order_by(Order.created_at))).all()
        return [await view_order(db, row.id) for row in rows]


@app.post("/api/admin/orders/{order_id}/retry")
async def retry_order(order_id: str):
    await schedule_delivery(order_id)
    async with Session() as db:
        return await view_order(db, order_id)


@app.post("/api/admin/inventory/{sku}")
async def add_inventory(sku: str, request: Request):
    data = await request.json()
    count = max(1, min(int(data.get("count", 1)), 100))
    async with Session.begin() as db:
        if not await db.get(Product, sku):
            raise HTTPException(404, "SKU не найден")
        for n in range(count):
            db.add(InventoryKey(sku=sku, code=f"{sku[:5]}-RESTOCK-{secrets.token_hex(4).upper()}"))
    await publish_catalog()
    return {"added": count}


@app.put("/api/admin/products/{sku}")
async def update_product(sku: str, payload: ProductUpdateInput):
    async with Session.begin() as db:
        product = await db.scalar(select(Product).where(Product.sku == sku).with_for_update())
        if not product:
            raise HTTPException(404, "SKU не найден")
        product.price = payload.price
    await publish_catalog()
    return {"sku": sku, "price": payload.price}


@app.get("/api/admin/providers")
async def get_provider_modes():
    async with Session() as db:
        rows = (await db.scalars(select(ProviderConfig).order_by(ProviderConfig.provider))).all()
        return [{"provider": row.provider, "mode": row.mode, "error_rate": row.error_rate, "timeout_rate": row.timeout_rate, "delay_ms": row.delay_ms} for row in rows]


@app.put("/api/admin/providers/{provider}")
async def set_provider_mode(provider: Literal["A", "B"], payload: ProviderModeInput):
    async with Session.begin() as db:
        config = await db.get(ProviderConfig, provider, with_for_update=True)
        config.mode = payload.mode
        config.error_rate = payload.error_rate
        config.timeout_rate = payload.timeout_rate
        config.delay_ms = payload.delay_ms
    return {"provider": provider, "mode": payload.mode, "error_rate": payload.error_rate, "timeout_rate": payload.timeout_rate, "delay_ms": payload.delay_ms}


@app.post("/api/providers/{provider}/issue")
async def provider_stub(provider: Literal["A", "B"], request: Request):
    data = await request.json()
    outcome, code, _ = await supplier_issue(provider, data["order_id"], data["sku"], data["request_id"])
    if outcome == "timeout_after_issue":
        raise HTTPException(504, "Supplier response timed out after issuing; retry same request_id")
    if outcome != "ok":
        raise HTTPException(409 if outcome == "out_of_stock" else 503, outcome)
    return {"status": "ok", "request_id": data["request_id"], "code": code}


@app.post("/issue")
async def provider_contract_alias(request: Request):
    """Contract-compatible default supplier endpoint; provider A is the primary stub."""
    return await provider_stub("A", request)
