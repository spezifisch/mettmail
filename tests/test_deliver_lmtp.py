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

import unittest
from unittest.mock import patch

from mettmail.exceptions import *


class TestDeliverLMTP(unittest.TestCase):
    TEST_HOST = "example.com"
    TEST_PORT = 24
    TEST_RECIPIENT = "foo@example.com"
    TEST_MAIL_MSG = bytearray(
        b"From: noreply.foo@mailgen.example.com\r\nTo: foo@testcot\r\nSubject: test mail 1641157914 to foo\r\n"
        + b"Date: Sun, 02 Jan 2022 21:11:54 +0000\r\n\r\nthis is content\r\n"
    )

    def test_success(self) -> None:
        with patch("smtplib.LMTP", autospec=True) as mock:
            mock_object = mock.return_value
            # empty dict means success
            mock_object.sendmail.return_value = {}

            from mettmail.deliver_lmtp import DeliverLMTP

            lmtp = DeliverLMTP(host=self.TEST_HOST, port=self.TEST_PORT, envelope_recipient=self.TEST_RECIPIENT)

            lmtp.connect()
            mock.assert_called_once_with(
                host=self.TEST_HOST, port=self.TEST_PORT, local_hostname=None, source_address=None
            )

            mock_object.ehlo.assert_called_once()
            name, args, kwargs = mock.method_calls.pop(0)
            assert name == "().ehlo"

            delivery_ok = lmtp.deliver_message(self.TEST_MAIL_MSG)
            mock_object.sendmail.assert_called_once()
            name, args, kwargs = mock.method_calls.pop(0)
            assert name == "().sendmail"
            assert kwargs.get("from_addr") == "mettmail@localhost"
            assert kwargs.get("to_addrs") == self.TEST_RECIPIENT
            assert b"this is content" in kwargs.get("msg")
            assert delivery_ok == True

            lmtp.disconnect()
            mock_object.quit.assert_called_once()
            name, args, kwargs = mock.method_calls.pop(0)
            assert name == "().quit"

    def test_invalid_constructor_args(self) -> None:
        with patch("smtplib.LMTP", autospec=True) as mock:
            from mettmail.deliver_lmtp import DeliverLMTP

            with self.assertRaises(ValueError):
                DeliverLMTP(host=self.TEST_HOST, port=self.TEST_PORT, envelope_recipient="")

            with self.assertRaises(ValueError):
                DeliverLMTP(host=self.TEST_HOST, port=self.TEST_PORT, envelope_recipient=None)

            with self.assertRaises(ValueError):
                DeliverLMTP(
                    host=self.TEST_HOST,
                    port=self.TEST_PORT,
                    envelope_recipient=self.TEST_RECIPIENT,
                    envelope_sender="",
                )

            with self.assertRaises(ValueError):
                DeliverLMTP(
                    host=self.TEST_HOST,
                    port=self.TEST_PORT,
                    envelope_recipient=self.TEST_RECIPIENT,
                    envelope_sender=None,
                )

    def test_fail_connect(self) -> None:
        with patch("smtplib.LMTP", autospec=True, side_effect=OSError("test")) as mock:
            from mettmail.deliver_lmtp import DeliverLMTP

            host = "invalid.example.com"
            port = 24
            recipient = "foo@invalid2.example.com"
            lmtp = DeliverLMTP(host=host, port=port, envelope_recipient=recipient)

            with self.assertRaises(MettmailDeliverConnectError):
                lmtp.connect()
