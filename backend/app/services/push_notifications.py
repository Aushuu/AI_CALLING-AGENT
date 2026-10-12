import json
import logging
import os
from base64 import b64encode

from app.database import claim_call_notification, delete_push_subscription, list_push_subscriptions

logger = logging.getLogger(__name__)


def normalize_private_key(private_key: str) -> str:
    if not private_key.lstrip().startswith("-----BEGIN"):
        return private_key
    from cryptography.hazmat.primitives import serialization

    loaded_key = serialization.load_pem_private_key(private_key.encode("utf-8"), password=None)
    der_key = loaded_key.private_bytes(
        encoding=serialization.Encoding.DER,
        format=serialization.PrivateFormat.PKCS8,
        encryption_algorithm=serialization.NoEncryption(),
    )
    return b64encode(der_key).decode("ascii")


def send_call_record_notification(call_sid: str) -> None:
    public_key = os.getenv("VAPID_PUBLIC_KEY", "").strip()
    private_key = os.getenv("VAPID_PRIVATE_KEY", "").strip()
    subject = os.getenv("VAPID_SUBJECT", "").strip()
    if not public_key or not private_key or not subject:
        return

    try:
        from pywebpush import WebPushException, webpush
    except ImportError:
        logger.error("Push notifications are configured but pywebpush is unavailable.")
        return
    try:
        private_key = normalize_private_key(private_key)
    except Exception as error:
        logger.warning("Call notifications have an invalid VAPID private key (%s).", type(error).__name__)
        return

    subscriptions = list_push_subscriptions()
    if not subscriptions or not claim_call_notification(call_sid):
        return

    payload = json.dumps({
        "title": "Call update",
        "body": "A call record is ready in call history.",
        "tag": f"call-record-{call_sid}",
        "url": "/#recent-calls",
    })
    for subscription in subscriptions:
        info = {
            "endpoint": subscription["endpoint"],
            "keys": {
                "p256dh": subscription["p256dh"],
                "auth": subscription["auth"],
            },
        }
        try:
            webpush(
                subscription_info=info,
                data=payload,
                vapid_private_key=private_key,
                vapid_claims={"sub": subject},
                ttl=60,
            )
        except WebPushException as error:
            status_code = error.response.status_code if error.response is not None else None
            if status_code in {404, 410}:
                delete_push_subscription(subscription["endpoint"])
            else:
                logger.warning("Call notification delivery failed (HTTP %s).", status_code)
        except Exception as error:
            logger.warning("Call notification delivery failed (%s).", type(error).__name__)
