"""Record a paid charge so its customer can activate an account.

Nothing else in this codebase writes to ``payment_charges``: taking payment
happens outside the app, and a provider webhook is deliberately not part of the
MVP. Without this command the setup-account flow has no way to be exercised at
all, which is the only reason it exists.

    docker compose run --rm backend python -m scripts.create_charge \\
        ch_3PabcXYZ customer@example.com

It prints the activation URL to hand to the customer. Re-running with the same
charge reference is refused rather than silently ignored - a duplicate almost
always means a second payment was recorded under the first one's id.
"""

from __future__ import annotations

import argparse
import sys
from urllib.parse import quote

from sqlalchemy import select

from app.config import settings
from app.database import session_scope
from app.logging_config import configure_logging, get_logger
from app.models import PaymentCharge

logger = get_logger(__name__)


def activation_url(email: str, charge_id: str) -> str:
    """The link the customer follows. Empty APP_PUBLIC_URL yields a bare path."""
    base = settings.app_public_url.rstrip("/")
    return f"{base}/setup-account?email={quote(email)}&charge={quote(charge_id)}"


def main() -> int:
    configure_logging()
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("charge_id", help="the payment provider's charge reference")
    parser.add_argument("email", help="the address the customer paid with")
    args = parser.parse_args()

    email = args.email.strip().lower()
    charge_id = args.charge_id.strip()

    with session_scope() as db:
        existing = db.scalar(select(PaymentCharge).where(PaymentCharge.charge_id == charge_id))
        if existing is not None:
            state = "already redeemed" if existing.is_used else "not yet redeemed"
            print(f"Refusing: charge {charge_id} is already recorded ({state}).", file=sys.stderr)
            return 1

        db.add(PaymentCharge(charge_id=charge_id, email=email))

    logger.info("payment_charge_recorded", extra={"charge_id": charge_id})
    print(activation_url(email, charge_id))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
