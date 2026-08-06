"""Delete expired guest accounts and everything they left on disk.

`POST /api/auth/guest` mints a row per visitor, so `users` grows without limit
while guest sessions are enabled. This reclaims both the rows and the media.

    docker compose run --rm backend python -m scripts.prune_guests --dry-run
    docker compose run --rm backend python -m scripts.prune_guests

Files are deleted BEFORE the database rows, deliberately. The rows are the only
record of which storage keys belong to whom: dropping them first and failing
half way through leaves media nobody can attribute and nobody will ever collect.
Doing it in this order, a crash leaves an account whose files are already gone -
ugly, but the next run finishes the job.

Only accounts with `is_guest` are ever considered. Real customers are never
touched no matter how old or idle.
"""

from __future__ import annotations

import argparse
from datetime import UTC, datetime, timedelta

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.config import settings
from app.database import session_scope
from app.logging_config import configure_logging, get_logger
from app.models import User, Video
from app.storage import Storage, get_storage

logger = get_logger(__name__)


def _delete_media(storage: Storage, user: User, db: Session, *, dry_run: bool) -> int:
    """Remove every stored object this user produced. Returns the count."""
    keys: list[str] = []
    for video in db.scalars(select(Video).where(Video.user_id == user.id)):
        keys.extend(
            k for k in (video.input_file_url, video.output_file_url, video.thumbnail_url) if k
        )
    if user.brand_profile is not None and user.brand_profile.logo_url:
        keys.append(user.brand_profile.logo_url)

    removed = 0
    for key in keys:
        if dry_run:
            removed += 1
            continue
        try:
            storage.delete(key)
            removed += 1
        except Exception:  # noqa: BLE001 - one bad key must not strand the rest
            logger.warning("guest_asset_delete_failed", extra={"key": key})
    return removed


def prune(older_than_days: int, *, dry_run: bool = False, limit: int | None = None) -> dict:
    cutoff = datetime.now(UTC) - timedelta(days=older_than_days)
    storage = get_storage()
    stats = {"users": 0, "videos": 0, "files": 0}

    with session_scope() as db:
        query = (
            select(User)
            .where(User.is_guest.is_(True), User.created_at < cutoff)
            .order_by(User.created_at)
        )
        if limit is not None:
            query = query.limit(limit)

        for user in db.scalars(query):
            videos = list(db.scalars(select(Video).where(Video.user_id == user.id)))

            stats["files"] += _delete_media(storage, user, db, dry_run=dry_run)
            stats["videos"] += len(videos)
            stats["users"] += 1

            if not dry_run:
                # Videos, rendering jobs, the brand profile and any reset tokens
                # all cascade from this one delete (ondelete=CASCADE on every
                # child FK), so there is nothing else to clean up by hand.
                db.delete(user)

        if dry_run:
            db.rollback()

    return stats


def main() -> int:
    configure_logging()
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument(
        "--days",
        type=int,
        default=settings.guest_retention_days,
        help="delete guests created more than this many days ago",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="report what would be removed, change nothing",
    )
    parser.add_argument(
        "--limit",
        type=int,
        default=None,
        help="cap how many accounts are processed in one run",
    )
    args = parser.parse_args()

    stats = prune(args.days, dry_run=args.dry_run, limit=args.limit)
    mode = "would delete" if args.dry_run else "deleted"
    logger.info("guest_prune_complete", extra={"dry_run": args.dry_run, **stats})
    print(
        f"{mode}: {stats['users']} guest accounts, "
        f"{stats['videos']} videos, {stats['files']} stored files "
        f"(older than {args.days} days)"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
