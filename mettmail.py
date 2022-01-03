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

from fetch_imap import imap_loop


@click.command()
@click.option("--debug", default=False, is_flag=True, help="Set loglevel to DEBUG")
@click.option("--trace", default=False, is_flag=True, help="Set loglevel to TRACE")
def run(debug, trace):
    logger.remove()
    if trace:
        logger.add(sys.stderr, level="TRACE")
    elif debug:
        logger.add(sys.stderr, level="DEBUG")
    else:
        logger.add(sys.stderr, level="INFO")

    loop = asyncio.get_event_loop()
    loop.run_until_complete(imap_loop("localhost", "foo", "pass"))


if __name__ == "__main__":
    run()
