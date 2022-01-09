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

from strictyaml import Int, Map, Optional, Str

_imap_schema = Map(
    {
        "host": Str(),
        Optional("port"): Int(),
        Optional("user"): Str(),
        Optional("password"): Str(),
        Optional("mailbox"): Str(),
        Optional("timeout_connect"): Int(),
        Optional("timeout_idle_start"): Int(),
        Optional("timeout_idle_end"): Int(),
    }
)

_lmtp_schema = Map(
    {
        "host": Str(),
        Optional("port"): Int(),
        "envelope_recipient": Str(),
        Optional("envelope_sender"): Str(),
        Optional("local_hostname"): Str(),
    }
)

MettmailSchema = Map({"imap": _imap_schema, "lmtp": _lmtp_schema})
