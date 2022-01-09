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


# Base exception for everything we raise
class MettmailException(Exception):
    pass


# Base Fetch exception
class MettmailFetchException(MettmailException):
    pass


# * Fetch exceptions...
class MettmailFetchAbort(MettmailFetchException):
    pass


class MettmailFetchTimeoutError(MettmailFetchException):
    pass


class MettmailFetchAuthenticationError(MettmailFetchException):
    pass


class MettmailFetchFeatureUnsupported(MettmailFetchException):
    pass


class MettmailFetchUnexpectedResponse(MettmailFetchException):
    pass


class MettmailFetchInconsistentResponse(MettmailFetchException):
    pass


class MettmailFetchCommandFailed(MettmailFetchException):
    pass


class MettmailFetchStateError(MettmailFetchException):
    pass


# Base Deliver exception
class MettmailDeliverException(MettmailException):
    pass


# * Deliver exceptions...
class MettmailDeliverConnectError(MettmailDeliverException):
    pass


class MettmailDeliverInconsistentResponse(MettmailDeliverException):
    pass


class MettmailDeliverCommandFailed(MettmailDeliverException):
    pass


class MettmailDeliverRecipientRefused(MettmailDeliverException):
    pass


class MettmailDeliverStateError(MettmailDeliverException):
    pass
