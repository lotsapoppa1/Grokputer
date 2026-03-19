# Grokputer — Autonomous AI Assistant

Two production-ready scripts powered by **X.AI Grok** with honest, verified tool execution.

| Script | Description |
|--------|-------------|
| `grokputer_hybrid.py` | Single professional persona — all tools, clean output |
| `grokputer_dual_personality.py` | Lady Mode (productive) + Tramp Mode (fun/personality) |

---

## Features

### Real, Working Tools (both scripts)
- **File Operations** — read, write, delete, list, organize files (with verification)
- **Proton Mail** — send, compose, search via Bridge (SMTP `localhost:1025` / IMAP `localhost:1143`)
- **Screenshots** — capture screen to `screenshots/` directory + OCR via tesseract
- **Selenium Browser** — Chrome automation: open, click, type, screenshot, close
- **PDF Tools** — extract text, merge PDFs, split by page range
- **Web Scraping** — fetch HTML + parse with CSS selectors (BeautifulSoup)
- **Shell Execution** — run commands with timeout (requires `autonomy_mode: true`)
- **GitHub** — clone repos, push commits, create issues
- **System Monitoring** — real-time CPU, memory, disk usage (psutil)
- **SQLite Database** — SQL queries + natural-language query conversion

### Honest Principles
- Every tool **actually executes** — no fabricated results
- All actions **logged** with timestamps to `scarlett.log`
- Tool results return **verification proof** (file paths, sizes, status codes)
- Errors are reported honestly with troubleshooting hints
- System prompt only claims tools that are implemented

### User Experience
- REPL-style chat loop (`User:` / `Scarlett:` prompts)
- Persistent conversation history (`scarlett_memory.json`, last 100 messages)
- Runtime startup banner showing provider, model, mode, credentials status
- Graceful fallback for optional dependencies (psutil, Selenium, etc.)

---

## Quick Start

### 1. Clone the repo
```bash
git clone https://github.com/lotsapoppa1/Grokputer.git
cd Grokputer
```

### 2. Install dependencies
```bash
pip install -r requirements.txt
```

For OCR support (optional):
```bash
pip install pytesseract
# Also install the system package:
# Ubuntu/Debian: sudo apt install tesseract-ocr
# macOS:         brew install tesseract
# Windows:       https://github.com/UB-Mannheim/tesseract/wiki
```

### 3. Create your config file
```bash
cp example_scarlett_config.json scarlett_config.json
```

