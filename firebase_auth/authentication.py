import logging
import os

import firebase_admin
from firebase_admin import auth
from firebase_admin import credentials
from rest_framework import authentication

from api.models import User
from .exceptions import FirebaseError
from .exceptions import InvalidAuthToken
from .exceptions import NoAuthToken

logger = logging.getLogger(__name__)
cred = credentials.Certificate(
    {
        "type": "service_account",
        "project_id": "channels-efc02",
        "private_key_id": "447e4241b743db0b38a8e2f6950f12946cecf65e",
        "private_key": "-----BEGIN PRIVATE KEY-----\nMIIEvQIBADANBgkqhkiG9w0BAQEFAASCBKcwggSjAgEAAoIBAQD3N+dKjvl/BMAX\nZ3kvF2F1qanOf2cwzdinlmeF1RhuhuRjpL2yfkc9lbEzz5FCKDHw02RV1c2aoq0h\nilC2UkTmi8kByhtzWDS1PhKObXrYtD5EqoKJAdPPW8o8SlC/m/JyC2o6IixRf8tX\nT11tuO4YXjoHELBZq6BYv6CMXFc6PX5vk27SVLQSzSOa7wdAd6+EcbVPF748wXQO\nHtXqFduqfOT+4DmJ0n/OJX2bPkRjp6k2BG3MZixvGg9J6lo8YTWJVAftk4KoQQw+\n7XiemYvqAiRpjaxtWcLkgCkBhUgscl2XcnPjOloOhz2xqaOLE/74HTeWG9WxdeAL\n8fQ+SR39AgMBAAECggEALFr44h018Y66Iljb2tGgmFpZD6Y3Lv/329W1/EKoEAie\nyKwBpxlWEdweP5QB1XNdxn4/FdF3AsQmOQrWgWfQWecBqRMIitDsIAqjjK9i56er\nNmm7YvaTeLRY3ClfRImn3cNji0ufVP4PTzp7oliYS4H4elUJtwT+j33OQfC9a8LL\neFWqsonmKfBoP4gh71xee3zuc7ZMzoGKJDPwSVLyrNjgstW6W8pSPmH6zfuIX47M\n/CCHWjO/SVR4QWzD94S/hdRZ2TXiImR3fjH979f8XxcOoj5DjenOXfhT6GSpkvNW\nnzVoMf61Xr4UvwvvdNS3wup1lQK3UrC6s2VZoxWqgQKBgQD/aPRSUiV/JzLGbqTY\nXiHEtol9bz9KIshJBli+GYbWj0T/DMrunyPtpyA0KXWM3/RdKHBOzoizKAIV8l6t\n6CFbCqPObBg3taN3TlP6LNu4PK7oWO+8xT/zIZrpzQdi4Bx9TtuL6U6mVzrrQ0T1\nW3YngAphJqh1HAUdfAKt8t31wQKBgQD3yhrOKZYSlE8FCFCjnLFh8664mF0/j2l7\n5TAkZJPwuMcF4TkGvSoquPjJNhRMuS2hT86h4z9QpoMyWlfAIo0kMI2jAlH5Tz15\nXNvOlrYPhnQl8w2xj32/WblefyqcDnOwyby/QTw82ELfmEGCLha50Di1jNi6J1dH\nYykWik9PPQKBgBabiqzSuqDzrknkN1Ezm9eWtLrWowqD46ibGDXTepz5V4kf78KJ\ncZuypGYZmV8b37xzPOWs4GrDStP4fSr1liZB3dgCt24O9OY1l7dYSyaWsIC+hpH1\n/8AcpGK3lETLQ5pP5Z0PzLdqlzuF28/ABchfTAvnaRfcoBNJC8+r5LvBAoGAK7YK\nXn31jFd/TQr3drVIkVf0ZXnzUSgSWpnGkVTwyBFAgqgFcEvkaV7x/ES+9f3gr8kt\nUV+OJsMI99P6ENnHfi/WfIAHR+yTkpov6FSrzzdPu/YRX1ZJv3yrd6EFOjxOakxc\nMHzojG819M2eGMHannK93kD3ZndULTKv59sEPJ0CgYEArI1+jFrYxQCkqrklyiXw\nqkjKODKjSb55n4KN4Muans5PADWQ5nTinIBJLtcABc/KyegPq5aAiTR/y1i2weMY\nTxCanIdFJ3aiGHbN5xi5SjvdZkXHA4VsNqblf+XlQeWQAMrccd5aedB9oImjVCti\nGfzUCO4P31gcbWL0JGFqCGk=\n-----END PRIVATE KEY-----\n",
        "client_email": "firebase-adminsdk-kyx2a@channels-efc02.iam.gserviceaccount.com",
        "client_id": "115075702519804890057",
        "auth_uri": "https://accounts.google.com/o/oauth2/auth",
        "token_uri": "https://oauth2.googleapis.com/token",
        "auth_provider_x509_cert_url": "https://www.googleapis.com/oauth2/v1/certs",
        "client_x509_cert_url": "https://www.googleapis.com/robot/v1/metadata/x509/firebase-adminsdk-kyx2a%40channels-efc02.iam.gserviceaccount.com",
    }
)

default_app = firebase_admin.initialize_app(cred)


class FirebaseAuthentication(authentication.BaseAuthentication):
    def authenticate(self, request):
        auth_header = request.META.get("HTTP_AUTHORIZATION")
        if not auth_header:
            raise NoAuthToken("No auth token provided")

        id_token = auth_header.split(" ").pop()
        try:
            decoded_token = auth.verify_id_token(id_token)
        except Exception:
            raise InvalidAuthToken("Invalid auth token")
            pass

        if not id_token or not decoded_token:
            return None

        try:
            uid = decoded_token.get("uid")
            logger.debug(f"{decoded_token}")
        except Exception:
            raise FirebaseError()

        user, created = User.objects.get_or_create(
            username=uid,
            first_name=decoded_token.get("name"),
            email=decoded_token.get("email"),
        )

        return (user, None)
