class AmneziaError(Exception):
    """Base exception for all amnezia-api errors."""


class AmneziaConnectionError(AmneziaError):
    """Network timeout or connection refused."""


class AmneziaClientError(AmneziaError):
    """4xx response from amnezia-api (bad request, conflict, etc.)."""


class AmneziaNotFoundError(AmneziaClientError):
    """404 — client or resource not found."""


class AmneziaServerError(AmneziaError):
    """5xx response — retryable."""
