"""
This file is part of mettmail (https://github.com/spezifisch/mettmail).
Based on imap_fetch.py of https://github.com/bamthomas/aioimaplib
Copyright (c) 2021-2022 spezifisch (https://github.com/spezifisch)
Copyright (c) 2021      Bruno Thomas (https://github.com/bamthomas)

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
import re
from typing import List, Optional

import aioimaplib
from loguru import logger

from deliver_base import DeliverBase
from exceptions import *

FETCH_MESSAGE_DATA_FLAGS = re.compile(rb".*FLAGS \((?P<flags>.*?)\).*")
FETCH_MESSAGE_DATA_SIZE = re.compile(rb".*RFC822.SIZE (?P<size>\d+).*")

CUSTOM_FLAG_FETCHED = "MettmailFetched"
bCUSTOM_FLAG_FETCHED = CUSTOM_FLAG_FETCHED.encode()


class FetchImap:
    def __init__(self, **kwargs) -> None:
        self.host = kwargs["host"]  # type: str
        self.port = kwargs.get("port", 993)  # type: int
        self.account = {
            "user": kwargs.get("user"),
            "password": kwargs.get("password"),
            "mailbox": kwargs.get("mailbox", "INBOX"),
        }
        self.deliverer = kwargs["deliverer"]  # type: DeliverBase

        self.client = None  # type: Optional[aioimaplib.IMAP4_SSL]

    async def connect(self) -> None:
        """Connect to IMAP server and login.

        Raises a MettmailFetch exception if anything fails.
        Login and mailbox selection was successful if no exception is raised."""
        logger.info(f"connecting to {self.host}")
        self.client = aioimaplib.IMAP4_SSL(host=self.host, timeout=30)

        logger.trace("waiting for hello")
        try:
            await self.client.wait_hello_from_server()  # returns None
        except TimeoutError as e:
            raise MettmailFetchConnectError(f"hello timeout: {e}")

        logger.trace("logging in")
        try:
            response = await self.client.login(self.account["user"], self.account["password"])
        except TimeoutError as e:
            raise MettmailFetchConnectError(f"login timeout: {e}")
        if response.result != "OK":
            raise MettmailFetchAuthenticationError(f"login error: {response}")

        logger.trace("selecting mailbox")
        try:
            response = await self.client.select(self.account["mailbox"])
        except TimeoutError as e:
            raise MettmailFetchConnectError(f"select timeout: {e}")
        if response.result != "OK":
            raise MettmailFetchCommandFailed(f"select error: {response}")
        select_response = response

        # TODO check if \* is in PERMANENTFLAGS: https://datatracker.ietf.org/doc/html/rfc3501#page-64

        logger.info(f"connected to {self.host}")
        logger.trace(f"server capabilities: {self.client.protocol.capabilities}")
        logger.trace(f"select response: {select_response}")
        if not self.client.has_capability("IDLE"):
            logger.warn("server doesn't support IDLE")

        # uncomment for testing purposes to quickly remove our flag from all messages
        # await self.client.uid("store", "1:*", f"-FLAGS.SILENT ({CUSTOM_FLAG_FETCHED})")

    def disconnect(self) -> None:
        if self.client:
            self.client.logout()

    async def run_idle_loop(self) -> None:
        logger.info("ready for new messages")
        while True:
            logger.debug("-> enter IDLE")
            idle_task = await self.client.idle_start(timeout=60)

            # wait for new messages
            new_uids = []  # type: List[int]
            msgs = await self.client.wait_server_push()
            for msg in msgs:
                if msg.endswith(b"EXISTS"):
                    uid = int(msg.split(b" ", 1)[0])
                    logger.debug(f"(push) new message: {uid}")
                    new_uids.append(uid)
                elif msg.endswith(b"RECENT"):
                    logger.trace(f"(push) new recent count: {msg}")
                elif msg.endswith(b"EXPUNGE"):
                    logger.trace(f"(push) message removed: {msg}")
                elif b"FETCH" in msg and b"\Seen" in msg:
                    logger.trace(f"(push) message seen {msg}")
                else:
                    logger.trace(f"(push) unprocessed message: {msg}")

            # end idle mode to fetch messages
            self.client.idle_done()
            await asyncio.wait_for(idle_task, timeout=5)
            logger.debug("<- ending IDLE")

            # process new messages
            if len(new_uids):
                logger.debug(f"got {len(new_uids)} new messages")

                # NOTE there isn't any retry logic implemented yet
                self.deliverer.connect()  # raises MettmailDeliverExceptions on failure

                for uid in new_uids:
                    await self.fetch_deliver_message(uid)  # raises MettmailExceptions on failure

                self.deliverer.disconnect()  # doesn't raise

    async def fetch_deliver_unflagged_messages(self) -> None:
        """Fetch and process all unfetched messages in folder.

        We use IMAP SEARCH to get a list of mail UIDs missing the MettmailFetched flag.
        These mails are fetched and processed by `fetch_deliver_mark_message()`.

        Currently this function raises exceptions on any failure and stops processing further mails, but in a
        fail-safe way so that it is guaranteed that only MettmailFetched-flagged messages have been delivered to their
        target.
        """
        logger.trace(f"fetching non-tagged mails")

        response = await self.client.uid_search(f"UNKEYWORD {CUSTOM_FLAG_FETCHED}")
        if response.result != "OK":
            raise MettmailFetchCommandFailed(f"search failed: {response}")

        # sanity checks
        if len(response.lines) != 2:
            raise MettmailFetchParserError(f"expected 2 lines, got response: {response}")

        if not response.lines[-1].lower().startswith(b"search completed"):
            raise MettmailFetchUnexpectedResponse(f"expected completed string, got response: {response}")

        # fetch all returned message uids
        if len(response.lines[0]):
            self.deliverer.connect()  # raises MettmailDeliverExceptions on failure

            for uid in response.lines[0].split(b" "):
                uid = int(uid)
                await self.fetch_deliver_message(uid)  # raises MettmailExceptions on failure

            self.deliverer.disconnect()  # doesn't raise
        else:
            logger.debug(f"no new messages")

    async def fetch_deliver_message(self, uid: int) -> None:
        """Fetch mail with given UID, deliver it to the destination, and mark the mail as fetched.

        We use IMAP FETCH to get the mail. Its flags are checked in case it's a newly added mail that already contains our
        MettmailFetched flag (it might have been moved back and forth by another IMAP session).

        The message is delivered to the destination server by `deliver_message()`. Only if this is successful we set the
        flag to indicate the message has been fetched.
        """
        logger.debug(f"-> fetching message {uid}")

        response = await self.client.uid("fetch", str(uid), "(FLAGS RFC822.SIZE BODY.PEEK[])")
        if response.result != "OK":
            raise MettmailFetchCommandFailed(f"fetch failed: {response}")

        # sanity checks
        if len(response.lines) != 4:
            raise MettmailFetchParserError(f"expected 3 lines, got {len(response.lines)} in response: {response}")

        if not response.lines[-1].lower().startswith(b"fetch completed"):
            raise MettmailFetchUnexpectedResponse(f"expected completed string, got response: {response}")

        # parse response
        fetch_command_without_literal = b"%s %s" % (response.lines[0], response.lines[2])
        logger.trace(f"command: {fetch_command_without_literal}")
        try:
            # check flags (new messages might be added to the mailbox that already have the "..fetched" flag)
            flags = FETCH_MESSAGE_DATA_FLAGS.match(fetch_command_without_literal).group("flags")
            if bCUSTOM_FLAG_FETCHED in flags.split(b" "):
                logger.debug(f"-> done with message {uid}, skipping because already flagged")
                return

            # get reported message size
            size = int(FETCH_MESSAGE_DATA_SIZE.match(fetch_command_without_literal).group("size"))
        except (AttributeError, ValueError):
            raise MettmailFetchParserError(f"got response: {response}")

        # sanity check for message size
        if size != len(response.lines[1]):
            raise MettmailFetchInconsistentResponse(f"expected message size {size}, got {len(response.lines[1])}")

        # deliver message
        msg = response.lines[1]
        ok = False
        try:
            ok = self.deliverer.deliver_message(msg)
        except MettmailDeliverException:
            logger.exception("deliverer failed")
            ok = False

        if ok:
            # set fetched flag only on successful delivery (no exception + returned True)
            await self.set_fetched_flag(uid)

        logger.debug(f"-> done with message {uid}")

    async def set_fetched_flag(self, message_uid: int) -> None:
        """Mark mail with given UID as fetched."""
        response = await self.client.uid("store", str(message_uid), f"+FLAGS.SILENT ({CUSTOM_FLAG_FETCHED})")
        if response.result != "OK":
            raise MettmailFetchCommandFailed(f"failed marking uid {message_uid} fetched: {response}")

        if len(response.lines) != 1:
            raise MettmailFetchParserError(f"expected one line, got {len(response.lines)} in response: {response}")

        if not response.lines[-1].lower().startswith(b"store completed"):
            raise MettmailFetchUnexpectedResponse(f"expected completed string, got response: {response}")

    def has_idle(self) -> bool:
        return self.client and self.client.has_capability("IDLE")


@logger.catch
async def imap_loop(host: str, user: str, password: str, deliverer: DeliverBase) -> None:
    fetcher = FetchImap(host=host, user=user, password=password, deliverer=deliverer)
    await fetcher.connect()

    # initially fetch unflagged messages (and deliver them)
    await fetcher.fetch_deliver_unflagged_messages()

    if not fetcher.has_idle():
        logger.warn("fetch complete, ending because we can't IDLE")
        fetcher.disconnect()
        return

    # fetch/deliver new messages as they arrive
    await fetcher.run_idle_loop()
