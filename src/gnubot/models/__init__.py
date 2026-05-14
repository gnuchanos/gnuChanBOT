"""SQLAlchemy ORM models."""

from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy import BigInteger, Boolean, DateTime, ForeignKey, Integer, String, UniqueConstraint
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship


class Base(DeclarativeBase):
    """Declarative base for all ORM models."""


class User(Base):
    """Discord user linked to a Roblox account and point totals."""

    __tablename__ = "users"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    discord_id: Mapped[int] = mapped_column(BigInteger, unique=True, index=True, nullable=False)
    roblox_id: Mapped[int | None] = mapped_column(BigInteger, nullable=True, index=True)
    points: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    active_follows: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    completed_follows: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
    )

    follow_histories: Mapped[list[FollowHistory]] = relationship(
        back_populates="user",
        cascade="all, delete-orphan",
    )
    redemption_requests: Mapped[list["RedemptionRequest"]] = relationship(
        back_populates="user",
        cascade="all, delete-orphan",
    )


class Client(Base):
    """Customer / campaign: Roblox target and follower goal."""

    __tablename__ = "clients"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    roblox_target_id: Mapped[int] = mapped_column(BigInteger, nullable=False, index=True)
    target_followers: Mapped[int] = mapped_column(Integer, nullable=False)
    current_followers: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True, index=True)
    display_name: Mapped[str | None] = mapped_column(String(128), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
    )

    follow_histories: Mapped[list[FollowHistory]] = relationship(
        back_populates="client",
        cascade="all, delete-orphan",
    )


class FollowHistory(Base):
    """
    Per (user, client) follow state and one-time reward tracking.

    * ``rewarded`` — the +points bonus was granted at most once for this pair.
    * ``currently_following`` — last verified Roblox follow state.
    """

    __tablename__ = "follow_history"
    __table_args__ = (UniqueConstraint("user_id", "client_id", name="uq_follow_user_client"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    client_id: Mapped[int] = mapped_column(ForeignKey("clients.id", ondelete="CASCADE"), nullable=False)
    rewarded: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False, index=True)
    currently_following: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    rewarded_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    user: Mapped[User] = relationship(back_populates="follow_histories")
    client: Mapped[Client] = relationship(back_populates="follow_histories")


class RedemptionRequest(Base):
    """
    Kullanıcının kredi bakiyesinden nakde çevrim / ödeme talebi (yönetici onayı).

    Onayda bakiyeden düşülür; gerçek ödeme bot dışında yapılır.
    """

    __tablename__ = "redemption_requests"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    points: Mapped[int] = mapped_column(Integer, nullable=False)
    note: Mapped[str | None] = mapped_column(String(240), nullable=True)
    status: Mapped[str] = mapped_column(String(16), nullable=False, default="pending", index=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
    )
    resolved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    resolver_discord_id: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    admin_note: Mapped[str | None] = mapped_column(String(240), nullable=True)

    user: Mapped[User] = relationship(back_populates="redemption_requests")
