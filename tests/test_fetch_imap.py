# type: ignore
"""
This file is part of mettmail (https://github.com/spezifisch/mettmail).
Copyright (c) 2022 spezifisch (https://github.com/spezifisch)

This program is free software: you can redistribute it and/or modify
it under the terms of the GNU Affero General Public License as
published by the Free Software Foundation, version 3 of the License.

This program is distributed in the hope that it will be useful,
but WITHOUT ANY WARRANTY; without even the implied warranty of
MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
GNU Affero General Public License for more details.

You should have received a copy of the GNU Affero General Public License
along with this program.  If not, see <https://www.gnu.org/licenses/>.
"""

import asyncio
import unittest
from unittest.mock import AsyncMock, PropertyMock, patch

import aioimaplib
from aioimaplib import Response

from mettmail.deliver_base import DeliverBase
from mettmail.exceptions import (
    MettmailFetchAuthenticationError,
    MettmailFetchCommandFailed,
    MettmailFetchFeatureUnsupported,
    MettmailFetchStateError,
    MettmailFetchTimeoutError,
)
from mettmail.fetch_imap import FetchIMAP


class DeliverMock(DeliverBase):
    def __init__(self, return_deliver_message=False) -> None:
        self.return_deliver_message = return_deliver_message

    def connect(self) -> None:
        return

    def disconnect(self) -> None:
        return

    def deliver_message(self, message: bytearray) -> bool:
        return self.return_deliver_message