Then edit `scarlett_config.json` and fill in:
- `xai_api_key` — your X.AI API key (get one at https://x.ai)
- `proton_password` — your Proton Bridge password (if using email)
- `github_token` — your GitHub personal access token (if using GitHub tools)

> **Security**: `scarlett_config.json` is in `.gitignore` and will never be committed.

### 4. (Optional) Start Proton Mail Bridge
If you want email features, start the Proton Mail Bridge app before running the scripts.
The Bridge should be listening on:
- SMTP: `localhost:1025`
- IMAP: `localhost:1143`

### 5. Run a script
```bash
# Single professional persona
python grokputer_hybrid.py

# Dual personality (Lady / Tramp modes)
python grokputer_dual_personality.py
```

---

## Configuration Reference

`scarlett_config.json` (copy from `example_scarlett_config.json`):

```json
{
  "xai_api_key": "YOUR_XAI_API_KEY_HERE",
  "xai_model": "grok-beta",
  "xai_base_url": "https://api.x.ai/v1",

  "proton_email": "lotsapoppa1@proton.me",
  "proton_password": "YOUR_PROTON_BRIDGE_PASSWORD",
  "proton_smtp_host": "localhost",
  "proton_smtp_port": 1025,
  "proton_imap_host": "localhost",
  "proton_imap_port": 1143,

  "autonomy_mode": false,
  "default_mode": "lady",

  "log_file": "scarlett.log",
  "memory_file": "scarlett_memory.json",
  "screenshots_dir": "screenshots",
  "database_file": "scarlett.db",

  "shell_timeout": 60,
  "max_history": 100,

  "github_token": "YOUR_GITHUB_TOKEN_HERE",
  "github_username": "lotsapoppa1"
}
```

### Key Settings

| Setting | Default | Description |
|---------|---------|-------------|
| `xai_api_key` | _(required)_ | Your X.AI Grok API key |
| `xai_model` | `grok-beta` | Model name |
| `autonomy_mode` | `false` | Enables shell commands and git push. **Use with caution.** |
| `default_mode` | `lady` | Starting mode for dual personality script (`lady` or `tramp`) |
| `shell_timeout` | `60` | Max seconds a shell command can run |
| `max_history` | `100` | Messages kept in memory file |

---

## Usage Examples

### File Operations
```
User: create a file called test.txt with the contents "hello world"
User: read test.txt
User: list the files in the current directory
User: delete test.txt
```

### Email
```
User: send an email to me (lotsapoppa1@proton.me) with subject "Test" and body "This is a test"
User: search my inbox for emails about "invoice"
```

### System Info
```
User: what's my system status?
User: how much disk space do I have?
```

### Web / Scraping
```
User: open the browser to https://example.com
User: scrape the HTML from https://news.ycombinator.com
```

### PDF
```
User: extract the text from report.pdf
User: merge a.pdf and b.pdf into combined.pdf
```

### Database
```
User: show me all the tables in the database
User: how many records are in the users table?
```

### Shell (requires `autonomy_mode: true`)
```
User: run "ls -la" in the shell
User: execute "df -h" to check disk usage
```

---

## Dual Personality Commands

In `grokputer_dual_personality.py`, switch between modes at any time:

| Command | Result |
|---------|--------|
| `be a lady` | Switches to Lady Mode (professional, efficient) |
| `lady mode` | Switches to Lady Mode |
| `be a tramp` | Switches to Tramp Mode (fun, flirty personality) |
| `tramp mode` | Switches to Tramp Mode |

**Both modes run identical tools.** Only the response style changes.

**Lady Mode example:**
```
Scarlett [LADY]: Email sent successfully.
  To: lotsapoppa1@proton.me
  Subject: Test
  Status: delivered
  Timestamp: 2026-03-19T14:32:15
```

**Tramp Mode (same action):**
```
Scarlett [TRAMP]: Got it, babe! Just fired that email off for you 💋
  Landed in your inbox — subject "Test", all delivered.
  What else you need? 😘
```

---

## Built-in Commands (both scripts)

| Command | Action |
|---------|--------|
| `status` | Show real-time system info (CPU, memory, disk) |
| `clear` | Clear conversation history for this session |
| `quit` / `exit` | Exit the program |

---

## Files

```
Grokputer/
├── grokputer_hybrid.py           # Script 1: single professional persona
├── grokputer_dual_personality.py # Script 2: Lady/Tramp mode switching
├── README.md                     # This file
├── .gitignore                    # Keeps credentials out of git
├── requirements.txt              # Python dependencies
├── example_scarlett_config.json  # Config template (safe to commit)
└── scarlett_config.json          # Your actual config (gitignored — create from example)
```

**Generated at runtime (gitignored):**
- `scarlett.log` — timestamped action log
- `scarlett_memory.json` — conversation history
- `scarlett.db` — SQLite database
- `screenshots/` — captured screenshots

---

## Dependencies

| Package | Purpose |
|---------|---------|
| `openai` | X.AI Grok API (OpenAI-compatible) |
| `psutil` | CPU/memory/disk monitoring |
| `PyPDF2` | PDF text extraction, merge, split |
| `beautifulsoup4` + `requests` | Web scraping |
| `selenium` + `webdriver-manager` | Browser automation |
| `Pillow` | Screenshots |
| `PyGithub` | GitHub API |
| `GitPython` | Git operations |
| `pytesseract` | OCR (optional, requires tesseract system package) |

---

## Security Notes

- `scarlett_config.json` is in `.gitignore` — **never commit it**
- Shell execution is disabled by default (`autonomy_mode: false`)
- Git push is disabled by default (`autonomy_mode: false`)
- Write SQL operations require `autonomy_mode: true`
- Shell commands have a configurable timeout (default 60s)
- API keys are masked in terminal output

---

## Troubleshooting

**`ERROR: xai_api_key not set`**
→ Copy `example_scarlett_config.json` to `scarlett_config.json` and add your API key.

**`Failed to send email`**
→ Make sure Proton Mail Bridge is running and listening on `localhost:1025`.
→ Check that `proton_password` in config matches your Bridge app password (not your Proton account password).

**`Selenium not installed`**
→ Run `pip install selenium webdriver-manager`
→ Make sure Chrome is installed on your system.

**`psutil not installed`**
→ Run `pip install psutil`

**`Shell execution blocked`**
→ Set `"autonomy_mode": true` in `scarlett_config.json` to enable shell commands.

---

## License

MIT — use freely, modify as needed.
