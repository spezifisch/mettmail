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
import time
from typing import List, Optional

import aioimaplib
from loguru import logger

from .deliver_base import DeliverBase
from .exceptions import (
    MettmailDeliverException,
    MettmailFetchAbort,
    MettmailFetchAuthenticationError,
    MettmailFetchCommandFailed,
    MettmailFetchFeatureUnsupported,
    MettmailFetchInconsistentResponse,
    MettmailFetchStateError,
    MettmailFetchTimeoutError,
    MettmailFetchUnexpectedResponse,
)

SELECT_PERMANENTFLAGS = re.compile(rb".*PERMANENTFLAGS \((?P<permanent_flags>.*?)\).*")
FETCH_MESSAGE_DATA_FLAGS = re.compile(rb".*FLAGS \((?P<flags>.*?)\).*")
FETCH_MESSAGE_DATA_SIZE = re.compile(rb".*RFC822.SIZE (?P<size>\d+).*")

CUSTOM_FLAG_FETCHED = "MettmailFetched"
bCUSTOM_FLAG_FETCHED = CUSTOM_FLAG_FETCHED.encode()


class FetchIMAP:
    def __init__(
        self,
        host: str,
        deliverer: DeliverBase,
        port: int = aioimaplib.IMAP4_SSL_PORT,
        user: str = "",
        password: str = "",
        mailbox: str = "INBOX",
        timeout_connect: int = 30,
        timeout_idle_start: int = 60,
        timeout_idle_end: int = 5,
    ) -> None:
        self.host = host  # type: str
        self.port = port  # type: int
        self.account = {
            "user": user,
            "password": password,
            "mailbox": mailbox,
        }
        self.deliverer = deliverer  # type: DeliverBase

        self.client = None  # type: Optional[aioimaplib.IMAP4_SSL]
        self.timeout_connect = timeout_connect
        self.timeout_idle_start = timeout_idle_start
        self.timeout_idle_end = timeout_idle_end

    async def connect(self) -> None:
        """Connect to IMAP server and login.

        Raises a MettmailFetch exception if anything fails.
        Login and mailbox selection was successful if no exception is raised.
        """
        logger.debug(f"connecting to {self.host}")
        self.client = aioimaplib.IMAP4_SSL(
            host=self.host, port=self.port, timeout=self.timeout_connect
        )  # doesn't raise

        logger.trace("waiting for hello")
        try:
            await self.client.wait_hello_from_server()  # returns None
            # NOTE aioimaplib doesn't catch OSErrors like socket.gaierror, not sure if this is my problem or theirs.
            # currently this just leads to a timeouterror here.
        except asyncio.TimeoutError:
            raise MettmailFetchTimeoutError("hello timeout")

        logger.trace("logging in")
        try:
            response = await self.client.login(self.account["user"], self.account["password"])
        except asyncio.TimeoutError:
            raise MettmailFetchTimeoutError("login timeout")
        if response.result != "OK":
            raise MettmailFetchAuthenticationError(f"login error: {response}")

        logger.trace("selecting mailbox")
        try:
            response = await self.client.select(self.account["mailbox"])
        except asyncio.TimeoutError:
            raise MettmailFetchTimeoutError("select timeout")
        if response.result != "OK":
            raise MettmailFetchCommandFailed(f"select error: {response}")
        select_response = response

        if not self.is_permanentflag_supported(select_response, b"\\*"):
            msg = "server doesn't support custom FLAGS. these are required for mettmail to work."
            raise MettmailFetchFeatureUnsupported(msg)

        logger.info(f"connected to {self.host}")
        logger.trace(f"server capabilities: {self.client.protocol.capabilities}")
        logger.trace(f"select response: {select_response}")
        if not self.has_idle():
            logger.warning("server doesn't support IDLE command")

        # uncomment for testing purposes to quickly remove our flag from all messages
        # await self.client.uid("store", "1:*", f"-FLAGS.SILENT ({CUSTOM_FLAG_FETCHED})")

    async def disconnect(self) -> bool:
        """Close IMAP connection."""
        if self.client:
            logger.trace("logging out")
            try:
                response = await self.client.logout()
            except asyncio.TimeoutError:
                logger.trace("ignoring timeout while trying to logout")
            except aioimaplib.aioimaplib.Abort:
                logger.trace("ignoring error while trying to logout")
            else:
                if response.result != "OK":
                    logger.debug(f"ignoring error trying to logout: {response}")
                else:
                    logger.trace("logged out")

            self.client = None
        else:
            logger.trace("already logged out")

        return True

    async def run_idle_loop(self) -> None:
        """Run loop waiting for mails and delivering them as they arrive."""
        # run until step function decides to stop (i.e. immediately for stubbed out unit tests)
        running = True
        while running:
            running = await self.idle_loop_step()

    async def idle_loop_step(self) -> bool:
        """Single loop step waiting for mails and delivering them as they arrive.

        Returns True if the loop should keep running."""
        if self.client is None:
            raise MettmailFetchStateError("called without being connected")

        logger.debug("-> enter IDLE")
        try:
            idle_task = await self.client.idle_start(
                timeout=self.timeout_idle_start
            )  # doesn't raise except for Abort and asyncio.TimeoutError
        except asyncio.TimeoutError:
            raise MettmailFetchTimeoutError("idle start timeout")
        except aioimaplib.Abort:
            raise MettmailFetchAbort("idle start abort")

        # wait for new messages
        new_uids = []  # type: List[int]
        try:
            msgs = await self.client.wait_server_push()
        except asyncio.TimeoutError:
            # time to restart IDLE: https://www.imapwiki.org/ClientImplementation/Synchronization
            logger.debug("leaving idle after timeout")
        else:
            # parse messages
            for msg in msgs:
                if msg.endswith(b"EXISTS"):
                    # new mails have arrived
                    uid = int(msg.split(b" ", 1)[0])
                    logger.debug(f"(push) new message: {uid}")
                    new_uids.append(uid)
                elif msg.endswith(b"RECENT"):
                    logger.trace(f"(push) new recent count: {msg}")
                else:
                    logger.trace(f"(push) unprocessed message: {msg}")

        # end idle mode (to fetch messages or because 29mins are over)
        self.client.idle_done()
        try:
            await asyncio.wait_for(idle_task, timeout=self.timeout_idle_end)  # raises asyncio.TimeoutError
        except asyncio.TimeoutError:
            raise MettmailFetchTimeoutError("idle end timeout")
        logger.debug("<- ending IDLE")

        # process new messages if any
        if len(new_uids):
            logger.debug(f"got {len(new_uids)} new messages")

            # NOTE there isn't any retry logic implemented yet
            self.deliverer.connect()  # raises MettmailDeliverExceptions on failure

            for uid in new_uids:
                await self.fetch_deliver_message(uid)  # raises MettmailExceptions on failure

            self.deliverer.disconnect()  # doesn't raise

        return True

    async def fetch_deliver_unflagged_messages(self) -> None:
        """Fetch and process all unfetched messages in folder.

        We use IMAP SEARCH to get a list of mail UIDs missing the MettmailFetched flag.
        These mails are fetched and processed by `fetch_deliver_mark_message()`.

        Currently this function raises exceptions on any failure and stops processing further mails, but in a
        fail-safe way so that it is guaranteed that only MettmailFetched-flagged messages have been delivered to their
        target.
        """
        if self.client is None:
            raise MettmailFetchStateError("called without being connected")

        logger.trace("fetching unflagged mails")
        try:
            response = await self.client.uid_search(f"UNKEYWORD {CUSTOM_FLAG_FETCHED}")
        except asyncio.TimeoutError:
            raise MettmailFetchTimeoutError("search timeout")
        if response.result != "OK":
            raise MettmailFetchCommandFailed(f"search failed: {response}")

        # sanity checks
        if len(response.lines) != 2:
            raise MettmailFetchUnexpectedResponse(f"expected 2 lines, got response: {response}")

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
            logger.debug("no new messages")

    async def fetch_deliver_message(self, uid: int) -> None:
        """Fetch mail with given UID, deliver it to the destination, and mark the mail as fetched.

        We use IMAP FETCH to get the mail. Its flags are checked in case it's a newly added mail that already contains
        our MettmailFetched flag (it might have been moved back and forth by another IMAP session).

        The message is delivered to the destination server by `deliver_message()`. Only if this is successful we set the
        flag to indicate the message has been fetched.
        """
        if self.client is None:
            raise MettmailFetchStateError("called without being connected")

        logger.debug(f"-> fetching message {uid}")
        start_time = time.time()

        # get mail
        try:
            response = await self.client.uid("fetch", str(uid), "(FLAGS RFC822.SIZE BODY.PEEK[])")
        except asyncio.TimeoutError:
            raise MettmailFetchTimeoutError("fetch timeout")
        if response.result != "OK":
            raise MettmailFetchCommandFailed(f"fetch failed: {response}")

        # sanity checks
        if len(response.lines) != 4:
            raise MettmailFetchUnexpectedResponse(
                f"expected 4 lines, got {len(response.lines)} in response: {response}"
            )

        if not response.lines[-1].lower().startswith(b"fetch completed"):
            raise MettmailFetchUnexpectedResponse(f"expected completed string, got response: {response}")

        # parse response
        fetch_command_without_literal = b"%s %s" % (response.lines[0], response.lines[2])
        logger.trace(f"command: {fetch_command_without_literal!r}")
        try:
            # check flags (new messages might be added to the mailbox that already have the "..fetched" flag)
            match = FETCH_MESSAGE_DATA_FLAGS.match(fetch_command_without_literal)
            assert match is not None
            flags = match.group("flags")
            if bCUSTOM_FLAG_FETCHED.lower() in flags.lower().split(b" "):
                logger.debug(f"-> done with message {uid}, skipping because already flagged")
                return

            # get reported message size
            match = FETCH_MESSAGE_DATA_SIZE.match(fetch_command_without_literal)
            assert match is not None
            size = int(match.group("size"))
        except AssertionError:
            raise MettmailFetchUnexpectedResponse(f"got response: {response}")

        # sanity check for message size
        if size != len(response.lines[1]):
            raise MettmailFetchInconsistentResponse(f"expected message size {size}, got {len(response.lines[1])}")

        # deliver message
        msg = response.lines[1]
        ok = False
        try:
            ok = self.deliverer.deliver_message(msg)
        except MettmailDeliverException:
            # just to show this is intentional
            logger.error(f"failed delivering message uid={uid}")
            raise

        # set flag
        if ok:
            # set fetched flag only on successful delivery (no exception + returned True)
            await self.set_fetched_flag(
                uid
            )  # TODO how should we do error handling here? we can't un-deliver the mail.
        else:
            # should never happen
            raise MettmailFetchStateError("delivery was not ok but no exception was raised")

        # done
        end_time = time.time()
        duration = end_time - start_time
        logger.info(f"delivered message {uid} ({size} Bytes) in {duration:.3f} s")
        logger.debug(f"<- done with message {uid}")

    async def set_fetched_flag(self, message_uid: int) -> None:
        """Mark mail with given UID as fetched."""
        if self.client is None:
            raise MettmailFetchStateError("called without being connected")

        try:
            response = await self.client.uid("store", str(message_uid), f"+FLAGS.SILENT ({CUSTOM_FLAG_FETCHED})")
        except asyncio.TimeoutError:
            raise MettmailFetchTimeoutError("store timeout")
        if response.result != "OK":
            raise MettmailFetchCommandFailed(f"failed marking uid {message_uid} fetched: {response}")

        if len(response.lines) != 1:
            raise MettmailFetchUnexpectedResponse(
                f"expected one line, got {len(response.lines)} in response: {response}"
            )

        if not response.lines[-1].lower().startswith(b"store completed"):
            raise MettmailFetchUnexpectedResponse(f"expected completed string, got response: {response}")

    def has_idle(self) -> bool:
        return self.client is not None and self.client.has_capability("IDLE")

    @staticmethod
    def is_permanentflag_supported(response: aioimaplib.Response, wanted_flag: bytes) -> bool:
        """Check if the given SELECT Response contains the wanted PERMANENTFLAGS.

        This is used to check if the special flag \\* (backslash asterisk) is present which indicated that the client
        can create custom message flags. Mettmail uses this feature to mark messages which have been delivered.
        Dovecot supports this feature.

        See: https://datatracker.ietf.org/doc/html/rfc3501#page-64
        """

        big_line = b"".join(response.lines)
        match = SELECT_PERMANENTFLAGS.match(big_line)
        if not match:
            logger.trace("regex didn't match")
            return False

        supported_pflags = match.group("permanent_flags").split(b" ")
        logger.trace(f"supported_pflags={supported_pflags}")
        return wanted_flag in supported_pflags
