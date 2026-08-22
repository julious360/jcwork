---
name: ship-check
description: Run the exact CI gate locally before pushing — ruff, ruff format, mypy, pytest — and fix what fails. Use before committing or pushing, or when CI is red and the failure needs reproducing.
---

# Ship Check

Deliberately thin: it wraps the repository's own gate, it does not invent one.
The authority is `.github/workflows/ci.yml`; if this skill and that file disagree,
the workflow wins and this skill is out of date.

## The gate, in order

```bash
ruff check agent tests
ruff format --check agent tests
mypy agent
pytest -q
```

Stop at the first failure, fix it, then restart from the top. A later stage passing
on an unfixed earlier stage means nothing.

## Fix rules

- `ruff format --check` failing → `ruff format agent tests`, then re-read the diff.
  Never hand-format to satisfy it.
- `mypy` failing → add the annotation. `disallow_untyped_defs` is on; a `# type: ignore`
  needs a reason in the same line's comment, and `warn_unused_ignores` will fail the
  build if the ignore is unnecessary.
- `pytest` failing → fix the code. **Never skip, xfail, delete, or loosen a test to
  get green.** `tests/test_meta_write_only.py` in particular is an architectural
  guard, not a unit test — if it fails, a read method reached the Meta client and the
  change is wrong.

## Pre-push checklist

- [ ] All four commands clean
- [ ] `ADAGENT_META__DRY_RUN` still defaults to true everywhere
- [ ] No secrets in the diff (`git diff --staged | grep -Ei 'api[_-]?key|token|secret|password'`)
- [ ] Config changes went to `agent/config/*.yaml`, not hardcoded
- [ ] New warehouse reads live in `agent/warehouse/queries.py`

## Headless

```bash
claude -p "/ship-check" --allowedTools "Bash(ruff:*),Bash(mypy:*),Bash(pytest:*),Read,Edit"
```
Wire it as a git pre-push hook:
```bash
printf '#!/usr/bin/env bash\nexec claude -p "/ship-check" --allowedTools "Bash(ruff:*),Bash(mypy:*),Bash(pytest:*),Read,Edit"\n' \
  > .git/hooks/pre-push && chmod +x .git/hooks/pre-push
```
