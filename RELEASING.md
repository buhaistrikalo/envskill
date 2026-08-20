# Releasing

Releases are made from `main` by pushing a tag that exactly matches the package
version. The release workflow verifies the source, builds the distributions,
and creates a GitHub Release with the distributions and SHA-256 checksums.

PyPI and Homebrew are future distribution targets. The current release path
does not require either service.

## Future distribution targets

- [ ] Publish to PyPI through Trusted Publishing.
- [ ] Add a Homebrew formula or tap after the package distribution path is
      established.

Do not add PyPI API tokens to the repository or GitHub secrets when this work
is scheduled.

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
6. Verify the GitHub Release contains both distributions and `SHA256SUMS`, then
   install from the tag using the command in `README.md`.

The workflow stops if the tag does not match the package version or any
verification step fails. GitHub Release assets are immutable for a published
version; create a new version for corrections.
