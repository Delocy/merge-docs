# merge-docs

**Your FastAPI contracts, documented automatically.** merge-docs reads every endpoint's request and response models straight from the code. Then it:

- **comments on each pull request** with its API changes: endpoints added, removed or renamed, and fields added, removed, retyped, or made required
- **publishes a searchable API catalogue** to GitHub Pages on every push to your default branch

Nobody writes docs, and nobody digs through the codebase. Nothing is guessed: if the code doesn't declare a model, the catalogue says so. There's no AI, and your code is never run. It's read statically.

## Add it to a repo (about 5 minutes)

1. Copy [`examples/api-changes.yml`](examples/api-changes.yml) and [`examples/catalogue.yml`](examples/catalogue.yml) into your repo's `.github/workflows/`. If your default branch isn't `main`, change it in `catalogue.yml`.
2. In your repo, go to **Settings → Pages → Build and deployment → Source: GitHub Actions**.
3. Push to the default branch. The catalogue appears at `https://<owner>.github.io/<repo>/`.
4. Open a PR that changes a route or a Pydantic model. A comment from `github-actions[bot]` lists the API changes.

Organisation repos may need an admin to allow Pages and to let workflows use `pull-requests: write`.

> **Visibility:** a GitHub Pages site is public, unless your organisation has GitHub Enterprise Cloud with private Pages. Check this before publishing the catalogue of a private codebase. The PR comments work on their own, without Pages.

## Optional: notes per feature

Add `docs/features/<path/to/router_module>.md` (for example `docs/features/app/routers/orders.md`) to explain how a feature works. Notes show on the catalogue page. When a PR removes an endpoint or a field that a note mentions in backticks (`` `GET /api/orders/{id}` ``, `` `status` ``), the PR comment lists the note under **Notes to update**.

## What it understands

- Routes declared with `@router.get/post/put/patch/delete`, `@router.api_route(methods=[...])` and `router.add_api_route(...)`, including `APIRouter(prefix=...)` and `include_router(..., prefix=...)`, through relative imports and app factories
- Request bodies and responses from Pydantic models (`response_model=` or the return annotation), with inheritance, `Optional`/`X | None`, `list[X]`, and nested models one level deep
- Test files (`tests/`, `test_*.py`, `conftest.py`) are ignored

## Try it on past PRs first (free)

```bash
GITHUB_TOKEN=$(gh auth token) python -m merge_docs.cli.validate --repo owner/name --pr 101 --pr 117 --out validation/
```

This writes, for each PR, the comment merge-docs would have posted and the catalogue pages for the modules that changed. See [`docs/validation.md`](docs/validation.md).

## Develop

```bash
uv sync
uv run pytest
```

Demo: [Delocy/daily-frame-api-demo](https://github.com/Delocy/daily-frame-api-demo), with its [live catalogue](https://delocy.github.io/daily-frame-api-demo/).
