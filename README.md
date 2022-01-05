# mettmail
get mail from IMAP server with IDLE extension and deliver to LMTP server, nothing else

## Requirements

* python >=3.6.2
* [poetry](https://python-poetry.org/)

## Run

```shell
poetry run mettmail --help
```

## Install

Install mettmail python package and CLI command.

```shell
poetry install
```

## Development

Install dependencies and pre-commit hooks:

```shell
poetry install --no-root
poetry run pre-commit install
```

Make sure to use tests:

```shell
poetry run pytest
```
