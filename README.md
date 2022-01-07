# mettmail

Get mail from IMAP server with IDLE extension and deliver to LMTP server, nothing else.

## Requirements

* python >=3.8
* [poetry](https://python-poetry.org/) (`pip install --user poetry`)

## Install

Install mettmail python package and CLI command.

```shell
poetry install --no-root
```

## Run

Create configuration file based on the example:

```shell
cp mettmail.example.yaml mettmail.yaml
```

Edit it with your IMAP/LMTP connection details. You can override most of `DeliverLMTP` and `FetchIMAP` constructor parameters.

Run parameters:

```shell
poetry run mettmail --help
```

## Development

### Build Dependencies

* [nox](https://nox.thea.codes/) as test-runner
* [pyenv](https://github.com/pyenv/pyenv) (recommended) to manage python versions

Install dependencies and pre-commit hooks:

```shell
# you may need to install the following tools outside of your virtualenv, too:
pip install nox poetry pre-commit
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

**Note:** Python 3.10 support is currently broken because of a bug in `aioimaplib`.

Use `nox` to run tests and other useful things automatically for all supported python versions.

Initial setup for all interpreters and environments:

```shell
pyenv install 3.8.12
pyenv install 3.9.9
pyenv install 3.10.1
pyenv local 3.8.12 3.9.9 3.10.1
nox
```

After that it runs much more quickly reusing the created virtualenvs:

```shell
nox -r
```
