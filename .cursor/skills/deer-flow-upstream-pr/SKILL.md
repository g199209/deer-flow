---
name: deer-flow-upstream-pr
description: Opens a pull request against the upstream bytedance/deer-flow repository from a personal fork after running project checks (CONTRIBUTING.md and CI parity). Use when the user wants to contribute via PR to upstream, cherry-pick a commit from dev onto main-based branch, push the fork, and create the PR with GitHub CLI—or when they ask to follow the DeerFlow upstream PR workflow.
---

# DeerFlow: upstream PR from a fork

## When this applies

- Changes live on **`dev`** (or another branch) and should be submitted **to `bytedance/deer-flow`**, not only the fork.
- The user uses **`origin`** = their fork and **`gh`** authenticated to GitHub.

## Prerequisites

- `gh` CLI installed and `gh auth login` done.
- SSH or HTTPS access to `git@github.com:bytedance/deer-flow.git` (read).
- Push access to the fork (`origin`).

## 1. Discover requirements and run checks

1. Read **CONTRIBUTING.md** at repo root for declared checks.
2. Read **.github/workflows/backend-unit-tests.yml** for CI parity (backend `make lint`, `make test` in `backend/`).

**Run (from repo root):**

| Area | Command | Notes |
|------|---------|--------|
| Backend lint | `cd backend && make lint` | `ruff` |
| Backend tests | `cd backend && make test` | Full `pytest` suite |
| Frontend | `cd frontend && pnpm install` (if needed), then `pnpm lint` and `pnpm exec tsc --noEmit` | See note below |
| Format spot-check | `pnpm exec prettier --check "<paths you touched>"` | CONTRIBUTING cites Prettier for frontend |

> **Note — `pnpm check` vs `pnpm lint` + `tsc`:** `pnpm check` internally calls `next lint`, which can fail on some Next.js versions with a CLI-level error unrelated to the code. Use `pnpm lint` (ESLint) + `pnpm exec tsc --noEmit` (TypeScript) as the reliable gate instead.

**Local-only backend failure (not a regression from a frontend-only change):** Root **`config.yaml` is gitignored**. If it enables a non-default **checkpointer** (e.g. sqlite), `tests/test_checkpointer.py` may fail locally while **CI passes** (no `config.yaml` in a clean clone). Say so explicitly if stopping the workflow; do not block a frontend-only PR on that without confirming.

If checks that are **in scope for the change** fail, **stop**: fix or align with the user before branching/PR.

## 2. Base branch and feature branch

1. Ensure **`upstream`** remote exists (idempotent):
   ```bash
   git remote get-url upstream 2>/dev/null || git remote add upstream git@github.com:bytedance/deer-flow.git
   ```
2. `git fetch upstream main`
3. `git checkout main`
4. `git merge upstream/main` (fast-forward preferred) so the PR base matches upstream `main`.
5. `git checkout -b <pr-branch-name>` — use a short, descriptive name prefixed with the conventional commit type:
   - `fix/<slug>` — bug fixes
   - `feat/<slug>` — new features
   - `docs/<slug>` — documentation only
   - `refactor/<slug>`, `chore/<slug>`, `build/<slug>` — as appropriate
   - Example: `fix/subtask-card-only-task-tool-calls`
6. Cherry-pick the commit(s) from **`dev`** (or the source branch):
   - Single commit: `git cherry-pick <sha>`
   - Multiple commits (preserve order, oldest first): `git cherry-pick <sha1> <sha2> ...`
   - Contiguous range: `git cherry-pick <oldest-sha>^..<newest-sha>`

Resolve conflicts after each cherry-pick step before pushing.

## 3. Push and open the PR (upstream, not the fork as target)

1. Push the PR branch to **the fork**: `git push -u origin <pr-branch-name>`.
2. Create the PR **against upstream** with head = **`fork-owner:branch`**:

```bash
gh pr create -R bytedance/deer-flow --base main --head <your-github-username>:<pr-branch-name> \
  --title "conventional title" \
  --body "$(cat <<'EOF'
... detailed English body: background, problem, root cause, approach, testing, follow-ups ...
EOF
)"
```

**PR body (English):** Prefer a clear structure: **Background**, **Root cause** (or **Problem**), **What this PR does**, **Testing**, optional **Follow-ups**. Upstream reviewers expect concise technical English.

## 4. After the PR is open

1. **`git checkout dev`** so day-to-day work continues on the usual branch.
2. Optionally sync fork `main` with upstream when convenient: `git checkout main && git push origin main`.

## Quick checklist

- [ ] CONTRIBUTING + CI-relevant checks run; failures explained if environment-specific
- [ ] `main` updated from `upstream/main`
- [ ] PR branch created; commit(s) cherry-picked
- [ ] Pushed to `origin`
- [ ] `gh pr create -R bytedance/deer-flow` with `--head user:branch`
- [ ] **Checked out `dev` again**
