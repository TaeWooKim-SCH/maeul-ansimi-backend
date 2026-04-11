import logging

from rest_framework import status
from rest_framework.exceptions import APIException
from rest_framework.views import exception_handler

logger = logging.getLogger(__name__)


class ServiceUnavailableError(APIException):
    status_code = status.HTTP_503_SERVICE_UNAVAILABLE
    default_detail = "외부 서비스에 일시적으로 접근할 수 없습니다."
    default_code = "service_unavailable"


def custom_exception_handler(exc: Exception, context: dict) -> object:
    response = exception_handler(exc, context)

    if response is not None:
        response.data["status_code"] = response.status_code
    else:
        logger.exception("Unhandled exception: %s", exc)

    return response
