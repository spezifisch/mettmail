#!/usr/bin/env python3
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

import smtplib
from typing import Optional, Tuple

from loguru import logger

from .deliver_base import DeliverBase
from .exceptions import (
    MettmailDeliverCommandFailed,
    MettmailDeliverConnectError,
    MettmailDeliverRecipientRefused,
    MettmailDeliverStateError,
)


class DeliverLMTP(DeliverBase):
    # Default envelope sender address if not specified in constructor parameters.
    # This address is used only for the mail envelope. Not to be confused with the RFC822 "From" header.
    # It might be recorded by the receiving mailserver in a RFC822 header like "X-Envelope-From", but otherwise its
    # value should be irrelevant.
    DEFAULT_SENDER = "mettmail@localhost"

    def __init__(
        self,
        host: str,
        envelope_recipient: str,
        port: int = smtplib.LMTP_PORT,
        envelope_sender: str = DEFAULT_SENDER,
        local_hostname: Optional[str] = None,
        source_address: Optional[Tuple[str, int]] = None,
    ) -> None:
        # smtplib.LMTP.connect() parameters
        self.host = host  # type: str
        self.port = port  # type: int
        self.local_hostname = local_hostname  # type: Optional[str]
        self.source_address = source_address  # type: Optional[Tuple[str, int]]

        # envelope recipient address (required). all mail is delivered to one single pre-defined recipient
        self.envelope_recipient = envelope_recipient  # type: str
        if not self.envelope_recipient or not isinstance(self.envelope_recipient, str):
            raise ValueError(f"envelope_recipient parameter is required. invalid recipient: {self.envelope_recipient}")

        # envelope sender address
        self.envelope_sender = envelope_sender  # type: str
        if not self.envelope_sender or not isinstance(self.envelope_sender, str):
            raise ValueError(f"invalid sender: {self.envelope_sender}")

        # LMTP client
        self.client = None  # type: Optional[smtplib.LMTP]

    def connect(self) -> None:
        if self.client is not None:
            logger.info("quitting leftover client")
            self.disconnect()

        logger.debug(f"connecting to {self.host}:{self.port}")
        try:
            self.client = smtplib.LMTP(
                host=self.host, port=self.port, local_hostname=self.local_hostname, source_address=self.source_address
            )
        except (smtplib.SMTPConnectError, smtplib.SMTPServerDisconnected) as err:
            raise MettmailDeliverConnectError(f"connection error: {err}")
        except smtplib.SMTPException as err:
            raise MettmailDeliverConnectError(f"smtp error: {err}")
        except OSError as err:
            raise MettmailDeliverConnectError(f"socket error: {err}")

        logger.trace("sending LHLO")
        try:
            self.client.ehlo()
        except smtplib.SMTPException as err:
            raise MettmailDeliverCommandFailed(f"LHLO failed: {err}")

    def disconnect(self) -> None:
        if self.client:
            logger.trace("sending quit")
            try:
                self.client.quit()
            except smtplib.SMTPException as err:
                logger.warning(f"quit failed: {err}")
                # proceed anyway
            else:
                logger.trace("quit ok")
                self.client = None
        else:
            logger.trace("already disconnected")

    def deliver_message(self, message: bytearray) -> bool:
        assert self.envelope_recipient
        assert self.envelope_sender
        if self.client is None:
            raise MettmailDeliverStateError("tried to deliver while client is not connected")

        from_addr = self.envelope_sender
        to_addr = self.envelope_recipient
        logger.debug(f"sending message: e_from=<{from_addr}> e_to=<{to_addr}> size={len(message)}")

        # send mail
        try:
            response = self.client.sendmail(from_addr=from_addr, to_addrs=to_addr, msg=message)
        except smtplib.SMTPRecipientsRefused as err:
            raise MettmailDeliverRecipientRefused(f"recipient refused: {err}")
        except smtplib.SMTPException as err:
            raise MettmailDeliverCommandFailed(f"smtp failure: {err}")
        except:  # noqa: E722
            # catch all exception and make sure we leave this function
            logger.exception("general exception while sending")  # make sure we get the backtrace
            raise MettmailDeliverCommandFailed("general smtp failure")

        logger.trace(f"sendmail response: {response}")
        assert isinstance(response, dict)
        if len(response) == 0:
            logger.trace("delivery successful")
            # Quote: https://docs.python.org/3/library/smtplib.html#smtplib.SMTP.sendmail
            # This method will return normally if the mail is accepted for at least one recipient. Otherwise it will
            # raise an exception. That is, if this method does not raise an exception, then someone should get your
            # mail. If this method does not raise an exception, it returns a dictionary, with one entry for each
            # recipient that was refused. Each entry contains a tuple of the SMTP error code and the accompanying
            # error message sent by the server.

            # -> if we get to this point, no exception has been raised and the response dictionary is empty,
            # indicating "no error"
            return True  # delivery successful
        else:
            raise MettmailDeliverCommandFailed(f"sending failed, server returned: {response}")
