# Publishing Exo Control

## GitHub (wheel / sdist)

```bash
git tag -a v2.0.0 -m "Exo Control v2.0.0"
git push origin v2.0.0
gh release create v2.0.0 --title "v2.0.0" --generate-notes
python -m build
gh release upload v2.0.0 dist/exo_control-2.0.0*
```

Install from tag until PyPI is live:

```bash
pip install "git+https://github.com/ImAvgErix/ExoControl.git@v2.0.0"
```

## PyPI trusted publisher

GitHub side is already done:

- Environment: `pypi` (no extra protection rules)
- Workflow: `.github/workflows/publish.yml` (OIDC `id-token: write`)
- Owner/repo: `ImAvgErix/ExoControl`

PyPI pending publisher is **registered** (2026-08-12) on account **UhhErix**:

- Project: `exo-control`
- GitHub: `ImAvgErix/ExoControl`
- Workflow: `publish.yml`
- Environment: `pypi`

The first successful `publish.yml` run creates the project and turns this pending publisher into an ordinary one.

```bash
# after 2.0 is on origin/main (or a release tag):
gh workflow run publish.yml -R ImAvgErix/ExoControl
```

Do not run publish against an old main (1.2.x) — that would upload the pre-invert tree.
