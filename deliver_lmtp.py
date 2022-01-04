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


import asyncio
import smtplib
import sys
from typing import Optional

from loguru import logger

from deliver_base import DeliverBase
from exceptions import (
    MettmailDeliverCommandFailed,
    MettmailDeliverConnectError,
    MettmailDeliverException,
    MettmailDeliverInconsistentResponse,
)


class DeliverLMTP(DeliverBase):
    # Default envelope sender address if not specified in constructor parameters.
    # This address is used only for the mail envelope. Not to be confused with the RFC822 "From" header.
    # It might be recorded by the receiving mailserver in a RFC822 header like "X-Envelope-From", but otherwise its
    # value should be irrelevant.
    DEFAULT_SENDER = "mettmail@localhost"

    def __init__(self, **kwargs) -> None:
        # smtplib.LMTP.connect() parameters
        self.host = kwargs["host"]  # type: str
        self.port = kwargs.get("port", None)  # type: Optional[int]
        self.local_hostname = kwargs.get("local_hostname", None)  # type: Optional[str]
        self.source_address = kwargs.get("source_address", None)  # type: Optional[str]

        # envelope recipient address (required). all mail is delivered to one single pre-defined recipient
        self.envelope_recipient = kwargs.get("envelope_recipient")  # type: str
        if not self.envelope_recipient or not isinstance(self.envelope_recipient, str):
            raise ValueError(f"envelope_recipient parameter is required. invalid recipient: {self.envelope_recipient}")

        # envelope sender address
        self.envelope_sender = kwargs.get("envelope_sender", self.DEFAULT_SENDER)  # type: str
        if not self.envelope_sender or not isinstance(self.envelope_sender, str):
            raise ValueError(f"invalid sender: {self.envelope_sender}")

        # LMTP client
        self.client = None  # type: Optional[smtplib.LMTP]

    def connect(self) -> None:
        if self.client is not None:
            logger.info("quitting leftover client")
            try:
                self.client.quit()
            except smtplib.SMTPException:
                logger.exception("tried to close still open client")
            self.client = None

        logger.debug(f"connecting to {self.host}:{self.port}")
        try:
            self.client = smtplib.LMTP(
                host=self.host, port=self.port, local_hostname=self.local_hostname, source_address=self.source_address
            )
        except (smtplib.SMTPConnectError, smtplib.SMTPServerDisconnected):
            err = "connection terminated"
            logger.exception(err)
            raise MettmailDeliverConnectError(err)
        except smtplib.SMTPException:
            err = "could not connect"
            logger.exception(err)
            raise MettmailDeliverConnectError(err)

        logger.trace("sending LHLO")
        try:
            self.client.ehlo()
        except smtplib.SMTPHeloError:
            err = "server refused LHLO"
            logger.exception(err)
            raise MettmailDeliverCommandFailed(err)

    def disconnect(self) -> None:
        if self.client is None:
            return

        try:
            self.client.quit()
        except smtplib.SMTPException:
            logger.exception("tried to close still open client")
            # proceed anyway

        self.client = None

    def deliver_message(self, message: bytearray) -> bool:
        from_addr = self.envelope_sender
        to_addr = self.envelope_recipient
        logger.debug(f"sending message with size {len(message)} from=<{from_addr}> to=<{to_addr}>")

        # send mail
        try:
            response = self.client.sendmail(from_addr=from_addr, to_addrs=to_addr, msg=message)
        except smtplib.SMTPException:
            err = "smtp failure while sending"
            logger.exception(err)
            raise MettmailDeliverCommandFailed(err)
        except:
            # catch all exception and make sure we leave this function
            err = "general exception while sending"
            logger.exception(err)
            raise MettmailDeliverCommandFailed(err)

        logger.trace(f"sendmail response: {response}")
        # sanity check
        if not isinstance(response, dict):
            raise MettmailDeliverInconsistentResponse("not a dict")

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


@logger.catch
async def lmtp_test(host, port, recipient) -> bool:
    msg = bytearray(
        b"From: noreply.foo@mailgen.example.com\r\nTo: foo@testcot\r\nSubject: test mail 1641157914 to foo\r\nDate: Sun, 02 Jan 2022 21:11:54 +0000\r\n\r\nthis is content\r\n"
    )

    lmtp = DeliverLMTP(host=host, port=port, envelope_recipient=recipient)
    try:
        lmtp.connect()
    except MettmailDeliverException:
        logger.exception("failed connecting to deliver mail")
        return False

    delivery_ok = False

    try:
        delivery_ok = lmtp.deliver_message(msg)
    except MettmailDeliverException:
        logger.exception("failed delivering mail")
    finally:
        logger.info(f"delivery_ok={delivery_ok}")

    lmtp.disconnect()

    return delivery_ok


if __name__ == "__main__":
    logger.remove()
    logger.add(sys.stderr, level="TRACE")

    loop = asyncio.get_event_loop()
    loop.run_until_complete(lmtp_test("localhost", 24, "rxa"))
