# Publishing Exo Control

## GitHub release (done for v1.2.0)

```bash
git tag -a v1.2.0 -m "Exo Control v1.2.0"
git push origin v1.2.0
gh release create v1.2.0 --title "v1.2.0" --notes-file notes.md
gh release upload v1.2.0 dist/*.whl dist/*.tar.gz
```

Install from tag:

```bash
pip install "git+https://github.com/ImAvgErix/ExoControl.git@v1.2.0"
```

Or from release asset:

```bash
pip install https://github.com/ImAvgErix/ExoControl/releases/download/v1.2.0/exo_control-1.2.0-py3-none-any.whl
```

## PyPI (one-time setup)

Workflow: `.github/workflows/publish.yml` (Trusted Publishing / OIDC).

1. Create project **exo-control** on https://pypi.org (or claim name).
2. PyPI → Account settings → **Publishing** → **Add a new pending publisher**:
   - Owner: `ImAvgErix`
   - Repository: `ExoControl`
   - Workflow: `publish.yml`
   - Environment: `pypi`
3. GitHub repo → Settings → Environments → create **`pypi`** (optional protection rules).
4. Publish a GitHub Release (or run workflow_dispatch on `publish.yml`).

Until then, use the git/tag or release wheel install above.

## Verify install

```bash
pip install "git+https://github.com/ImAvgErix/ExoControl.git@v1.2.0"
exo-control doctor
python -c "from exo_control import ExoExecEngine; print(ExoExecEngine)"
```
