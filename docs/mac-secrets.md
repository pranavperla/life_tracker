# Storing API keys on macOS (for any project)

Never commit secrets. Use one of these patterns so **every app** can read the same values without duplicating tokens in each repo.

## 1. macOS Keychain (recommended)

Store each secret once; retrieve by name in scripts or shell.

**Save a secret (run once per secret):**

```bash
security add-generic-password -a "$USER" -s "life-tracker-telegram" -w "PASTE_TOKEN_HERE"
```

Replace the service name (`life-tracker-telegram`) with something unique per secret, e.g. `gemini-api`, `fitbit-client-secret`.

**Read in Terminal (test):**

```bash
security find-generic-password -s "life-tracker-telegram" -w
```

**Use in a project without a `.env` file:** export before running Python:

```bash
export TELEGRAM_BOT_TOKEN=$(security find-generic-password -s "life-tracker-telegram" -w)
export GEMINI_API_KEY=$(security find-generic-password -s "gemini-api" -w)
python main.py
```

Or add those `export` lines to `~/.zshrc` **only if** you are comfortable with secrets in your shell startup (less isolated than Keychain-only reads).

---

## 2. Single private file in your home (simple)

```bash
touch ~/.secrets.env
chmod 600 ~/.secrets.env
```

Put lines like:

```bash
export TELEGRAM_BOT_TOKEN="..."
export GEMINI_API_KEY="..."
```

In `~/.zshrc`:

```bash
[ -f ~/.secrets.env ] && source ~/.secrets.env
```

Then **any** terminal or project sees those variables. **Do not** copy this file into projects; keep one copy in `$HOME` only.

**Risk:** Plaintext on disk. Prefer Keychain for higher sensitivity.

---

## 3. Hybrid (what this repo expects)

This project reads **`python-dotenv`** from a **`.env` file inside the project folder**. That file is gitignored.

Options:

- **Symlink** a shared secrets file (still plaintext):

  ```bash
  ln -s ~/.secrets/life-tracker.env /path/to/life-tracker/.env
  ```

- Or keep **`.env` only in the project** but back it up via Keychain / encrypted backup.

---

## 4. Password managers

1Password, Bitwarden, etc. can store notes and copy-paste into `.env` when you rotate keys. Good for humans; automation still needs Keychain or env files.

---

## Checklist

- [ ] `.env` is in `.gitignore` (this repo includes it).
- [ ] Never paste tokens in GitHub issues, Discord, or AI chats.
- [ ] Rotate any token that was exposed.
