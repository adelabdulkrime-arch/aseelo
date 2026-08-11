"""Outgoing mail.

Two backends, chosen by ``MAIL_BACKEND``:

``console``
    Logs the message instead of sending it. The default, so development and the
    test suite never need credentials.
``smtp``
    Plain :mod:`smtplib`. Every provider worth using (SES, Resend, Postmark,
    Mailgun, Zoho, Gmail) speaks SMTP, so there is no vendor SDK here and
    switching provider is a change of environment variables, not of code.
"""

from __future__ import annotations

import smtplib
from email.message import EmailMessage

from app.config import settings
from app.logging_config import get_logger

logger = get_logger(__name__)


class MailError(Exception):
    """Raised when a message could not be handed to the transport."""


def _send_smtp(message: EmailMessage) -> None:
    try:
        if settings.smtp_ssl:
            client: smtplib.SMTP = smtplib.SMTP_SSL(
                settings.smtp_host, settings.smtp_port, timeout=settings.smtp_timeout_seconds
            )
        else:
            client = smtplib.SMTP(
                settings.smtp_host, settings.smtp_port, timeout=settings.smtp_timeout_seconds
            )
        with client:
            if settings.smtp_starttls and not settings.smtp_ssl:
                client.starttls()
            if settings.smtp_username:
                client.login(settings.smtp_username, settings.smtp_password)
            client.send_message(message)
    except (OSError, smtplib.SMTPException) as exc:
        raise MailError(str(exc)) from exc


def send_mail(*, to: str, subject: str, text_body: str, html_body: str | None = None) -> None:
    """Deliver one message, or raise :class:`MailError`."""
    message = EmailMessage()
    message["From"] = settings.mail_from
    message["To"] = to
    message["Subject"] = subject
    message.set_content(text_body)
    if html_body:
        message.add_alternative(html_body, subtype="html")

    if settings.mail_backend == "smtp":
        _send_smtp(message)
        logger.info("mail_sent", extra={"to": to, "backend": "smtp"})
        return

    # Console backend. The body carries a live credential, so it is only safe to
    # write into the log outside production.
    if settings.is_production:
        logger.warning(
            "mail_not_sent_console_backend",
            extra={"to": to, "subject": subject},
        )
        return
    logger.info("mail_console", extra={"to": to, "subject": subject, "body": text_body})


# ---------------------------------------------------------------------------
# Password reset
# ---------------------------------------------------------------------------
_RESET_SUBJECT = "إعادة تعيين كلمة المرور | Reset your ASEELO password"


def _reset_bodies(name: str, link: str, ttl_minutes: int) -> tuple[str, str]:
    text = (
        f"مرحباً {name}،\n\n"
        "وصلنا طلب لإعادة تعيين كلمة مرور حسابك في أصيلو.\n"
        f"افتح الرابط التالي خلال {ttl_minutes} دقيقة:\n\n"
        f"{link}\n\n"
        "إن لم تطلب ذلك، تجاهل هذه الرسالة — كلمة مرورك لن تتغير.\n\n"
        "---\n\n"
        f"Hi {name},\n\n"
        "We received a request to reset your ASEELO password.\n"
        f"Open the link below within {ttl_minutes} minutes:\n\n"
        f"{link}\n\n"
        "If you did not request this, ignore this email — your password stays unchanged.\n"
    )
    html = (
        '<div dir="rtl" style="font-family:system-ui,sans-serif;line-height:1.7">'
        f"<p>مرحباً {name}،</p>"
        "<p>وصلنا طلب لإعادة تعيين كلمة مرور حسابك في أصيلو.</p>"
        f'<p><a href="{link}">إعادة تعيين كلمة المرور</a></p>'
        f"<p>الرابط صالح لمدة {ttl_minutes} دقيقة. إن لم تطلب ذلك، تجاهل هذه الرسالة.</p>"
        "</div><hr>"
        '<div dir="ltr" style="font-family:system-ui,sans-serif;line-height:1.7">'
        f"<p>Hi {name},</p>"
        "<p>We received a request to reset your ASEELO password.</p>"
        f'<p><a href="{link}">Reset your password</a></p>'
        f"<p>This link is valid for {ttl_minutes} minutes. If you did not request it, ignore "
        "this email.</p>"
        "</div>"
    )
    return text, html


def send_password_reset(*, to: str, name: str, token: str) -> None:
    """Mail a reset link, or raise :class:`MailError`.

    Returns without sending when ``APP_PUBLIC_URL`` is unset: there would be no
    valid link to put in the message. The caller still reports success to the
    user, because telling them otherwise would reveal whether the address is
    registered.
    """
    if not settings.app_public_url:
        logger.warning("password_reset_not_sent_no_app_url", extra={"to": to})
        return

    link = f"{settings.app_public_url.rstrip('/')}/reset-password?token={token}"
    text, html = _reset_bodies(name, link, settings.password_reset_token_ttl_minutes)
    send_mail(to=to, subject=_RESET_SUBJECT, text_body=text, html_body=html)
