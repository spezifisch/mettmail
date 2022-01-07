# type: ignore
"""
This file is part of mettmail (https://github.com/spezifisch/mettmail).
Copyright (c) 2022 spezifisch (https://github.com/spezifisch)

This program is free software: you can redistribute it and/or modify
it under the terms of the GNU General Public License as published by
the Free Software Foundation, version 3 of the License.

This program is distributed in the hope that it will be useful,
but WITHOUT ANY WARRANTY; without even the implied warranty of
MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
GNU General Public License for more details.

You should have received a copy of the GNU General Public License
along with this program.  If not, see <http://www.gnu.org/licenses/>.
"""

import asyncio
import unittest
from socket import gaierror
from unittest.mock import AsyncMock, Mock, PropertyMock, call, mock_open, patch

import aioimaplib
from aioimaplib import Response

from mettmail.deliver_base import DeliverBase
from mettmail.exceptions import *
from mettmail.fetch_imap import FetchIMAP


class TestFetchIMAPConnected(unittest.IsolatedAsyncioTestCase):
    TEST_HOST = "example.com"
    TEST_MAIL_MSG = bytearray(
        b"From: noreply.foo@mailgen.example.com\r\nTo: foo@testcot\r\nSubject: test mail 1641157914 to foo\r\n"
        + b"Date: Sun, 02 Jan 2022 21:11:54 +0000\r\n\r\nthis is content\r\n"
    )

    DOVECOT_FETCH_RESPONSE = [
        b"123 FETCH (UID 123 FLAGS () RFC822.SIZE 152 BODY[] {152}",
        TEST_MAIL_MSG,
        b")",
        b"Fetch completed (0.001 + 0.000 secs).",
    ]

    def setUp(self) -> None:
        self.mock_aioimaplib = patch("aioimaplib.IMAP4_SSL", autospec=True).start()
        self.addCleanup(patch.stopall)
        mock_object = self.mock_aioimaplib.return_value

        # return values for method calls for connect
        mock_object.wait_hello_from_server.return_value = None
        mock_object.has_capability.return_value = True  # yes, we have IDLE
        mock_object.login.return_value = Response("OK", [])
        mock_object.select.return_value = Response("OK", [])
        mock_object.protocol = PropertyMock(return_value=[])
        # disconnect
        mock_object.logout.return_value = Response("OK", [])
        # idle loop
        f = asyncio.Future()
        f.set_result("foo")
        mock_object.idle_start.return_value = f
        mock_object.wait_server_push.return_value = aioimaplib.STOP_WAIT_SERVER_PUSH
        mock_object.idle_done.return_value = None

        self.response_no = Response("NO", [])
        self.response_bad = Response("BAD", [])

        self.deliver_mock = Mock(spec_set=DeliverBase)
        self.deliver_mock.deliver_message.return_value = True

        self.deliver_mock_bad = Mock(spec_set=DeliverBase)
        self.deliver_mock_bad.deliver_message.return_value = False

        self.imap = FetchIMAP(
            host=self.TEST_HOST,
            deliverer=self.deliver_mock,
        )
        self.imap.timeout_idle_start = 1
        self.imap.timeout_idle_end = 1
        self.imap.is_permanentflag_supported = Mock(return_value=True)  # yes, we can add new PERMANENTFLAGS

    async def test_setup(self) -> None:
        await self.imap.connect()
        self.mock_aioimaplib.assert_called_once_with(host=self.TEST_HOST, port=aioimaplib.IMAP4_SSL_PORT, timeout=30)
        assert self.imap.client is not None

    async def test_set_fetched_flag_success(self) -> None:
        await self.imap.connect()

        mock_object = self.mock_aioimaplib.return_value
        mock_object.uid.return_value = Response(result="OK", lines=[b"Store completed (0.001 + 0.000 secs)."])

        uid = 123
        await self.imap.set_fetched_flag(uid)

        mock_object.uid.assert_called_once_with("store", str(uid), "+FLAGS.SILENT (MettmailFetched)")

    async def test_set_fetched_flag_unexpected_line(self) -> None:
        await self.imap.connect()

        mock_object = self.mock_aioimaplib.return_value
        mock_object.uid.return_value = Response(result="OK", lines=[b"All your base are belong to us."])

        with self.assertRaises(MettmailFetchUnexpectedResponse) as ctx:
            await self.imap.set_fetched_flag(123)
        assert "expected completed" in str(ctx.exception)

    async def test_set_fetched_flag_unexpected_lines(self) -> None:
        await self.imap.connect()

        mock_object = self.mock_aioimaplib.return_value
        mock_object.uid.return_value = Response(result="OK", lines=[b"All your base are", b"belong to us."])

        with self.assertRaises(MettmailFetchUnexpectedResponse) as ctx:
            await self.imap.set_fetched_flag(123)
        assert "expected one line" in str(ctx.exception)

    async def test_set_fetched_flag_denied(self) -> None:
        await self.imap.connect()

        mock_object = self.mock_aioimaplib.return_value
        mock_object.uid.return_value = self.response_no

        with self.assertRaises(MettmailFetchCommandFailed) as ctx:
            await self.imap.set_fetched_flag(123)
        assert "failed marking" in str(ctx.exception)

    async def test_set_fetched_flag_timeout(self) -> None:
        await self.imap.connect()

        mock_object = self.mock_aioimaplib.return_value
        mock_object.uid.side_effect = asyncio.TimeoutError("test")

        with self.assertRaises(MettmailFetchTimeoutError) as ctx:
            await self.imap.set_fetched_flag(123)
        assert "store timeout" == str(ctx.exception)

    async def test_fdm_success(self) -> None:
        # that method is already tested above
        self.imap.set_fetched_flag = AsyncMock()

        mock_object = self.mock_aioimaplib.return_value
        mock_object.uid.return_value = Response(result="OK", lines=self.DOVECOT_FETCH_RESPONSE)

        await self.imap.connect()
        uid = 123
        await self.imap.fetch_deliver_message(uid)

        # imap fetch
        mock_object.uid.assert_called_once_with("fetch", str(uid), "(FLAGS RFC822.SIZE BODY.PEEK[])")
        # lmtp delivered
        self.deliver_mock.deliver_message.assert_called_once_with(self.TEST_MAIL_MSG)
        # flagged as fetched
        self.imap.set_fetched_flag.assert_called_once_with(uid)

    async def test_fdm_bogus_deliver(self) -> None:
        self.imap.set_fetched_flag = AsyncMock()
        # simulate an error (returned False) that should have raised an exception, but didn't due to a bug
        self.deliver_mock.deliver_message.return_value = False

        mock_object = self.mock_aioimaplib.return_value
        mock_object.uid.return_value = Response(result="OK", lines=self.DOVECOT_FETCH_RESPONSE)

        await self.imap.connect()
        with self.assertRaises(MettmailFetchStateError) as ctx:
            await self.imap.fetch_deliver_message(123)
        assert "no exception was" in str(ctx.exception)

        # imap fetch
        mock_object.uid.assert_called_once()
        # lmtp tried to deliver
        self.deliver_mock.deliver_message.assert_called_once_with(self.TEST_MAIL_MSG)
        # NOT flagged as fetched
        self.imap.set_fetched_flag.assert_not_called()

    async def test_fdm_deliver_fail(self) -> None:
        self.imap.set_fetched_flag = AsyncMock()
        # simulate a regular error (exception raised)
        self.deliver_mock.deliver_message.return_value = False
        self.deliver_mock.deliver_message.side_effect = MettmailDeliverRecipientRefused("test")

        mock_object = self.mock_aioimaplib.return_value
        mock_object.uid.return_value = Response(result="OK", lines=self.DOVECOT_FETCH_RESPONSE)

        await self.imap.connect()
        with self.assertRaises(MettmailDeliverException) as ctx:
            await self.imap.fetch_deliver_message(123)
        assert "test" == str(ctx.exception)

        # imap fetch
        mock_object.uid.assert_called_once()
        # lmtp tried to deliver
        self.deliver_mock.deliver_message.assert_called_once_with(self.TEST_MAIL_MSG)
        # NOT flagged as fetched
        self.imap.set_fetched_flag.assert_not_called()

    async def test_fdm_bad_message_size(self) -> None:
        self.imap.set_fetched_flag = AsyncMock()

        mock_object = self.mock_aioimaplib.return_value
        lines = [self.DOVECOT_FETCH_RESPONSE[0], bytearray(b"another message")] + self.DOVECOT_FETCH_RESPONSE[2:]
        mock_object.uid.return_value = Response(result="OK", lines=lines)

        await self.imap.connect()
        with self.assertRaises(MettmailFetchInconsistentResponse) as ctx:
            await self.imap.fetch_deliver_message(123)
        assert "expected message size" in str(ctx.exception)

        # imap fetch
        mock_object.uid.assert_called_once()
        # lmtp did NOT try to deliver
        self.deliver_mock.deliver_message.assert_not_called()
        # NOT flagged as fetched
        self.imap.set_fetched_flag.assert_not_called()

    async def test_fdm_missing_message_flags(self) -> None:
        self.imap.set_fetched_flag = AsyncMock()

        mock_object = self.mock_aioimaplib.return_value
        lines = [self.DOVECOT_FETCH_RESPONSE[0].replace(b"FLAGS", b"FOO")] + self.DOVECOT_FETCH_RESPONSE[1:]
        mock_object.uid.return_value = Response(result="OK", lines=lines)

        await self.imap.connect()
        with self.assertRaises(MettmailFetchUnexpectedResponse) as ctx:
            await self.imap.fetch_deliver_message(123)

        # imap fetch
        mock_object.uid.assert_called_once()
        # lmtp did NOT try to deliver
        self.deliver_mock.deliver_message.assert_not_called()
        # NOT flagged as fetched
        self.imap.set_fetched_flag.assert_not_called()

    async def test_fdm_missing_message_size(self) -> None:
        self.imap.set_fetched_flag = AsyncMock()

        mock_object = self.mock_aioimaplib.return_value
        lines = [self.DOVECOT_FETCH_RESPONSE[0].replace(b"RFC822.SIZE", b"FOO")] + self.DOVECOT_FETCH_RESPONSE[1:]
        mock_object.uid.return_value = Response(result="OK", lines=lines)

        await self.imap.connect()
        with self.assertRaises(MettmailFetchUnexpectedResponse) as ctx:
            await self.imap.fetch_deliver_message(123)

        # imap fetch
        mock_object.uid.assert_called_once()
        # lmtp did NOT try to deliver
        self.deliver_mock.deliver_message.assert_not_called()
        # NOT flagged as fetched
        self.imap.set_fetched_flag.assert_not_called()

    async def test_fdm_already_flagged(self) -> None:
        self.imap.set_fetched_flag = AsyncMock()

        mock_object = self.mock_aioimaplib.return_value
        # dovecot seems to ignore case, storing "MettmailFetched" flag as "mettmailfetched" (conforming to standard)
        lines = [
            self.DOVECOT_FETCH_RESPONSE[0].replace(b"FLAGS ()", b"FLAGS (\\Seen mettmailfetched)")
        ] + self.DOVECOT_FETCH_RESPONSE[1:]
        mock_object.uid.return_value = Response(result="OK", lines=lines)

        await self.imap.connect()
        await self.imap.fetch_deliver_message(123)

        # imap fetch
        mock_object.uid.assert_called_once()
        # lmtp did NOT try to deliver
        self.deliver_mock.deliver_message.assert_not_called()
        # NOT flagged as fetched
        self.imap.set_fetched_flag.assert_not_called()

    async def test_fdm_bad_response(self) -> None:
        self.imap.set_fetched_flag = AsyncMock()

        mock_object = self.mock_aioimaplib.return_value
        lines = self.DOVECOT_FETCH_RESPONSE[:3] + [b"MOIN"]
        mock_object.uid.return_value = Response(result="OK", lines=lines)

        await self.imap.connect()
        with self.assertRaises(MettmailFetchUnexpectedResponse) as ctx:
            await self.imap.fetch_deliver_message(123)
        assert "expected completed string" in str(ctx.exception)

        # imap fetch
        mock_object.uid.assert_called_once()
        # lmtp did NOT try to deliver
        self.deliver_mock.deliver_message.assert_not_called()
        # NOT flagged as fetched
        self.imap.set_fetched_flag.assert_not_called()

    async def test_fdm_bad_response_lines(self) -> None:
        self.imap.set_fetched_flag = AsyncMock()

        mock_object = self.mock_aioimaplib.return_value
        lines = self.DOVECOT_FETCH_RESPONSE[:3]
        mock_object.uid.return_value = Response(result="OK", lines=lines)

        await self.imap.connect()
        with self.assertRaises(MettmailFetchUnexpectedResponse) as ctx:
            await self.imap.fetch_deliver_message(123)
        assert "expected 4 lines" in str(ctx.exception)

        # imap fetch
        mock_object.uid.assert_called_once()
        # lmtp did NOT try to deliver
        self.deliver_mock.deliver_message.assert_not_called()
        # NOT flagged as fetched
        self.imap.set_fetched_flag.assert_not_called()

    async def test_fdm_denied(self) -> None:
        self.imap.set_fetched_flag = AsyncMock()

        mock_object = self.mock_aioimaplib.return_value
        mock_object.uid.return_value = self.response_no

        await self.imap.connect()
        with self.assertRaises(MettmailFetchCommandFailed) as ctx:
            await self.imap.fetch_deliver_message(123)
        assert "fetch failed" in str(ctx.exception)

        # imap fetch
        mock_object.uid.assert_called_once()
        # lmtp did NOT try to deliver
        self.deliver_mock.deliver_message.assert_not_called()
        # NOT flagged as fetched
        self.imap.set_fetched_flag.assert_not_called()

    async def test_fdm_denied_bad(self) -> None:
        self.imap.set_fetched_flag = AsyncMock()

        mock_object = self.mock_aioimaplib.return_value
        mock_object.uid.return_value = self.response_bad

        await self.imap.connect()
        with self.assertRaises(MettmailFetchCommandFailed) as ctx:
            await self.imap.fetch_deliver_message(123)
        assert "fetch failed" in str(ctx.exception)

        # imap fetch
        mock_object.uid.assert_called_once()
        # lmtp did NOT try to deliver
        self.deliver_mock.deliver_message.assert_not_called()
        # NOT flagged as fetched
        self.imap.set_fetched_flag.assert_not_called()

    async def test_fdm_timeout(self) -> None:
        self.imap.set_fetched_flag = AsyncMock()

        mock_object = self.mock_aioimaplib.return_value
        mock_object.uid.side_effect = asyncio.TimeoutError("test")

        await self.imap.connect()
        with self.assertRaises(MettmailFetchTimeoutError) as ctx:
            await self.imap.fetch_deliver_message(123)
        assert "fetch timeout" in str(ctx.exception)

        # imap fetch
        mock_object.uid.assert_called_once()
        # lmtp did NOT try to deliver
        self.deliver_mock.deliver_message.assert_not_called()
        # NOT flagged as fetched
        self.imap.set_fetched_flag.assert_not_called()

    async def test_fdu_success_single(self) -> None:
        self.imap.fetch_deliver_message = AsyncMock()

        mock_object = self.mock_aioimaplib.return_value
        mock_object.uid_search.return_value = Response("OK", [b"1134", b"Search completed (0.001 + 0.000 secs)."])

        await self.imap.connect()
        await self.imap.fetch_deliver_unflagged_messages()

        self.imap.fetch_deliver_message.assert_called_once_with(1134)

        mock_object.uid_search.assert_called_once_with("UNKEYWORD MettmailFetched")
        mock_object.uid.assert_not_called()
        self.deliver_mock.connect.assert_called_once_with()
        self.deliver_mock.deliver_message.assert_not_called()  # mocked out
        self.deliver_mock.disconnect.assert_called_once_with()

    async def test_fdu_success_multiple(self) -> None:
        self.imap.fetch_deliver_message = AsyncMock()

        mock_object = self.mock_aioimaplib.return_value
        mock_object.uid_search.return_value = Response(
            "OK", [b"2 4 6 8 10", b"Search completed (0.001 + 0.000 secs)."]
        )

        await self.imap.connect()
        await self.imap.fetch_deliver_unflagged_messages()

        self.imap.fetch_deliver_message.assert_has_calls([call(x) for x in (2, 4, 6, 8, 10)])

        mock_object.uid_search.assert_called_once_with("UNKEYWORD MettmailFetched")
        mock_object.uid.assert_not_called()
        self.deliver_mock.connect.assert_called_once_with()
        self.deliver_mock.deliver_message.assert_not_called()
        self.deliver_mock.disconnect.assert_called_once_with()

    async def test_fdu_success_none(self) -> None:
        self.imap.fetch_deliver_message = AsyncMock()

        mock_object = self.mock_aioimaplib.return_value
        mock_object.uid_search.return_value = Response("OK", [b"", b"Search completed (0.001 + 0.000 secs)."])

        await self.imap.connect()
        await self.imap.fetch_deliver_unflagged_messages()

        self.imap.fetch_deliver_message.assert_not_called()

        mock_object.uid_search.assert_called_once()
        mock_object.uid.assert_not_called()
        self.deliver_mock.connect.assert_not_called()  # shouldn't connect when there are no messages
        self.deliver_mock.deliver_message.assert_not_called()
        self.deliver_mock.disconnect.assert_not_called()

    async def test_fdu_bad_response(self) -> None:
        self.imap.fetch_deliver_message = AsyncMock()

        mock_object = self.mock_aioimaplib.return_value
        mock_object.uid_search.return_value = Response("OK", [b"MOIN", b"MOIN"])

        await self.imap.connect()
        with self.assertRaises(MettmailFetchUnexpectedResponse) as ctx:
            await self.imap.fetch_deliver_unflagged_messages()
        assert "expected completed string" in str(ctx.exception)

        self.deliver_mock.connect.assert_not_called()
        self.imap.fetch_deliver_message.assert_not_called()

    async def test_fdu_bad_response_lines(self) -> None:
        self.imap.fetch_deliver_message = AsyncMock()

        mock_object = self.mock_aioimaplib.return_value
        mock_object.uid_search.return_value = Response("OK", [b"MOIN"])

        await self.imap.connect()
        with self.assertRaises(MettmailFetchUnexpectedResponse) as ctx:
            await self.imap.fetch_deliver_unflagged_messages()
        assert "expected 2 lines" in str(ctx.exception)

        self.deliver_mock.connect.assert_not_called()
        self.imap.fetch_deliver_message.assert_not_called()

    async def test_fdu_response_denied(self) -> None:
        self.imap.fetch_deliver_message = AsyncMock()

        mock_object = self.mock_aioimaplib.return_value
        mock_object.uid_search.return_value = self.response_no

        await self.imap.connect()
        with self.assertRaises(MettmailFetchCommandFailed) as ctx:
            await self.imap.fetch_deliver_unflagged_messages()
        assert "search failed" in str(ctx.exception)

        self.deliver_mock.connect.assert_not_called()
        self.imap.fetch_deliver_message.assert_not_called()

    async def test_fdu_response_timeout(self) -> None:
        self.imap.fetch_deliver_message = AsyncMock()

        mock_object = self.mock_aioimaplib.return_value
        mock_object.uid_search.side_effect = asyncio.TimeoutError("test")

        await self.imap.connect()
        with self.assertRaises(MettmailFetchTimeoutError) as ctx:
            await self.imap.fetch_deliver_unflagged_messages()
        assert "search timeout" == str(ctx.exception)

        self.deliver_mock.connect.assert_not_called()
        self.imap.fetch_deliver_message.assert_not_called()

    async def test_idle_loop_no_mail(self) -> None:
        self.imap.fetch_deliver_message = AsyncMock()

        mock_object = self.mock_aioimaplib.return_value

        await self.imap.connect()
        ret = await self.imap.idle_loop_step()
        assert True == ret

        mock_object.idle_start.assert_called_once_with(timeout=1)
        mock_object.wait_server_push.assert_called_once_with()
        mock_object.idle_done.assert_called_once_with()
        self.deliver_mock.connect.assert_not_called()
        self.imap.fetch_deliver_message.assert_not_called()
        self.deliver_mock.disconnect.assert_not_called()

    async def test_idle_loop_one_mail(self) -> None:
        self.imap.fetch_deliver_message = AsyncMock()

        mock_object = self.mock_aioimaplib.return_value
        mock_object.wait_server_push.return_value = [b"23 EXISTS", b"1 RECENT", b"OK Still here"]

        await self.imap.connect()
        ret = await self.imap.idle_loop_step()
        assert True == ret

        mock_object.idle_start.assert_called_once_with(timeout=1)
        mock_object.wait_server_push.assert_called_once_with()
        mock_object.idle_done.assert_called_once_with()
        self.deliver_mock.connect.assert_called_once_with()
        self.imap.fetch_deliver_message.assert_called_once_with(23)
        self.deliver_mock.disconnect.assert_called_once_with()

    async def test_idle_loop_dconnect_exception(self) -> None:
        self.imap.fetch_deliver_message = AsyncMock()
        self.deliver_mock.connect.side_effect = MettmailDeliverConnectError("test")

        mock_object = self.mock_aioimaplib.return_value
        mock_object.wait_server_push.return_value = [b"1 EXISTS", b"1 RECENT"]

        await self.imap.connect()
        with self.assertRaises(MettmailDeliverConnectError) as ctx:
            await self.imap.idle_loop_step()
        assert "test" == str(ctx.exception)

        mock_object.idle_start.assert_called_once_with(timeout=1)
        mock_object.wait_server_push.assert_called_once_with()
        mock_object.idle_done.assert_called_once_with()
        self.deliver_mock.connect.assert_called_once_with()
        self.imap.fetch_deliver_message.assert_not_called()
        self.deliver_mock.disconnect.assert_not_called()

    async def test_idle_loop_fdm_exception(self) -> None:
        self.imap.fetch_deliver_message = AsyncMock()
        self.imap.fetch_deliver_message.side_effect = MettmailDeliverRecipientRefused("test")

        mock_object = self.mock_aioimaplib.return_value
        mock_object.wait_server_push.return_value = [b"1 EXISTS", b"1 RECENT"]

        await self.imap.connect()
        with self.assertRaises(MettmailDeliverRecipientRefused) as ctx:
            await self.imap.idle_loop_step()
        assert "test" == str(ctx.exception)

        mock_object.idle_start.assert_called_once_with(timeout=1)
        mock_object.wait_server_push.assert_called_once_with()
        mock_object.idle_done.assert_called_once_with()
        self.deliver_mock.connect.assert_called_once_with()
        self.imap.fetch_deliver_message.assert_called_once_with(1)
        self.deliver_mock.disconnect.assert_not_called()

    async def test_idle_loop_idle_end_timeout(self) -> None:
        mock_object = self.mock_aioimaplib.return_value
        mock_object.wait_server_push.return_value = aioimaplib.STOP_WAIT_SERVER_PUSH
        # don't set the future so it will lead to a timeout
        mock_object.idle_start.return_value = asyncio.Future()

        await self.imap.connect()
        with self.assertRaises(MettmailFetchTimeoutError) as ctx:
            await self.imap.idle_loop_step()
        assert "idle end timeout" == str(ctx.exception)

        mock_object.idle_start.assert_called_once_with(timeout=1)
        mock_object.wait_server_push.assert_called_once_with()
        mock_object.idle_done.assert_called_once_with()
        self.deliver_mock.connect.assert_not_called()
        self.deliver_mock.disconnect.assert_not_called()

    async def test_idle_loop_wait_push_timeout(self) -> None:
        mock_object = self.mock_aioimaplib.return_value
        mock_object.wait_server_push.side_effect = asyncio.TimeoutError("test")

        await self.imap.connect()
        ret = await self.imap.idle_loop_step()
        assert True == ret

        mock_object.idle_start.assert_called_once_with(timeout=1)
        mock_object.wait_server_push.assert_called_once_with()
        mock_object.idle_done.assert_called_once_with()
        self.deliver_mock.connect.assert_not_called()
        self.deliver_mock.disconnect.assert_not_called()

    async def test_idle_loop_idle_start_timeout(self) -> None:
        mock_object = self.mock_aioimaplib.return_value
        mock_object.idle_start.side_effect = asyncio.TimeoutError("test")

        await self.imap.connect()
        with self.assertRaises(MettmailFetchTimeoutError) as ctx:
            await self.imap.idle_loop_step()
        assert "idle start timeout" == str(ctx.exception)

        mock_object.idle_start.assert_called_once_with(timeout=1)
        mock_object.wait_server_push.assert_not_called()
        mock_object.idle_done.assert_not_called()
        self.deliver_mock.connect.assert_not_called()
        self.deliver_mock.disconnect.assert_not_called()

    async def test_idle_loop_idle_start_abort(self) -> None:
        mock_object = self.mock_aioimaplib.return_value
        mock_object.idle_start.side_effect = aioimaplib.Abort("test")

        await self.imap.connect()
        with self.assertRaises(MettmailFetchAbort) as ctx:
            await self.imap.idle_loop_step()
        assert "idle start abort" == str(ctx.exception)

        mock_object.idle_start.assert_called_once_with(timeout=1)
        mock_object.wait_server_push.assert_not_called()
        mock_object.idle_done.assert_not_called()
        self.deliver_mock.connect.assert_not_called()
        self.deliver_mock.disconnect.assert_not_called()