class TestFetchIMAP(unittest.IsolatedAsyncioTestCase):
    TEST_HOST = "example.com"
    TEST_PORT = 123
    TEST_USER = "foo"
    TEST_PASSWORD = "secret"
    TEST_MAILBOX = "foobar"

    # responses from Dovecot v2.3.13
    DOVECOT_SELECT_LINES = [
        b"FLAGS (\\Answered \\Flagged \\Deleted \\Seen \\Draft)",
        b"OK [PERMANENTFLAGS (\\Answered \\Flagged \\Deleted \\Seen \\Draft \\*)] Flags permitted.",
        b"1 EXISTS",
        b"1 RECENT",
        b"OK [UNSEEN 1] First unseen.",
        b"OK [UIDVALIDITY 1641470680] UIDs valid",
        b"OK [UIDNEXT 2] Predicted next UID",
        b"[READ-WRITE] Select completed (0.002 + 0.000 + 0.001 secs).",
    ]

    def setUp(self) -> None:
        self.mock_aioimaplib = patch("aioimaplib.IMAP4_SSL", autospec=True).start()
        self.addCleanup(patch.stopall)
        mock_object = self.mock_aioimaplib.return_value

        # return values for method calls
        mock_object.wait_hello_from_server.return_value = None
        mock_object.has_capability.return_value = True  # yes, we have IDLE
        mock_object.login.return_value = Response("OK", [])
        mock_object.select.return_value = Response(result="OK", lines=self.DOVECOT_SELECT_LINES)
        mock_object.logout.return_value = Response("OK", [])
        mock_object.protocol = PropertyMock(return_value=[])

        self.response_no = Response("NO", [])
        self.deliver_mock = DeliverMock(return_deliver_message=True)

    async def test_success(self) -> None:
        mock_object = self.mock_aioimaplib.return_value

        imap = FetchIMAP(
            host=self.TEST_HOST,
            port=self.TEST_PORT,
            user=self.TEST_USER,
            password=self.TEST_PASSWORD,
            mailbox=self.TEST_MAILBOX,
            deliverer=self.deliver_mock,
        )
        assert imap.host == self.TEST_HOST
        assert imap.port == self.TEST_PORT
        assert imap.account["user"] == self.TEST_USER
        assert imap.account["password"] == self.TEST_PASSWORD
        assert imap.account["mailbox"] == self.TEST_MAILBOX
        assert imap.deliverer == self.deliver_mock

        await imap.connect()
        self.mock_aioimaplib.assert_called_once_with(host=self.TEST_HOST, port=self.TEST_PORT, timeout=30)

        mock_object.wait_hello_from_server.assert_called_once()
        name, args, kwargs = self.mock_aioimaplib.method_calls.pop(0)
        assert name == "().wait_hello_from_server"

        mock_object.login.assert_called_once_with(self.TEST_USER, self.TEST_PASSWORD)
        name, args, kwargs = self.mock_aioimaplib.method_calls.pop(0)
        assert name == "().login"

        mock_object.select.assert_called_once_with(self.TEST_MAILBOX)
        name, args, kwargs = self.mock_aioimaplib.method_calls.pop(0)
        assert name == "().select"

        mock_object.has_capability.assert_called_once_with("IDLE")
        name, args, kwargs = self.mock_aioimaplib.method_calls.pop(0)
        assert name == "().has_capability"

        # disconnect
        assert imap.client is not None
        await imap.disconnect()
        mock_object.logout.assert_called_once()
        name, args, kwargs = self.mock_aioimaplib.method_calls.pop(0)
        assert name == "().logout"
        assert imap.client is None

    async def test_connect_timeout_hello(self) -> None:
        mock_object = self.mock_aioimaplib.return_value
        mock_object.wait_hello_from_server.side_effect = asyncio.TimeoutError()
        imap = FetchIMAP(
            host=self.TEST_HOST,
            deliverer=self.deliver_mock,
        )

        with self.assertRaises(MettmailFetchTimeoutError) as ctx:
            await imap.connect()
        assert "hello timeout" in str(ctx.exception)

    async def test_connect_timeout_login(self) -> None:
        mock_object = self.mock_aioimaplib.return_value
        mock_object.login.side_effect = asyncio.TimeoutError()
        imap = FetchIMAP(
            host=self.TEST_HOST,
            deliverer=self.deliver_mock,
        )

        with self.assertRaises(MettmailFetchTimeoutError) as ctx:
            await imap.connect()
        assert "login timeout" in str(ctx.exception)

    async def test_connect_failed_login(self) -> None:
        mock_object = self.mock_aioimaplib.return_value
        mock_object.login.return_value = self.response_no
        imap = FetchIMAP(
            host=self.TEST_HOST,
            deliverer=self.deliver_mock,
        )

        with self.assertRaises(MettmailFetchAuthenticationError) as ctx:
            await imap.connect()
        assert "login error" in str(ctx.exception)

    async def test_connect_timeout_select(self) -> None:
        mock_object = self.mock_aioimaplib.return_value
        mock_object.select.side_effect = asyncio.TimeoutError()
        imap = FetchIMAP(
            host=self.TEST_HOST,
            deliverer=self.deliver_mock,
        )

        with self.assertRaises(MettmailFetchTimeoutError) as ctx:
            await imap.connect()
        assert "select timeout" in str(ctx.exception)

    async def test_connect_failed_select(self) -> None:
        mock_object = self.mock_aioimaplib.return_value
        mock_object.select.return_value = self.response_no
        imap = FetchIMAP(
            host=self.TEST_HOST,
            deliverer=self.deliver_mock,
        )

        with self.assertRaises(MettmailFetchCommandFailed) as ctx:
            await imap.connect()
        assert "select error" in str(ctx.exception)

    async def test_connect_missing_pflags(self) -> None:
        mock_object = self.mock_aioimaplib.return_value
        lines = [
            self.DOVECOT_SELECT_LINES[0],
        ] + self.DOVECOT_SELECT_LINES[2:]
        mock_object.select.return_value = Response(result="OK", lines=lines)
        imap = FetchIMAP(
            host=self.TEST_HOST,
            deliverer=self.deliver_mock,
        )

        with self.assertRaises(MettmailFetchFeatureUnsupported) as ctx:
            await imap.connect()
        assert "custom FLAGS" in str(ctx.exception)

    async def test_connect_no_wildcard_pflag(self) -> None:
        mock_object = self.mock_aioimaplib.return_value
        line = b"OK [PERMANENTFLAGS (\\Answered \\Flagged \\Deleted \\Seen \\Draft)] Flags permitted."
        lines = [self.DOVECOT_SELECT_LINES[0], line] + self.DOVECOT_SELECT_LINES[2:]
        mock_object.select.return_value = Response(result="OK", lines=lines)
        imap = FetchIMAP(
            host=self.TEST_HOST,
            deliverer=self.deliver_mock,
        )

        with self.assertRaises(MettmailFetchFeatureUnsupported) as ctx:
            await imap.connect()
        assert "custom FLAGS" in str(ctx.exception)

    async def test_connect_no_idle(self) -> None:
        mock_object = self.mock_aioimaplib.return_value
        mock_object.has_capability.return_value = False  # no, we don't have IDLE
        imap = FetchIMAP(
            host=self.TEST_HOST,
            deliverer=self.deliver_mock,
        )

        await imap.connect()
        mock_object.has_capability.assert_called_once_with("IDLE")

    async def test_disconnect_timeout(self) -> None:
        mock_object = self.mock_aioimaplib.return_value
        mock_object.logout.side_effect = asyncio.TimeoutError()
        imap = FetchIMAP(
            host=self.TEST_HOST,
            deliverer=self.deliver_mock,
        )

        await imap.connect()
        await imap.disconnect()
        assert imap.client is None

    async def test_disconnect_abort(self) -> None:
        mock_object = self.mock_aioimaplib.return_value
        mock_object.logout.side_effect = aioimaplib.aioimaplib.Abort("test")
        imap = FetchIMAP(
            host=self.TEST_HOST,
            deliverer=self.deliver_mock,
        )

        await imap.connect()
        await imap.disconnect()
        assert imap.client is None

    async def test_disconnect_fail_logout(self) -> None:
        mock_object = self.mock_aioimaplib.return_value
        mock_object.logout.return_value = self.response_no
        imap = FetchIMAP(
            host=self.TEST_HOST,
            deliverer=self.deliver_mock,
        )

        await imap.connect()
        await imap.disconnect()
        assert imap.client is None

    async def test_disconnect_logout_double(self) -> None:
        imap = FetchIMAP(
            host=self.TEST_HOST,
            deliverer=self.deliver_mock,
        )

        await imap.disconnect()
        await imap.disconnect()

    async def test_state_errors(self) -> None:
        imap = FetchIMAP(
            host=self.TEST_HOST,
            deliverer=self.deliver_mock,
        )

        # not connected
        assert imap.client is None

        with self.assertRaises(MettmailFetchStateError):
            await imap.run_idle_loop()

        with self.assertRaises(MettmailFetchStateError):
            await imap.idle_loop_step()

        with self.assertRaises(MettmailFetchStateError):
            await imap.fetch_deliver_unflagged_messages()

        with self.assertRaises(MettmailFetchStateError):
            await imap.fetch_deliver_message(123)

        with self.assertRaises(MettmailFetchStateError):
            await imap.set_fetched_flag(123)

        assert imap.client is None

    async def test_loop_runner(self) -> None:
        imap = FetchIMAP(
            host=self.TEST_HOST,
            deliverer=self.deliver_mock,
        )

        # stub out loop function
        imap.idle_loop_step = AsyncMock(return_value=False)

        await imap.connect()
        await imap.run_idle_loop()
        imap.idle_loop_step.assert_called_once_with()
