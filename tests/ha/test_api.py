"""Tests for the ``XcelOutageApi`` HTTP client.

Uses mocked ``aiohttp.ClientSession`` to verify request headers, timeout,
and response parsing.  All tests are synchronous wrappers around the async
API — ``asyncio.run()`` drives each coroutine.
"""

from __future__ import annotations

import asyncio
import json
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
import aiohttp

from custom_components.xcel_outages.api import (
    XcelOutageApi,
    XcelOutagesConnectionError,
    XcelOutagesSchemaError,
)
from custom_components.xcel_outages.const import ENDPOINT_URL, REQUEST_TIMEOUT, USER_AGENT
from custom_components.xcel_outages.models import ParseOutcome

pytestmark = pytest.mark.hass


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _run(coro):
    """Run an async coroutine synchronously."""
    return asyncio.run(coro)


_SENTINEL = object()  # sentinel to distinguish "not set" from None


def _mock_response(status: int = 200, json_data: object = _SENTINEL) -> AsyncMock:
    """Create a mock ``aiohttp.ClientResponse``.

    When *json_data* is the sentinel (default), ``resp.json`` returns an
    empty list.  Pass ``json_data=None`` explicitly to test null responses.
    """
    resp = AsyncMock(spec=aiohttp.ClientResponse)
    resp.status = status
    resp.__aenter__.return_value = resp
    resp.__aexit__.return_value = None
    if json_data is _SENTINEL:
        resp.json.return_value = []
    else:
        resp.json.return_value = json_data
    return resp


def _make_session(mock_resp: AsyncMock) -> AsyncMock:
    """Create a mock ``aiohttp.ClientSession`` that returns *mock_resp*."""
    session = AsyncMock(spec=aiohttp.ClientSession)
    session.get.return_value = mock_resp
    return session


# =========================================================================
# 1. Static request headers
# =========================================================================


class TestRequestHeaders:
    """Every request must include the expected static headers."""

    def test_accept_header(self):
        """Request includes ``Accept: application/json``."""
        resp = _mock_response(status=200, json_data=[])
        session = _make_session(resp)
        api = XcelOutageApi(session)

        _run(api.fetch_events())

        call_kwargs = session.get.call_args
        assert call_kwargs is not None
        _, kwargs = call_kwargs
        headers = kwargs.get("headers", {})
        assert headers.get("Accept") == "application/json"

    def test_user_agent_header(self):
        """Request includes the configured ``User-Agent``."""
        resp = _mock_response(status=200, json_data=[])
        session = _make_session(resp)
        api = XcelOutageApi(session)

        _run(api.fetch_events())

        call_kwargs = session.get.call_args
        assert call_kwargs is not None
        _, kwargs = call_kwargs
        headers = kwargs.get("headers", {})
        assert headers.get("User-Agent") == USER_AGENT

    def test_endpoint_url(self):
        """Request is made to the configured ``ENDPOINT_URL``."""
        resp = _mock_response(status=200, json_data=[])
        session = _make_session(resp)
        api = XcelOutageApi(session)

        _run(api.fetch_events())

        call_args = session.get.call_args
        assert call_args is not None
        args, _ = call_args
        assert args[0] == ENDPOINT_URL

    def test_all_headers_present(self):
        """Both Accept and User-Agent headers are set simultaneously."""
        resp = _mock_response(status=200, json_data=[])
        session = _make_session(resp)
        api = XcelOutageApi(session)

        _run(api.fetch_events())

        call_kwargs = session.get.call_args
        assert call_kwargs is not None
        _, kwargs = call_kwargs
        headers = kwargs.get("headers", {})
        assert headers.get("Accept") == "application/json"
        assert headers.get("User-Agent") == USER_AGENT


# =========================================================================
# 2. Request timeout
# =========================================================================


class TestRequestTimeout:
    """Each request must use the configured timeout."""

    def test_timeout_is_set(self):
        """Request passes ``ClientTimeout`` with the configured seconds."""
        resp = _mock_response(status=200, json_data=[])
        session = _make_session(resp)
        api = XcelOutageApi(session)

        _run(api.fetch_events())

        call_kwargs = session.get.call_args
        assert call_kwargs is not None
        _, kwargs = call_kwargs
        timeout = kwargs.get("timeout")
        assert timeout is not None
        assert timeout.total == REQUEST_TIMEOUT


# =========================================================================
# 3. Successful response — valid payload
# =========================================================================


class TestSuccessfulResponse:
    """API returns valid JSON list → parse and return ParseOutcome."""

    def test_empty_list_returns_parse_outcome(self):
        """Valid empty list → ``ParseOutcome`` with zero events."""
        resp = _mock_response(status=200, json_data=[])
        session = _make_session(resp)
        api = XcelOutageApi(session)

        outcome = _run(api.fetch_events())
        assert isinstance(outcome, ParseOutcome)
        assert outcome.is_valid_payload is True
        assert len(outcome.events) == 0

    def test_valid_events_returns_parse_outcome(self):
        """Valid event list → ``ParseOutcome`` with parsed events."""
        payload = [
            {
                "identifier": "test001",
                "status": "ACTIVE",
                "numPeople": 50,
                "latitude": 39.75,
                "longitude": -105.0,
                "county": "Jefferson",
                "additionalProperties": {"states": ["CO"]},
            }
        ]
        resp = _mock_response(status=200, json_data=payload)
        session = _make_session(resp)
        api = XcelOutageApi(session)

        outcome = _run(api.fetch_events())
        assert isinstance(outcome, ParseOutcome)
        assert outcome.is_valid_payload is True
        assert len(outcome.events) == 1
        assert outcome.events[0].identifier == "test001"
        assert outcome.raw_count == 1
        assert outcome.malformed_count == 0


