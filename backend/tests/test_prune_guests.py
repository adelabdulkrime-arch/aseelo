"""Pruning expired guest accounts, and everything it must not touch."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy import select

from app.models import BrandProfile, User, Video, VideoStatus
from app.storage import get_storage
from scripts.prune_guests import prune

from .conftest import register


def _make_guest(db, *, days_old: int, with_video: bool = False) -> User:
    user = User(
        name="Guest",
        email=f"guest-{uuid.uuid4().hex}@guest.aseelo.example",
        password_hash="x",
        is_guest=True,
    )
    db.add(user)
    db.flush()
    db.add(BrandProfile(user_id=user.id, brand_name="My Brand"))

    if with_video:
        db.add(
            Video(
                user_id=user.id,
                text_content="hi",
                input_file_url=f"users/{user.id}/inputs/{uuid.uuid4().hex}.mp4",
                output_file_url=f"users/{user.id}/outputs/{uuid.uuid4().hex}.mp4",
                thumbnail_url=f"users/{user.id}/thumbnails/{uuid.uuid4().hex}.jpg",
                status=VideoStatus.COMPLETED,
            )
        )
    db.commit()

    # created_at has a server default, so age it after the fact.
    user.created_at = datetime.now(UTC) - timedelta(days=days_old)
    db.commit()
    db.refresh(user)
    return user


def test_removes_guests_past_the_cutoff(client, db):
    old = _make_guest(db, days_old=10)

    stats = prune(older_than_days=7)

    assert stats["users"] == 1
    assert db.scalar(select(User).where(User.id == old.id)) is None


def test_keeps_guests_inside_the_window(client, db):
    fresh = _make_guest(db, days_old=2)

    stats = prune(older_than_days=7)

    assert stats["users"] == 0
    assert db.scalar(select(User).where(User.id == fresh.id)) is not None


def test_never_touches_real_accounts_however_old(client, db):
    """The guard that matters: a paying customer is not a guest."""
    account = register(client)
    user = db.scalar(select(User).where(User.email == account["email"]))
    user.created_at = datetime.now(UTC) - timedelta(days=3650)
    db.commit()

    stats = prune(older_than_days=7)

    assert stats["users"] == 0
    assert db.scalar(select(User).where(User.email == account["email"])) is not None


def test_cascades_to_videos_and_brand_profile(client, db):
    guest = _make_guest(db, days_old=30, with_video=True)
    guest_id = guest.id

    stats = prune(older_than_days=7)

    assert stats["videos"] == 1
    assert db.scalars(select(Video).where(Video.user_id == guest_id)).all() == []
    assert db.scalar(select(BrandProfile).where(BrandProfile.user_id == guest_id)) is None


def test_deletes_the_files_not_just_the_rows(client, db, tmp_path):
    """Rows alone would leave orphaned media nobody can attribute or collect."""
    guest = _make_guest(db, days_old=30, with_video=True)
    video = db.scalar(select(Video).where(Video.user_id == guest.id))

    storage = get_storage()
    import io

    for key in (video.input_file_url, video.output_file_url, video.thumbnail_url):
        storage.save_stream(key, io.BytesIO(b"payload"))
        assert storage.exists(key)
    keys = [video.input_file_url, video.output_file_url, video.thumbnail_url]

    stats = prune(older_than_days=7)

    assert stats["files"] == 3
    for key in keys:
        assert not storage.exists(key), f"{key} survived the prune"


def test_dry_run_changes_nothing(client, db):
    guest = _make_guest(db, days_old=30, with_video=True)

    stats = prune(older_than_days=7, dry_run=True)

    assert stats["users"] == 1  # reported...
    assert db.scalar(select(User).where(User.id == guest.id)) is not None  # ...but still there


def test_limit_caps_one_run(client, db):
    for _ in range(3):
        _make_guest(db, days_old=30)

    stats = prune(older_than_days=7, limit=2)

    assert stats["users"] == 2
    assert db.scalar(select(User).where(User.is_guest.is_(True))) is not None


@pytest.mark.parametrize("days", [0, 1])
def test_cutoff_is_inclusive_of_nothing_newer(client, db, days):
    _make_guest(db, days_old=days)
    stats = prune(older_than_days=7)
    assert stats["users"] == 0
