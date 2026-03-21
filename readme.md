# Grokputer - Autonomous AI Assistant

Three production-ready scripts. All share 34 fully implemented tools.
Pick the personality layer that suits your workflow.

## Scripts

### `grokputer_main.py` — Version A (Original)
The original powerhouse. LADY / TRAMP mode switching, full preflight,
agentic tool loop, memory persistence, structured logging.

### `grokputer_hybrid.py` — Version B (Hybrid)
Single unified Scarlett persona — honest, direct, no mode switching.
One identity, full autonomy, same 34 tools. Simpler and clean.

Commands: `who are you` · `status` · `clear` · `quit`

### `grokputer_dual_personality.py` — Version C (Dual Personality)
Two fully realised personalities in one body. LADY MODE: polished,
precise, elegant. TRAMP MODE: wild, magnetic, full throttle.
Same tools and power — radically different energy. Switch at will.

Switch commands: `be a lady` · `be a tramp` · `flip` · `toggle`
Info commands: `persona` · `status` · `clear` · `quit`

## Getting the files onto your computer (GitHub Desktop)

The scripts live on the **`copilot/build-ultimate-scarlett-powerhouse`** branch.
Two ways to get them locally:

### Option 1 — Pull the PR branch directly (fastest)
1. Open **GitHub Desktop**
2. In the top bar click **Current Branch** → find and select
   `copilot/build-ultimate-scarlett-powerhouse`
3. Click **Fetch origin** (top right) — then **Pull origin** if it appears
4. Your local folder now has `grokputer_hybrid.py` and
   `grokputer_dual_personality.py` alongside the original `grokputer_main.py`

### Option 2 — Merge the PR on GitHub first, then pull main
1. Go to [github.com/lotsapoppa1/Grokputer/pulls](https://github.com/lotsapoppa1/Grokputer/pulls)
2. Open the open PR and click **Merge pull request**
3. Back in **GitHub Desktop**, make sure **Current Branch** is `main`
4. Click **Fetch origin** → **Pull origin**
5. Done — all three scripts are now on your `main` branch locally

### Verifying the files are there
After pulling, open the repo folder in Explorer/Finder and confirm you see:
```
grokputer_main.py              ← Version A (original)
grokputer_hybrid.py            ← Version B (single persona)
grokputer_dual_personality.py  ← Version C (dual personality)
scarlett_config.json           ← fill this in with your keys
```

## Quick Start

```bash
# copy and fill in your credentials
cp scarlett_config.json scarlett_config_updated.json

# run whichever version you want
python grokputer_main.py
python grokputer_hybrid.py
python grokputer_dual_personality.py
```

## Tools (all three scripts)
File I/O · Email (send/compose/search) · Screenshots · OCR ·
Browser automation · PDF (extract/merge/split) · Web scraping ·
System monitoring · SQLite database · GitHub (clone/push/issues) ·
Shell execution · Python execution · Package management · Env vars