# =========================================================================
# 4. HTTP-level errors
# =========================================================================


class TestHttpErrors:
    """Non-200 HTTP responses cause ``XcelOutagesConnectionError``."""

    def test_http_404_raises_connection_error(self):
        """HTTP 404 → ``XcelOutagesConnectionError``."""
        resp = _mock_response(status=404)
        session = _make_session(resp)
        api = XcelOutageApi(session)

        with pytest.raises(XcelOutagesConnectionError, match="HTTP 404"):
            _run(api.fetch_events())

    def test_http_500_raises_connection_error(self):
        """HTTP 500 → ``XcelOutagesConnectionError``."""
        resp = _mock_response(status=500)
        session = _make_session(resp)
        api = XcelOutageApi(session)

        with pytest.raises(XcelOutagesConnectionError, match="HTTP 500"):
            _run(api.fetch_events())

    def test_http_403_raises_connection_error(self):
        """HTTP 403 → ``XcelOutagesConnectionError``."""
        resp = _mock_response(status=403)
        session = _make_session(resp)
        api = XcelOutageApi(session)

        with pytest.raises(XcelOutagesConnectionError):
            _run(api.fetch_events())


# =========================================================================
# 5. Invalid schema responses
# =========================================================================


class TestInvalidSchema:
    """Non-list or unparseable payloads cause ``XcelOutagesSchemaError``."""

    def test_non_list_json_raises_schema_error(self):
        """JSON dict (not a list) → ``XcelOutagesSchemaError``."""
        resp = _mock_response(status=200, json_data={"not": "a list"})
        session = _make_session(resp)
        api = XcelOutageApi(session)

        with pytest.raises(XcelOutagesSchemaError, match="Unexpected API response shape"):
            _run(api.fetch_events())

    def test_json_null_raises_schema_error(self):
        """JSON ``null`` → ``XcelOutagesSchemaError``."""
        resp = _mock_response(status=200, json_data=None)
        session = _make_session(resp)
        api = XcelOutageApi(session)

        with pytest.raises(XcelOutagesSchemaError, match="Unexpected API response shape"):
            _run(api.fetch_events())

    def test_json_string_raises_schema_error(self):
        """JSON string → ``XcelOutagesSchemaError``."""
        resp = _mock_response(status=200, json_data="not a list")
        session = _make_session(resp)
        api = XcelOutageApi(session)

        with pytest.raises(XcelOutagesSchemaError, match="Unexpected API response shape"):
            _run(api.fetch_events())

    def test_all_records_malformed_raises_schema_error(self):
        """List where every record is malformed → ``XcelOutagesSchemaError``."""
        payload = [
            {"identifier": None, "status": "ACTIVE"},
            {"identifier": 42, "latitude": "invalid"},
        ]
        resp = _mock_response(status=200, json_data=payload)
        session = _make_session(resp)
        api = XcelOutageApi(session)

        with pytest.raises(XcelOutagesSchemaError, match="Could not parse any event records"):
            _run(api.fetch_events())


# =========================================================================
# 6. JSON decode errors
# =========================================================================


class TestJsonDecodeErrors:
    """Unparseable response body → ``XcelOutagesSchemaError``."""

    def test_invalid_json_raises_schema_error(self):
        """Non-JSON response body → ``XcelOutagesSchemaError``."""
        resp = _mock_response(status=200)
        resp.json.side_effect = json.JSONDecodeError(
            "Expecting value", "bad-data", 0
        )
        session = _make_session(resp)
        api = XcelOutageApi(session)

        with pytest.raises(XcelOutagesSchemaError, match="Could not decode API response"):
            _run(api.fetch_events())


# =========================================================================
# 7. Network errors (aiohttp.ClientError / TimeoutError)
# =========================================================================


class TestNetworkErrors:
    """Transport-level errors cause ``XcelOutagesConnectionError``."""

    def test_aiohttp_client_error_raises_connection_error(self):
        """``aiohttp.ClientError`` → ``XcelOutagesConnectionError``."""
        mock_session = AsyncMock(spec=aiohttp.ClientSession)
        mock_session.get.side_effect = aiohttp.ClientConnectionError("DNS failure")
        api = XcelOutageApi(mock_session)

        with pytest.raises(XcelOutagesConnectionError, match="Could not reach the outage API"):
            _run(api.fetch_events())

    def test_asyncio_timeout_raises_connection_error(self):
        """``asyncio.TimeoutError`` → ``XcelOutagesConnectionError``."""
        mock_session = AsyncMock(spec=aiohttp.ClientSession)
        mock_session.get.side_effect = asyncio.TimeoutError()

        api = XcelOutageApi(mock_session)

        with pytest.raises(XcelOutagesConnectionError, match="Request timed out"):
            _run(api.fetch_events())
