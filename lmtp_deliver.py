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
import sys

from loguru import logger


async def deliver_message(message: bytearray) -> bool:
    return False


@logger.catch
async def lmtp_test(host, port) -> None:
    msg = bytearray(
        b"From: noreply.foo@mailgen.example.com\r\nTo: foo@testcot\r\nSubject: test mail 1641157914 to foo\r\nDate: Sun, 02 Jan 2022 21:11:54 +0000\r\n\r\nthis is content\r\n"
    )
    ok = await deliver_message(msg)
    logger.info("ok", ok)


if __name__ == "__main__":
    logger.remove()
    logger.add(sys.stderr, level="TRACE")

    loop = asyncio.get_event_loop()
    loop.run_until_complete(lmtp_test("localhost", 24))
