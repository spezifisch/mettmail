# mettmail

Get mail from IMAP server with IDLE extension and deliver to LMTP server, nothing else.

**Design choices:**

-   Our most important goal is to never risk losing any email.
-   Processed incoming emails are only flagged as fetched but not yet deleted.
-   We ensure that only emails are flagged which have been 100% certainly delivered to their LMTP destination.
-   All errors lead to safe failure states, most of them just quitting of the program and retry on the next run. (Though this will be improved in the future.)
-   Rely on IMAP IDLE and custom flags features.
-   As little state should be kept inside mettmail as possible. (Currently no state at all is kept; fetched mails are marked with an IMAP flag which is stored on the server.)
-   100% unit test coverage, additional black box tests against a real non-mocked IMAP/LMTP-server.

**TODO:**

-   Implement deleting emails (figure out how to do it in a safe way, currently all emails are flagged but kept)
-   Test and ensure Podman compatibility
-   Implement Docker health checking

## Usage with Docker

This is the recommended way like [docker-dovecot-mettmail](https://github.com/spezifisch/docker-dovecot-mettmail) is using this package.

This script it designed to take advantage of Docker's automatic restarting feature to simplify our error logic.

Pretty much every non-recoverable error leads to an exception that leaves all mails in a safe state and whatever failed is tried again on the next run. Also it's pretty nice security-wise that every mettmail instance runs in its own container without being able to see login credentials for other configured accounts.

### Requirements

-   Docker
-   docker-compose

### Run

Use the included `docker-compose.yaml` and `mettmail.example.yaml` as a starting point.

1. Rename `mettmail.example.yaml` to something like `mettmail-foo.yaml` and add your IMAP/LMTP server credentials. Using the schema `mettmail-XXX.yaml` is recommended so your configuration isn't included in a layer of the image if you're building the Docker image yourself instead of using the provided release from GitHub (the `.dockerignore` file excludes files using this naming pattern).
2. Edit `docker-compose.yaml` and rename your service from `mettmail_example` to `mettmail_foo`. Also make sure to change the entry for the configuration file.
3. Add multiple copies of this service with own configs for each of your accounts that you want to fetch.

Finally:

```shell
docker-compose up -d
```

View logs:

```shell
docker-compose logs -f
```

Make sure the services are healthy (TODO after Docker health checking has been implemented):

```shell
docker-compose ps
```

## Usage without Docker

You _can_ use mettmail without Docker with the following steps.

### Requirements

-   python >=3.8
-   [poetry](https://python-poetry.org/) (`pip install --user poetry`)

Install dependencies:

```shell
poetry install --no-root
```

### Run

Create configuration file based on the example:

```shell
cp mettmail.example.yaml mettmail.yaml
```

Edit it with your IMAP/LMTP connection details. You can override most of `DeliverLMTP` and `FetchIMAP` constructor parameters.

Run parameters:

```shell
poetry run mettmail --help
```

Now you need something to restart mettmail after failures, for example:

-   Run it as a systemd (user) service

## Development

### Build Dependencies

-   [nox](https://nox.thea.codes/) as test-runner
-   [pyenv](https://github.com/pyenv/pyenv) (recommended) to manage python versions

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

# using nox for a single Python version
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

After that it runs much more quickly reusing the created virtualenvs.

## Issues/Contributions

Bug reports and contributions are welcome. Please use the issue tracker for bug reports and send a PR if you have something to contribute.
Please make sure to run the configured pre-commit tools to make integration and review easier.
