# This file is part of mettmail (https://github.com/spezifisch/mettmail).
# Copyright (c) 2022 spezifisch (https://github.com/spezifisch)

# This program is free software: you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation, version 3 of the License.

# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU General Public License for more details.

# You should have received a copy of the GNU General Public License
# along with this program.  If not, see <http://www.gnu.org/licenses/>.

FROM python:3.9.9-slim AS base

LABEL org.opencontainers.image.authors="spezifisch"
LABEL org.opencontainers.image.url="https://github.com/spezifisch/mettmail"
LABEL org.opencontainers.image.source="https://github.com/spezifisch/mettmail"
LABEL org.opencontainers.image.licenses="GPL-3.0-only"

ENV PYTHONFAULTHANDLER=1 \
    PYTHONUNBUFFERED=1 \
    PYTHONHASHSEED=random

FROM base AS builder

ARG PIP_NO_CACHE_DIR=off \
    PIP_DISABLE_PIP_VERSION_CHECK=on \
    PIP_DEFAULT_TIMEOUT=100 \
    POETRY_NO_INTERACTION=1 \
    POETRY_VIRTUALENVS_IN_PROJECT=1 \
    POETRY_VERSION=1.1.12

# build deps
RUN apt-get update && apt-get install -y \
    build-essential \
    git \
    python3-dev \
    unzip \
    wget
RUN pip install "poetry==$POETRY_VERSION"

WORKDIR /app

# install dependencies
COPY pyproject.toml poetry.lock /app/
RUN poetry install --no-dev --no-root

# build and install package
COPY . .
RUN poetry build && \
    /app/.venv/bin/pip install dist/*.whl

# runtime image
FROM base AS runtime
COPY --from=builder /app/.venv/ /app/.venv

WORKDIR /app
RUN useradd mettmail
USER mettmail

ENTRYPOINT ["/app/.venv/bin/mettmail"]