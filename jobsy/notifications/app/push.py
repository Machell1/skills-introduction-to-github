"""Push notification delivery via Firebase Cloud Messaging.

In production, configure FIREBASE_CREDENTIALS_JSON env var with the
service account JSON. When not configured, notifications are logged
but not delivered (useful for development).
"""

import json
import logging
import os

logger = logging.getLogger(__name__)

_fcm_initialized = False


def _init_fcm():
    """Initialize Firebase Admin SDK if credentials are available."""
    global _fcm_initialized
    if _fcm_initialized:
        return True

    creds_json = os.getenv("FIREBASE_CREDENTIALS_JSON")
    if not creds_json:
        logger.warning("FIREBASE_CREDENTIALS_JSON not set, push notifications disabled")
        return False

    try:
        import firebase_admin
        from firebase_admin import credentials

        cred = credentials.Certificate(json.loads(creds_json))
        firebase_admin.initialize_app(cred)
        _fcm_initialized = True
        logger.info("Firebase Admin SDK initialized")
        return True
    except Exception:
        logger.exception("Failed to initialize Firebase")
        return False


async def send_push_notification(
    device_token: str,
    title: str,
    body: str,
    data: dict | None = None,
    platform: str = "android",
) -> bool:
    """Send a push notification to a single device.

    Returns True if sent successfully, False otherwise.
    """
    if not _init_fcm():
        logger.info("Push (dry-run): [%s] %s - %s", device_token[:20], title, body)
        return False

    try:
        from firebase_admin import messaging

        message = messaging.Message(
            notification=messaging.Notification(title=title, body=body),
            data=data or {},
            token=device_token,
        )

        if platform == "ios":
            message.apns = messaging.APNSConfig(
                payload=messaging.APNSPayload(
                    aps=messaging.Aps(badge=1, sound="default"),
                ),
            )

        response = messaging.send(message)
        logger.info("Push sent: %s", response)
        return True
    except Exception:
        logger.exception("Failed to send push to %s", device_token[:20])
        return False


async def send_push_to_user(
    user_tokens: list[tuple[str, str]],  # [(token, platform), ...]
    title: str,
    body: str,
    data: dict | None = None,
) -> int:
    """Send a push notification to all of a user's registered devices.

    Returns the number of successful deliveries.
    """
    sent = 0
    for token, platform in user_tokens:
        if await send_push_notification(token, title, body, data, platform):
            sent += 1
    return sent
