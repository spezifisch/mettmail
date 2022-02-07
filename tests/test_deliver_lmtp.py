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

import unittest
from smtplib import (
    SMTPException,
    SMTPNotSupportedError,
    SMTPRecipientsRefused,
    SMTPServerDisconnected,
)
from socket import gaierror
from unittest.mock import patch

from mettmail.deliver_lmtp import DeliverLMTP
from mettmail.exceptions import (
    MettmailDeliverCommandFailed,
    MettmailDeliverConnectError,
    MettmailDeliverRecipientRefused,
    MettmailDeliverStateError,
)


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

            lmtp = DeliverLMTP(host=self.TEST_HOST, port=self.TEST_PORT, envelope_recipient=self.TEST_RECIPIENT)

            lmtp.connect()
            mock.assert_called_once_with(
                host=self.TEST_HOST, port=self.TEST_PORT, local_hostname=None, source_address=None
            )

            mock_object.ehlo.assert_called_once()
            name, args, kwargs = mock.method_calls.pop(0)
            assert name == "().ehlo"

            # send mail
            delivery_ok = lmtp.deliver_message(self.TEST_MAIL_MSG)
            mock_object.sendmail.assert_called_once()
            name, args, kwargs = mock.method_calls.pop(0)
            assert name == "().sendmail"
            assert kwargs.get("from_addr") == "mettmail@localhost"
            assert kwargs.get("to_addrs") == self.TEST_RECIPIENT
            assert b"this is content" in kwargs.get("msg")
            assert delivery_ok is True

            # quit
            lmtp.disconnect()
            mock_object.quit.assert_called_once()
            name, args, kwargs = mock.method_calls.pop(0)
            assert name == "().quit"

    def test_invalid_constructor_args(self) -> None:
        with patch("smtplib.LMTP", autospec=True):
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

    def test_state_errors(self) -> None:
        with patch("smtplib.LMTP", autospec=True) as mock:
            lmtp = DeliverLMTP(host=self.TEST_HOST, port=self.TEST_PORT, envelope_recipient=self.TEST_RECIPIENT)

            # shouldn't to anything because we're not connected yet
            lmtp.disconnect()
            mock.return_value.quit.assert_not_called()

            with self.assertRaises(MettmailDeliverStateError) as ctx:
                lmtp.deliver_message(self.TEST_MAIL_MSG)
            assert "tried to deliver" in str(ctx.exception)

            lmtp.connect()
            mock.assert_called_once_with(
                host=self.TEST_HOST, port=self.TEST_PORT, local_hostname=None, source_address=None
            )

            # check double connect safeguard
            lmtp.connect()
            mock.return_value.quit.assert_called_once()

            # add quit exception
            mock.return_value.quit.side_effect = SMTPException("test")
            lmtp.disconnect()

    def test_fail_connect_errors_disconnect(self) -> None:
        # things that raise on LMTP object construction
        with patch("smtplib.LMTP", autospec=True, side_effect=SMTPServerDisconnected("test")) as mock:
            lmtp = DeliverLMTP(host=self.TEST_HOST, port=self.TEST_PORT, envelope_recipient=self.TEST_RECIPIENT)
            with self.assertRaises(MettmailDeliverConnectError) as ctx:
                lmtp.connect()
            assert "connection error" in str(ctx.exception)

    def test_fail_connect_errors_notsupp(self) -> None:
        with patch("smtplib.LMTP", autospec=True, side_effect=SMTPNotSupportedError("test")) as mock:
            lmtp = DeliverLMTP(host=self.TEST_HOST, port=self.TEST_PORT, envelope_recipient=self.TEST_RECIPIENT)
            with self.assertRaises(MettmailDeliverConnectError) as ctx:
                lmtp.connect()
            assert "smtp error" in str(ctx.exception)

    def test_fail_connect_errors_gaierror(self) -> None:
        with patch("smtplib.LMTP", autospec=True, side_effect=gaierror("test")) as mock:
            lmtp = DeliverLMTP(host=self.TEST_HOST, port=self.TEST_PORT, envelope_recipient=self.TEST_RECIPIENT)
            with self.assertRaises(MettmailDeliverConnectError) as ctx:
                lmtp.connect()
            assert "socket error" in str(ctx.exception)

    def test_fail_connect_errors_socketerror(self) -> None:
        with patch("smtplib.LMTP", autospec=True, side_effect=OSError("test")) as mock:
            lmtp = DeliverLMTP(host=self.TEST_HOST, port=self.TEST_PORT, envelope_recipient=self.TEST_RECIPIENT)
            with self.assertRaises(MettmailDeliverConnectError) as ctx:
                lmtp.connect()
            assert "socket error" in str(ctx.exception)

    def test_fail_connect_errors_ehlo_disconnect(self) -> None:
        # raises on ehlo
        with patch("smtplib.LMTP", autospec=True) as mock:
            mock.return_value.ehlo.side_effect = SMTPServerDisconnected("test")

            lmtp = DeliverLMTP(host=self.TEST_HOST, port=self.TEST_PORT, envelope_recipient=self.TEST_RECIPIENT)
            with self.assertRaises(MettmailDeliverCommandFailed) as ctx:
                lmtp.connect()
            assert "LHLO failed" in str(ctx.exception)

    def test_fail_connect_errors_valueerror(self) -> None:
        # uncovered exceptions should pass through so we can log and fix them
        with patch("smtplib.LMTP", autospec=True, side_effect=ValueError("test")):
            lmtp = DeliverLMTP(host=self.TEST_HOST, port=self.TEST_PORT, envelope_recipient=self.TEST_RECIPIENT)
            with self.assertRaises(ValueError):
                lmtp.connect()

    def test_fail_connect_errors_ehlo_valueerror(self) -> None:
        with patch("smtplib.LMTP", autospec=True) as mock:
            mock.return_value.ehlo.side_effect = ValueError("test")
            lmtp = DeliverLMTP(host=self.TEST_HOST, port=self.TEST_PORT, envelope_recipient=self.TEST_RECIPIENT)
            with self.assertRaises(ValueError):
                lmtp.connect()

    def test_class_fudgery(self) -> None:
        with patch("smtplib.LMTP", autospec=True):
            lmtp = DeliverLMTP(host=self.TEST_HOST, port=self.TEST_PORT, envelope_recipient=self.TEST_RECIPIENT)
            lmtp.connect()

            lmtp.envelope_recipient = None

            with self.assertRaises(AssertionError):
                lmtp.deliver_message(self.TEST_MAIL_MSG)

    def test_delivery_errors_rcptrefused(self) -> None:
        # recipients refused
        with patch("smtplib.LMTP", autospec=True) as mock:
            mock_object = mock.return_value
            # normal behaviour: exception raised AND dict returned
            mock_object.sendmail.return_value = {self.TEST_RECIPIENT: (123, "test")}
            mock.return_value.sendmail.side_effect = SMTPRecipientsRefused("abc")

            lmtp = DeliverLMTP(host=self.TEST_HOST, port=self.TEST_PORT, envelope_recipient=self.TEST_RECIPIENT)
            lmtp.connect()

            with self.assertRaises(MettmailDeliverRecipientRefused) as ctx:
                lmtp.deliver_message(self.TEST_MAIL_MSG)
            assert "recipient refused" in str(ctx.exception)

    def test_delivery_errors_disconnect(self) -> None:
        # connection dropped
        with patch("smtplib.LMTP", autospec=True) as mock:
            mock_object = mock.return_value
            # normal behaviour: exception raised AND dict returned
            mock_object.sendmail.return_value = {self.TEST_RECIPIENT: (123, "test")}
            mock.return_value.sendmail.side_effect = SMTPServerDisconnected("abc")

            lmtp = DeliverLMTP(host=self.TEST_HOST, port=self.TEST_PORT, envelope_recipient=self.TEST_RECIPIENT)
            lmtp.connect()

            with self.assertRaises(MettmailDeliverCommandFailed) as ctx:
                lmtp.deliver_message(self.TEST_MAIL_MSG)
            assert "smtp failure" in str(ctx.exception)

    def test_delivery_errors_sendmail_oserror(self) -> None:
        # socket stuff
        with patch("smtplib.LMTP", autospec=True) as mock:
            mock_object = mock.return_value
            # kinda abnormal behaviour
            mock_object.sendmail.return_value = {}
            mock.return_value.sendmail.side_effect = OSError("test")

            lmtp = DeliverLMTP(host=self.TEST_HOST, port=self.TEST_PORT, envelope_recipient=self.TEST_RECIPIENT)
            lmtp.connect()

            with self.assertRaises(MettmailDeliverCommandFailed) as ctx:
                lmtp.deliver_message(self.TEST_MAIL_MSG)
            assert "general smtp failure" == str(ctx.exception)

    def test_delivery_errors_inconsistency1(self) -> None:
        # test weird stuff just in case
        with patch("smtplib.LMTP", autospec=True) as mock:
            mock_object = mock.return_value
            # abnormal behaviour: exception NOT raised but dict returned
            mock_object.sendmail.return_value = {self.TEST_RECIPIENT: (123, "test")}

            lmtp = DeliverLMTP(host=self.TEST_HOST, port=self.TEST_PORT, envelope_recipient=self.TEST_RECIPIENT)
            lmtp.connect()

            with self.assertRaises(MettmailDeliverCommandFailed) as ctx:
                lmtp.deliver_message(self.TEST_MAIL_MSG)
            assert "sending failed" in str(ctx.exception)

    def test_delivery_errors_inconsistency2(self) -> None:
        with patch("smtplib.LMTP", autospec=True) as mock:
            mock_object = mock.return_value
            # abnormal behaviour: exception not raised and non-dict returned (isn't possible)
            mock_object.sendmail.return_value = 123

            lmtp = DeliverLMTP(host=self.TEST_HOST, port=self.TEST_PORT, envelope_recipient=self.TEST_RECIPIENT)
            lmtp.connect()

            with self.assertRaises(AssertionError):
                lmtp.deliver_message(self.TEST_MAIL_MSG)
