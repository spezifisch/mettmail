#!/usr/bin/env python3
"""
This file is part of mettmail (https://github.com/spezifisch/mettmail).
Copyright (c) 2021-2022 spezifisch (https://github.com/spezifisch)

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
import sys

import click
from loguru import logger

from deliver_lmtp import DeliverLMTP
from exceptions import MettmailDeliverException, MettmailFetchAuthenticationError, MettmailFetchException
from fetch_imap import FetchIMAP


@logger.catch
async def mettmail_loop(fetcher: FetchIMAP) -> None:
    """Mettmail main loop that fetches mails as they arrive on IMAP and delivers them using LMTP.

    TODO: retry logic, on any problem we currently just raise an exception and bail."""
    logger.info("connecting")
    try:
        await fetcher.connect()
    except MettmailFetchAuthenticationError as err:
        logger.error(f"login failed: {err}")
        return
    except MettmailFetchException as err:
        logger.error(f"connection failed: {err}")
        return

    try:
        # initially fetch unflagged messages (and deliver them)
        logger.info("initial fetch")
        await fetcher.fetch_deliver_unflagged_messages()

        if not fetcher.has_idle():
            logger.warning("fetch complete, ending because we can't IDLE")
            return

        # fetch/deliver new messages as they arrive
        logger.info("waiting for new messages")
        await fetcher.run_idle_loop()
    except MettmailFetchException as err:
        logger.error(f"fetcher error: {err}")
        return
    except MettmailDeliverException as err:
        logger.error(f"deliverer error: {err}")
        return


@click.command()
@click.option("--debug", default=False, is_flag=True, help="Set loglevel to DEBUG")
@click.option("--trace", default=False, is_flag=True, help="Set loglevel to TRACE")
def run(debug: bool, trace: bool) -> None:
    logger.remove()
    if trace:
        logger.add(sys.stderr, level="TRACE")
    elif debug:
        logger.add(sys.stderr, level="DEBUG")
    else:
        logger.add(sys.stderr, level="INFO")

    # LMTP
    lmtp_host = "localhost"
    lmtp_port = 24
    lmtp_envelope_recipient = "rxa"
    deliverer = DeliverLMTP(host=lmtp_host, port=lmtp_port, envelope_recipient=lmtp_envelope_recipient)

    # IMAP
    imap_host = "localhost"
    imap_user = "foo"
    imap_password = "pass"
    fetcher = FetchIMAP(host=imap_host, user=imap_user, password=imap_password, deliverer=deliverer)

    # run mettmail_loop until an error occurs
    loop = asyncio.get_event_loop()
    task = mettmail_loop(fetcher)
    loop.run_until_complete(task)

    # cleanup
    logger.trace("cleanup")
    loop.run_until_complete(fetcher.disconnect())
    deliverer.disconnect()


if __name__ == "__main__":
    run()
