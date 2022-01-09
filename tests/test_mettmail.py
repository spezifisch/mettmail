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

import sys
from io import StringIO
from unittest import IsolatedAsyncioTestCase
from unittest.mock import AsyncMock

from loguru import logger

from mettmail import __version__, mettmail
from mettmail.exceptions import (
    MettmailDeliverConnectError,
    MettmailFetchAuthenticationError,
    MettmailFetchCommandFailed,
    MettmailFetchTimeoutError,
)
from mettmail.fetch_imap import FetchIMAP


def test_version() -> None:
    assert __version__ == "0.1.0"


class TestMettmailMain(IsolatedAsyncioTestCase):
    def setUp(self) -> None:
        logger.remove()
        logger.add(sys.stderr, level="INFO", diagnose=False, backtrace=False)

        self.error_log = StringIO()
        logger.add(self.error_log, level="ERROR", format="{message}", diagnose=False, backtrace=False)

        self.mock_fetcher = AsyncMock(spec_set=FetchIMAP)

    async def test_loop_success(self):
        self.mock_fetcher.has_idle.return_value = True

        await mettmail.mettmail_loop(self.mock_fetcher)

        self.mock_fetcher.connect.assert_called_once_with()
        self.mock_fetcher.fetch_deliver_unflagged_messages.assert_called_once_with()
        self.mock_fetcher.has_idle.assert_called_once_with()
        self.mock_fetcher.run_idle_loop.assert_called_once_with()

    async def test_loop_success_no_idle(self):
        self.mock_fetcher.has_idle.return_value = False

        await mettmail.mettmail_loop(self.mock_fetcher)

        self.mock_fetcher.connect.assert_called_once_with()
        self.mock_fetcher.fetch_deliver_unflagged_messages.assert_called_once_with()
        self.mock_fetcher.has_idle.assert_called_once_with()
        self.mock_fetcher.run_idle_loop.assert_not_called()

    async def test_loop_exception_idle_deliver(self):
        self.mock_fetcher.has_idle.return_value = True
        self.mock_fetcher.run_idle_loop.side_effect = MettmailDeliverConnectError("test")

        await mettmail.mettmail_loop(self.mock_fetcher)

        assert self.error_log.getvalue().startswith("deliverer error\nTraceback")

        self.mock_fetcher.run_idle_loop.assert_called_once()

    async def test_loop_exception_idle_fetch(self):
        self.mock_fetcher.has_idle.return_value = True
        self.mock_fetcher.run_idle_loop.side_effect = MettmailFetchTimeoutError("test")

        await mettmail.mettmail_loop(self.mock_fetcher)

        assert self.error_log.getvalue().startswith("fetcher error\nTraceback")

        self.mock_fetcher.run_idle_loop.assert_called_once()

    async def test_loop_exception_fdum(self):
        self.mock_fetcher.fetch_deliver_unflagged_messages.side_effect = MettmailFetchCommandFailed("test")

        await mettmail.mettmail_loop(self.mock_fetcher)

        assert self.error_log.getvalue().startswith("fetcher error\nTraceback")

        self.mock_fetcher.fetch_deliver_unflagged_messages.assert_called_once_with()
        self.mock_fetcher.has_idle.assert_not_called()
        self.mock_fetcher.run_idle_loop.assert_not_called()

    async def test_loop_exception_connect_auth(self):
        self.mock_fetcher.connect.side_effect = MettmailFetchAuthenticationError("test")

        await mettmail.mettmail_loop(self.mock_fetcher)

        assert self.error_log.getvalue().startswith("login failed\nTraceback")

        self.mock_fetcher.connect.assert_called_with()
        self.mock_fetcher.fetch_deliver_unflagged_messages.assert_not_called()

    async def test_loop_exception_connect_failed(self):
        self.mock_fetcher.connect.side_effect = MettmailFetchTimeoutError("test")

        await mettmail.mettmail_loop(self.mock_fetcher)

        assert self.error_log.getvalue().startswith("connection failed\nTraceback")

        self.mock_fetcher.connect.assert_called_with()
        self.mock_fetcher.fetch_deliver_unflagged_messages.assert_not_called()
