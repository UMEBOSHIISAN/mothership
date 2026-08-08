# Installation and lifecycle

## Requirements

- Git
- Python 3.12 or later
- A shell that can run POSIX shell scripts

No package installation is required for the bundled tests or diagnostics.

## Install

```sh
git clone https://github.com/UMEBOSHIISAN/mothership.git
cd mothership
python3 --version
```

Confirm that the reported Python version is 3.12 or newer before continuing.

## Run the diagnostic

```sh
./bootstrap/doctor.sh
```

The diagnostic checks the local availability and documented options of fixed adapter aliases. It does not install software, authenticate, invoke a model, make a network request, edit settings, or create hooks. It exits non-zero when an adapter is not available; that result is diagnostic information, not a broken installation.

## Verify the checkout

```sh
python3 -m unittest discover -s tests -v
```

All tests should pass. If Python reports missing language features such as `datetime.UTC` or `zip(..., strict=True)`, switch to Python 3.12+ and run the command again.

## Review local configuration

[`config/executors.example.json`](../config/executors.example.json) intentionally includes empty command arrays. It is a review template, not a ready-to-run configuration.

If you create a local configuration:

1. Keep it in a user-controlled location.
2. Review every command and path before use.
3. Keep tokens, credentials, private data, and machine-specific paths out of Git.
4. Treat every eventual external action as a separate, human-approved step.

Mothership itself does not read a credential, install a hook, or alter your editor or Codex configuration.

## Update

1. Obtain the next tagged release from GitHub.
2. Read its changelog and compare its checksum manifest if one is included.
3. Replace the old checkout or clone the new release into a separate directory.
4. Run the test command above before using it.

There is no in-place updater.

## Remove

Delete the cloned repository directory when you no longer need it. Mothership does not leave installed hooks, managed credentials, or settings changes behind.

## Troubleshooting

| Symptom | Check |
| --- | --- |
| Tests fail on language features | Use Python 3.12 or later |
| The diagnostic returns non-zero | Read its JSON output; an adapter may simply be unavailable locally |
| You need an adapter command | Add it only after local review; the included example is intentionally blank |
| You need to perform an external action | Do it outside Mothership using your own credentials and explicit approval |
