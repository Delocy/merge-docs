# Validation: does the contract catalogue unblock people? (go/no-go)

Run this before rolling merge-docs out to a team. It's **free**: it uses only the GitHub API and reads the code at each PR's base and head. No AI, and no API keys beyond GitHub.

## Run it

1. Pick 3–5 merged PRs from the team's repo that changed FastAPI routes or Pydantic models. Include the one where a teammate got stuck.
2. From a checkout of merge-docs (after `uv sync`):
   ```bash
   GITHUB_TOKEN=$(gh auth token) uv run python -m merge_docs.cli.validate --repo owner/name --pr 101 --pr 117 --pr 130 --out validation/
   ```
3. For each PR, open:
   - `validation/<pr>-comment.md`: the comment the app would have posted on that PR
   - `validation/<pr>-<module>.md`: the catalogue page for each module whose contract changed

## Rate each page

Ask the developer who got blocked:

| PR | Module | Would this page have unblocked you? (yes / partly / no) | What was missing? |
|----|--------|----------------------------------------------------------|-------------------|
|    |        |                                                          |                   |

## Decide

- **Go** ahead with the workflows if most pages are rated "yes".
- **Look at `declared_response_share`** in `summary.csv`. It's the share of endpoints whose response model the code declares. If it's low, many pages say "not declared", and adding `response_model=` to routes is the cheaper fix before building more.
- **Rethink** if pages are rated "no" because people need the *why*, not the contract. Author notes or an AI add-on would then matter more.
