# Releasing

Releases are made from `main` by pushing a tag that exactly matches the package
version. The release workflow verifies the source, builds the distributions,
publishes them to PyPI through Trusted Publishing, and creates a GitHub Release
with the same artifacts and SHA-256 checksums.

## One-time setup

Configure a PyPI trusted publisher for:

- owner: `buhaistrikalo`
- repository: `envskill`
- workflow: `.github/workflows/release.yml`
- GitHub environment: `pypi`

For the first release, configure a pending publisher if the `envskill` project
does not exist on PyPI yet. No PyPI API token belongs in the repository or in
GitHub secrets.

## Release checklist

1. Keep the worktree clean. Do not stage unrelated local paths such as `.hermes/`
   or `skills/`.
2. Update the version in `pyproject.toml`, `src/envskill/__init__.py`, and
   `uv.lock`.
3. Move the release notes from `Unreleased` to a dated version section in
   `CHANGELOG.md`.
4. Run the checks from `CONTRIBUTING.md` and verify the built distributions with
   `python -m twine check dist/*`.
5. Merge the release commit to `main`, then create and push the matching tag:

   ```bash
   git tag -a v0.2.0 -m "Release v0.2.0"
   git push origin v0.2.0
   ```

The workflow stops if the tag does not match the package version or any
verification step fails. PyPI uploads are immutable; use a yanked release for
an accidental publication and create a new version for corrections.
