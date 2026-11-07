from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class SendResult:
    """What a provider said after accepting a text."""

    provider_id: str = ""
    status: str = "sent"  # "sent" or "delivered"


class SMSError(Exception):
    """A text could not be sent.

    ``retryable`` means trying again later may work (timeouts, rate limits,
    provider outages). ``opted_out`` and ``invalid_number`` let Docketbell update
    the person's record so it stops trying.
    """

    def __init__(
        self,
        message: str,
        *,
        retryable: bool = False,
        code: str = "",
        opted_out: bool = False,
        invalid_number: bool = False,
    ) -> None:
        super().__init__(message)
        self.retryable = retryable
        self.code = code
        self.opted_out = opted_out
        self.invalid_number = invalid_number


class BaseBackend:
    """Interface every SMS backend implements.

    Subclasses set ``name`` and implement :meth:`send`. If the provider can
    report delivery, set ``status_callback_url_name`` to the URL name of the
    webhook that receives those reports.
    """

    name = "base"
    status_callback_url_name: str | None = None

    def __init__(self, **options) -> None:
        self.options = options

    def send(self, to: str, body: str, *, callback_url: str | None = None) -> SendResult:
        raise NotImplementedError

    def close(self) -> None:
        """Release connections. Called when a batch of sends is done."""

    def __enter__(self):
        return self

    def __exit__(self, *exc) -> None:
        self.close()
