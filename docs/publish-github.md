# Push this repo to GitHub (from Cursor)

Your code is committed on branch `main`. Automated `git push` from a sandbox cannot use your GitHub login—you publish from **your Mac** using Cursor (or Terminal) after GitHub is connected.

## Option A — Cursor (recommended after connecting GitHub)

1. Open the **Source Control** view (branch icon in the left sidebar, or `Ctrl+Shift+G` / `Cmd+Shift+G`).
2. If you see **Publish Branch** or **Publish to GitHub**, click it.
3. Choose **Private** repository and a name (e.g. `life-tracker`).
4. Cursor will create the repo (if needed) and push using your connected account.

If you already created an empty repo on github.com:

1. **Command Palette** (`Cmd+Shift+P`) → run **Git: Add Remote…**  
   Paste: `https://github.com/YOUR_USERNAME/YOUR_REPO.git`
2. Then **Sync** / **Push** from Source Control.

## Option B — Terminal on your Mac

1. Create a **new empty** repository on [github.com/new](https://github.com/new) (no README). Note the URL.

2. In Terminal:

```bash
cd /path/to/expenses-whatsapp-tracking

git remote add origin https://github.com/YOUR_USERNAME/YOUR_REPO.git
git branch -M main
git push -u origin main
```

Use a **Personal Access Token** as the password when prompted (GitHub → Settings → Developer settings → Personal access tokens), or set up **SSH** and use `git@github.com:YOUR_USERNAME/YOUR_REPO.git`.

## Verify `.env` is not pushed

```bash
git ls-files | grep -E '^\.env$' && echo "STOP: .env tracked!" || echo "OK: .env not in git"
```

Should print `OK`.
