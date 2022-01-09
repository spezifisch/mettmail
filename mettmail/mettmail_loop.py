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

from loguru import logger

from .exceptions import (
    MettmailDeliverException,
    MettmailFetchAuthenticationError,
    MettmailFetchException,
)
from .fetch_imap import FetchIMAP


@logger.catch
async def mettmail_loop(fetcher: FetchIMAP) -> bool:
    """Mettmail main loop that fetches mails as they arrive on IMAP and delivers them using LMTP.

    TODO: retry logic, on any problem we currently just raise an exception and bail."""
    logger.info("connecting")
    try:
        await fetcher.connect()
    except MettmailFetchAuthenticationError:
        logger.exception("login failed")
        return False
    except MettmailFetchException:
        logger.exception("connection failed")
        return False

    try:
        # initially fetch unflagged messages (and deliver them)
        logger.info("initial fetch")
        await fetcher.fetch_deliver_unflagged_messages()

        if not fetcher.has_idle():
            logger.warning("fetch complete, ending because we can't IDLE")
            return True

        # fetch/deliver new messages as they arrive
        logger.info("waiting for new messages")
        await fetcher.run_idle_loop()
    except MettmailFetchException:
        logger.exception("fetcher error")
        return False
    except MettmailDeliverException:
        logger.exception("deliverer error")
        return False

    return True
