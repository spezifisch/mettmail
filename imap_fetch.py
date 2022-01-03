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
from typing import List

import aioimaplib
from loguru import logger

from exceptions import *


FETCH_MESSAGE_DATA_FLAGS = re.compile(rb".*FLAGS \((?P<flags>.*?)\).*")
FETCH_MESSAGE_DATA_SIZE = re.compile(rb".*RFC822.SIZE (?P<size>\d+).*")

CUSTOM_FLAG_FETCHED = "MettmailFetched"
bCUSTOM_FLAG_FETCHED = CUSTOM_FLAG_FETCHED.encode()


async def deliver_message(message: bytearray) -> bool:
    return False


async def fetch_messages_flags(imap_client: aioimaplib.IMAP4_SSL) -> None:
    """Fetch and process all unfetched messages in folder.

    We use IMAP SEARCH to get a list of mail UIDs missing the MettmailFetched flag.
    These mails are fetched and processed by `fetch_deliver_mark_message()`.
    """
    logger.trace(f"fetching non-tagged mails")

    response = await imap_client.uid_search(f"UNKEYWORD {CUSTOM_FLAG_FETCHED}")
    if response.result != "OK":
        raise MettmailFetchCommandFailed(f"search failed: {response}")

    # sanity checks
    if len(response.lines) != 2:
        raise MettmailFetchParserError(f"expected 2 lines, got response: {response}")

    if not response.lines[-1].lower().startswith(b"search completed"):
        raise MettmailFetchUnexpectedResponse(f"expected completed string, got response: {response}")

    # fetch all returned message uids
    if len(response.lines[0]):
        for uid in response.lines[0].split(b" "):
            uid = int(uid)
            await fetch_deliver_mark_message(imap_client, uid)
    else:
        logger.debug(f"no new messages")


async def fetch_deliver_mark_message(imap_client: aioimaplib.IMAP4_SSL, uid: int) -> None:
    """Fetch mail with given UID, deliver it to the destination, and mark the mail as fetched.

    We use IMAP FETCH to get the mail. Its flags are checked in case it's a newly added mail that already contains our
    MettmailFetched flag (it might have been moved back and forth by another IMAP session).

    The message is delivered to the destination server by `deliver_message()`. Only if this is successful we set the
    flag to indicate the message has been fetched.
    """
    logger.debug(f"-> fetching message {uid}")

    response = await imap_client.uid("fetch", str(uid), "(FLAGS RFC822.SIZE BODY.PEEK[])")
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

    # handle message
    msg = response.lines[1]
    ok = await deliver_message(msg)

    if ok:
        # set fetched flag
        await mark_mail_fetched(imap_client, uid)

    logger.debug(f"-> done with message {uid}")


async def mark_mail_fetched(imap_client: aioimaplib.IMAP4_SSL, uid: int) -> None:
    """Mark mail with given UID as fetched."""
    response = await imap_client.uid("store", str(uid), f"+FLAGS.SILENT ({CUSTOM_FLAG_FETCHED})")
    if response.result != "OK":
        raise MettmailFetchCommandFailed(f"failed marking uid {uid} fetched: {response}")

    if len(response.lines) != 1:
        raise MettmailFetchParserError(f"expected one line, got {len(response.lines)} in response: {response}")

    if not response.lines[-1].lower().startswith(b"store completed"):
        raise MettmailFetchUnexpectedResponse(f"expected completed string, got response: {response}")


@logger.catch
async def imap_loop(host, user, password) -> None:
    logger.info(f"connecting to {host}")
    imap_client = aioimaplib.IMAP4_SSL(host=host, timeout=30)
    logger.trace("waiting for hello")
    await imap_client.wait_hello_from_server()
    logger.trace("logging in")
    await imap_client.login(user, password)

    logger.trace("selecting mailbox")
    response = await imap_client.select("INBOX")
    logger.trace(f"select response: {response}")
    # TODO check if \* is in PERMANENTFLAGS: https://datatracker.ietf.org/doc/html/rfc3501#page-64

    logger.info(f"connected to {host}")

    logger.trace(f"server capabilities: {imap_client.protocol.capabilities}")
    if not imap_client.has_capability("IDLE"):
        logger.warn("server doesn't support IDLE")

    # uncomment for testing purposes to quickly remove our flag from all messages
    # await imap_client.uid("store", "1:*", f"-FLAGS.SILENT ({CUSTOM_FLAG_FETCHED})")

    # initially fetch unflagged messages
    await fetch_messages_flags(imap_client)

    if not imap_client.has_capability("IDLE"):
        logger.warn("fetch complete, ending because we can't IDLE")
        imap_client.logout()
        return

    # IDLE loop
    logger.info("ready for new messages")
    while True:
        logger.debug("-> enter IDLE")
        idle_task = await imap_client.idle_start(timeout=60)

        # wait for new messages
        new_uids = []  # type: List[int]
        msgs = await imap_client.wait_server_push()
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
        imap_client.idle_done()
        await asyncio.wait_for(idle_task, timeout=5)
        logger.debug("<- ending IDLE")

        # process new messages
        if len(new_uids):
            logger.debug(f"got {len(new_uids)} new messages")
            for uid in new_uids:
                await fetch_deliver_mark_message(imap_client, uid)
