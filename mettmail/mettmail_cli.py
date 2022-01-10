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
import strictyaml
from loguru import logger

import mettmail.mettmail_loop

from .config_schema import MettmailSchema
from .deliver_lmtp import DeliverLMTP
from .fetch_imap import FetchIMAP


@click.command()
@click.option("--config", default="mettmail.yaml", help="Config file")
@click.option(
    "--debug", default=False, is_flag=True, help="Set loglevel to DEBUG (may show sensitive data in exceptions)"
)
@click.option("--trace", default=False, is_flag=True, help="Set loglevel to TRACE (may show sensitive data)")
def run(config: str, debug: bool, trace: bool) -> None:
    logger.remove()
    if trace:
        # print pretty much every call
        logger.add(sys.stderr, level="TRACE")
    elif debug:
        # print full backtraces and other stuff
        logger.add(sys.stderr, level="DEBUG")
    else:
        # don't print full backtraces which may include mail content
        logger.add(sys.stderr, level="INFO", diagnose=False, backtrace=False)

    # load config file
    try:
        args = strictyaml.load(open(config, "r").read(), schema=MettmailSchema, label=config)
    except OSError as err:
        logger.error(f"couldn't load config file: {err}")
        sys.exit(1)
    except strictyaml.YAMLError as err:
        logger.error(f"config file parsing error:\n{err}")
        sys.exit(1)

    # LMTP
    deliverer = DeliverLMTP(**args.data["lmtp"])

    # IMAP
    fetcher = FetchIMAP(**args.data["imap"], deliverer=deliverer)

    # run mettmail_loop until an error occurs
    loop = asyncio.get_event_loop()
    task = loop.create_task(mettmail.mettmail_loop.mettmail_loop(fetcher))
    done, _ = loop.run_until_complete(asyncio.wait({task}))
    return_code = 1
    if len(done) and done.pop().result() is True:
        return_code = 0

    # cleanup
    logger.trace("cleanup")
    task = loop.create_task(fetcher.disconnect())
    loop.run_until_complete(asyncio.wait({task}))
    deliverer.disconnect()

    sys.exit(return_code)


if __name__ == "__main__":
    run()
