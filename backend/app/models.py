from sqlalchemy import (
    Column,
    Integer,
    String,
    Boolean,
    ForeignKey,
    UniqueConstraint,
    Float,
)
from sqlalchemy.orm import relationship
from .db import Base


class User(Base):
    __tablename__ = "users"

    id = Column(Integer, primary_key=True, index=True)

    username = Column(String, unique=True, index=True, nullable=False)
    password_hash = Column(String, nullable=False)

    # Admin flag
    is_admin = Column(Boolean, default=False, nullable=False)

    # Letterboxd integration
    letterboxd_username = Column(String, nullable=True)
    letterboxd_avatar_url = Column(String, nullable=True)
    letterboxd_synced_at = Column(Integer, nullable=True)  # unix timestamp

    # Profile avatar (user-set, takes priority over letterboxd)
    avatar_url = Column(String, nullable=True)

    # Participation restriction (the user can still browse, chat and react)
    is_banned = Column(Boolean, default=False, nullable=False)
    ban_reason = Column(String, nullable=True)
    banned_at = Column(Integer, nullable=True)

    # sessions (login tokens)
    sessions = relationship(
        "Session",
        back_populates="user",
        cascade="all, delete-orphan",
        passive_deletes=True,
    )

    letterboxd_entries = relationship(
        "LetterboxdEntry",
        back_populates="user",
        cascade="all, delete-orphan",
        passive_deletes=True,
    )

    ban_requirements = relationship(
        "BanRequirement",
        back_populates="user",
        cascade="all, delete-orphan",
        passive_deletes=True,
    )


class Session(Base):
    __tablename__ = "sessions"

    id = Column(Integer, primary_key=True, index=True)

    user_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    token = Column(String, unique=True, index=True, nullable=False)

    created_at = Column(Integer, nullable=False)   # unix seconds
    expires_at = Column(Integer, nullable=False)   # unix seconds

    user = relationship("User", back_populates="sessions")


class Week(Base):
    __tablename__ = "weeks"

    id = Column(Integer, primary_key=True, index=True)
    title = Column(String, nullable=False)

    is_open = Column(Boolean, default=True, nullable=False)
    is_ready = Column(Boolean, default=False, nullable=False)

    # winner points to a film in films table (creates FK cycle with Film.week_id)
    winner_film_id = Column(Integer, ForeignKey("films.id"), nullable=True)

    is_special = Column(Boolean, default=False, nullable=False)
    theme = Column(String, nullable=True, default=None)

    films = relationship(
        "Film",
        back_populates="week",
        cascade="all, delete-orphan",
        foreign_keys="Film.week_id",
        passive_deletes=True,
    )

    # resolve cycle updates (SQLAlchemy will do extra UPDATE)
    winner = relationship(
        "Film",
        foreign_keys=[winner_film_id],
        post_update=True,
    )


class Film(Base):
    __tablename__ = "films"

    id = Column(Integer, primary_key=True, index=True)

    week_id = Column(Integer, ForeignKey("weeks.id", ondelete="CASCADE"), nullable=False)

    # Canonical fields (what the public sees)
    title = Column(String, nullable=False)
    year = Column(Integer, nullable=True)
    director = Column(String, nullable=True)
    poster_url = Column(String, nullable=True)

    # Who submitted it (used for voting rules)
    submitter_key = Column(String, nullable=False)

    # Raw submission (what user typed)
    submitted_title = Column(String, nullable=True)
    submitted_year = Column(Integer, nullable=True)

    # Matching metadata (TMDB / scoring)
    tmdb_id = Column(Integer, nullable=True)
    match_score = Column(Float, nullable=True)
    needs_review = Column(Boolean, default=False, nullable=False)

    week = relationship("Week", back_populates="films", foreign_keys=[week_id])

    votes = relationship(
        "Vote",
        back_populates="film",
        cascade="all, delete-orphan",
        passive_deletes=True,
    )


class Vote(Base):
    __tablename__ = "votes"

    id = Column(Integer, primary_key=True, index=True)

    week_id = Column(Integer, ForeignKey("weeks.id", ondelete="CASCADE"), nullable=False)
    film_id = Column(Integer, ForeignKey("films.id", ondelete="CASCADE"), nullable=False)

    voter_key = Column(String, nullable=False)

    film = relationship("Film", back_populates="votes")

    __table_args__ = (
        UniqueConstraint("week_id", "voter_key", name="unique_vote_per_week_per_voter"),
    )

class LetterboxdEntry(Base):
    """Cached diary entries fetched from a user's Letterboxd RSS feed."""
    __tablename__ = "letterboxd_entries"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)

    # Film identity — we match on tmdb_id when possible, otherwise title+year
    tmdb_id = Column(Integer, nullable=True, index=True)
    film_title = Column(String, nullable=False)
    film_year = Column(Integer, nullable=True)

    # Letterboxd data
    rating = Column(Float, nullable=True)          # 0.5 – 5.0 (half-stars)
    watched_date = Column(Integer, nullable=True)  # unix timestamp
    letterboxd_url = Column(String, nullable=True)
    is_rewatch = Column(Boolean, default=False, nullable=False)

    user = relationship("User", back_populates="letterboxd_entries")

    __table_args__ = (
        # one entry per user per tmdb film (most recent watch wins on upsert)
        UniqueConstraint("user_id", "tmdb_id", name="uq_lb_entry_user_tmdb"),
    )


class Reaction(Base):
    """Emoji reaction from a user on a film."""
    __tablename__ = "reactions"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    film_id = Column(Integer, ForeignKey("films.id", ondelete="CASCADE"), nullable=False, index=True)
    emoji = Column(String, nullable=False)  # one of the allowed emojis

    user = relationship("User")
    film = relationship("Film")

    __table_args__ = (
        UniqueConstraint("user_id", "film_id", name="uq_reaction_user_film"),
    )


class ChatMessage(Base):
    """Chat message for a week's discussion."""
    __tablename__ = "chat_messages"

    id = Column(Integer, primary_key=True, index=True)
    week_id = Column(Integer, ForeignKey("weeks.id", ondelete="CASCADE"), nullable=False, index=True)
    user_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    content = Column(String, nullable=False)
    created_at = Column(Integer, nullable=False)  # unix timestamp

    user = relationship("User")
    week = relationship("Week")


class BanRequirement(Base):
    """A film a banned user must log on Letterboxd before self-unbanning."""
    __tablename__ = "ban_requirements"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    title = Column(String, nullable=False)
    year = Column(Integer, nullable=True)
    tmdb_id = Column(Integer, nullable=True, index=True)
    poster_url = Column(String, nullable=True)

    user = relationship("User", back_populates="ban_requirements")
