# Mothership

![Mothership whale logo](assets/mothership-logo.png)

Mothership is a local, non-authorizing orchestration foundation. It provides
staged contracts, local validation helpers, and diagnostic surfaces; it does
not grant authority, choose work, or perform external actions on a user's
behalf.

## Requirements and verification

Use Python 3.12 or later. From the package root, run the test suite with:

```sh
python3 -m unittest discover -s tests -v
```

`bootstrap/doctor.sh` is diagnostic-only. It resolves and starts the packaged
diagnostic command, which can inspect the availability and documented options
of supported local adapter commands. It does not invoke models, install
software, authenticate, or change settings.

## Configuration

`config/executors.example.json` is a placeholder-only example. Copy it only
as a starting point for local review, then fill command arrays deliberately in
your own local configuration. The example intentionally contains no commands,
paths, endpoints, or access material.

Mothership does not install hooks, alter user settings, or manage credentials.
It is a local foundation rather than a service manager or deployment tool.

## Lifecycle

To update, replace the package directory with a newly obtained package
release, then rerun the verification command above. No in-place updater is
provided.

To remove Mothership, delete the cloned package directory. It does not create
hooks, settings changes, or managed credentials that require separate cleanup.

## License

Mothership is distributed under the MIT License. See [LICENSE](LICENSE).
