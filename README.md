# grok-repos

A single place for small, unrelated side projects: film and writing work, code experiments, little apps, and anything else built with AI assistants. Each project stays in its own folder. Nothing here is shared between them.

## Layout

```
grok-repos/
  README.md
  .gitignore
  projects/
    _template/      copy this when starting something new
    some-project/   one folder per project
```

The root of the repo only holds this README, the gitignore, and `projects/`. There is no shared build, package manager, or CI. A project can be notes, a script, or an app; it does not have to match its neighbors.

Folders under `projects/` whose names start with `_` are for the repo itself (today, only `_template`). Real projects use a normal name.

## Add a project

1. Copy `projects/_template` to `projects/<name>`. Use a short lowercase name with hyphens, such as `projects/short-film-notes`.
2. Rewrite that folder's README so it says what the project is and how to open or run it.
3. Put the project's files in that folder. Commit from the repository root as usual.

Projects do not import code from each other. If one grows dependencies, those live inside its own folder (`package.json`, `requirements.txt`, and so on).

## Move a project into its own repository

When one project should live in a separate private repository, split out the commits that touched its folder and push that history to the new remote. Do this from a clean working tree. Work in a copy or a new branch so this repo's `main` history stays as it is. Afterward, check `git log` in the new repo and confirm the files look right before deleting the folder here.

History that comes along is the commits that changed files inside that project folder. If a file was moved in from elsewhere in grok-repos, the commits from before that move usually stay behind.

### git subtree split

This is built into Git. It writes a branch whose root is the project folder.

```bash
git subtree split --prefix=projects/<name> -b <name>-split
```

Create the new repository from that branch:

```bash
mkdir ../<name>
cd ../<name>
git init -b main
git pull /path/to/grok-repos <name>-split
git remote add origin <private-repo-url>
git push -u origin main
```

### git filter-repo

[`git filter-repo`](https://github.com/newren/git-filter-repo) rewrites a clone so only one folder remains, and that folder becomes the repository root. It is not part of Git; install it with `pip install git-filter-repo` if the command is missing. Run it on a fresh clone. It removes the `origin` remote on purpose so the rewrite cannot be pushed back here by mistake.

```bash
git clone --no-local /path/to/grok-repos ../<name>
cd ../<name>
git filter-repo --subdirectory-filter projects/<name>
git remote add origin <private-repo-url>
git push -u origin main
```

`--no-local` avoids sharing objects with this repository, so the rewrite stays inside the clone.
