# mettmail

Get mail from IMAP server with IDLE extension and deliver to LMTP server, nothing else.

## Requirements

* python >=3.6.2

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

### Build Dependencies

* [poetry](https://python-poetry.org/)
* [nox](https://nox.thea.codes/) as test-runner
* [pyenv](https://github.com/pyenv/pyenv) (recommended) to manage python versions

Install dependencies and pre-commit hooks:

```shell
poetry install --no-root
poetry run pre-commit install
```

### Test/Coverage setup

#### Quickly

You can quickly run tests with:

```shell
# using your default interpreter
poetry run pytest

# using nox (add -r for the following runs)
nox -p 3.8
```

#### Thoroughly

Use `nox` to run tests and other useful things automatically for all supported python versions.

Initial setup for all interpreters and environments:

```shell
pyenv install 3.6.15
pyenv install 3.7.12
pyenv install 3.8.12
pyenv install 3.9.9
pyenv install 3.10.1
pyenv local 3.6.15 3.7.12 3.8.12 3.9.9 3.10.1
nox
```

After that it runs much more quickly reusing the created virtualenvs:

```shell
nox -r
```
