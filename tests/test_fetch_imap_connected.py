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
from unittest.mock import AsyncMock, Mock, PropertyMock, mock_open, patch

import aioimaplib
from aioimaplib import Response

from mettmail.deliver_base import DeliverBase
from mettmail.exceptions import *
from mettmail.fetch_imap import FetchIMAP

from .test_fetch_imap import DeliverMock


class TestFetchIMAPConnected(unittest.IsolatedAsyncioTestCase):
    TEST_HOST = "example.com"
    TEST_MAIL_MSG = bytearray(
        b"From: noreply.foo@mailgen.example.com\r\nTo: foo@testcot\r\nSubject: test mail 1641157914 to foo\r\n"
        + b"Date: Sun, 02 Jan 2022 21:11:54 +0000\r\n\r\nthis is content\r\n"
    )

    def setUp(self) -> None:
        self.mock_aioimaplib = patch("aioimaplib.IMAP4_SSL", autospec=True).start()
        self.addCleanup(patch.stopall)
        mock_object = self.mock_aioimaplib.return_value

        # return values for method calls
        mock_object.wait_hello_from_server.return_value = None
        mock_object.has_capability.return_value = True  # yes, we have IDLE
        mock_object.login.return_value = Response("OK", [])
        mock_object.select.return_value = Response("OK", [])
        mock_object.logout.return_value = Response("OK", [])
        mock_object.protocol = PropertyMock(return_value=[])

        self.response_no = Response("NO", [])
        self.response_bad = Response("BAD", [])
        self.deliver_mock = DeliverMock(return_deliver_message=True)
        self.deliver_mock_bad = DeliverMock(return_deliver_message=False)

        self.imap = FetchIMAP(
            host=self.TEST_HOST,
            deliverer=self.deliver_mock,
        )
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
