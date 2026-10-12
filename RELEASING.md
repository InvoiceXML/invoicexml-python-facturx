# Releasing to PyPI

Pushing a version tag publishes the release. The Release workflow tests and builds the package, then publishes it to PyPI once a maintainer approves the run. No API token is stored anywhere: PyPI trusts the workflow through Trusted Publishing.

## Each release

1. Set the new version in `pyproject.toml` and add it to `CHANGELOG.md`.
2. Run the tests, including the live suite: `INVOICEXML_LIVE=1 pytest`.
3. Commit, push, then tag and push the tag:

   ```bash
   git tag -a v1.2.3 -m "Release 1.2.3"
   git push origin v1.2.3
   ```

4. Open the *Actions* tab, select the *Release* run and press *Review deployments*, then *Approve and deploy*.

The workflow stops if the tag does not match the version in `pyproject.toml`.

## One-time setup

On [pypi.org](https://pypi.org), under *Your account*, then *Publishing*, add a trusted publisher. For a project that does not exist yet, use the pending publisher form:

| Field | Value |
|---|---|
| PyPI project name | the `name` in `pyproject.toml` |
| Owner | `InvoiceXML` |
| Repository name | this repository's name |
| Workflow name | `release.yml` |
| Environment name | `pypi` |

The first tagged release then creates the project on PyPI.
