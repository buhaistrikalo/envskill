# Releasing

Releases are made from `main` by pushing a tag that exactly matches the package
version. The release workflow verifies the source, builds the distributions,
publishes to PyPI (Trusted Publishing), and creates a GitHub Release with the
distributions and SHA-256 checksums.

PyPI distribution uses [Trusted Publishing](https://docs.pypi.org/trusted-publishers/)
(OIDC) — no API tokens are needed. Homebrew is provided through the
project-maintained [`buhaistrikalo/homebrew-envskill`](https://github.com/buhaistrikalo/homebrew-envskill)
tap and is updated from tagged GitHub Release assets.

## Distribution targets

- [x] Publish to PyPI through Trusted Publishing (OIDC, no tokens).
- [x] Add a Homebrew tap with a formula pinned to an immutable release asset
      and SHA-256 checksum.

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
7. When updating the Homebrew tap, change the formula URL, version, and
   checksum together, then run `brew test buhaistrikalo/envskill/envskill`.

For an existing tag that was created before the current workflow was merged,
run the workflow manually from `main`:

```bash
gh workflow run release.yml --ref main -f release_tag=v0.2.0
```

The workflow stops if the tag does not match the package version or any
verification step fails. A rerun may refresh assets for an existing release;
for an intentional correction, create a new version.
