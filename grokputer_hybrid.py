#!/usr/bin/env python3
"""
Grokputer Hybrid - Scarlett AI Assistant
Professional AI assistant with real file, email, web, shell, system, and DB capabilities.
"""

import json
import logging
import os
import shutil
import sqlite3
import smtplib
import subprocess
import sys
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from pathlib import Path

try:
    import requests
    HAS_REQUESTS = True
except ImportError:
    HAS_REQUESTS = False
    logging.warning("requests not installed — web commands disabled")

try:
    from bs4 import BeautifulSoup
    HAS_BS4 = True
except ImportError:
    HAS_BS4 = False
    logging.warning("beautifulsoup4 not installed — web scraping disabled")

try:
    import psutil
    HAS_PSUTIL = True
except ImportError:
    HAS_PSUTIL = False
    logging.warning("psutil not installed — system info disabled")

VERSION = "1.0.0"
CONFIG_FILE = "scarlett_config.json"

DEFAULT_CONFIG = {
    "name": "Scarlett",
    "email": "lotsapoppa1@proton.me",
    "proton_password": "",
    "smtp_host": "localhost",
    "smtp_port": 1025,
    "logging": {
        "level": "INFO",
        "file": "grokputer.log"
    }
}


def load_config() -> dict:
    """Load config from file, falling back to defaults."""
    if os.path.exists(CONFIG_FILE):
        try:
            with open(CONFIG_FILE, "r", encoding="utf-8") as f:
                cfg = json.load(f)
            # Merge with defaults for any missing keys
            merged = {**DEFAULT_CONFIG, **cfg}
            merged["logging"] = {**DEFAULT_CONFIG["logging"], **cfg.get("logging", {})}
            return merged
        except (json.JSONDecodeError, IOError) as e:
            print(f"[WARNING] Could not load {CONFIG_FILE}: {e}. Using defaults.")
    return dict(DEFAULT_CONFIG)


def setup_logging(config: dict) -> None:
    """Configure file and console logging handlers."""
    log_cfg = config.get("logging", DEFAULT_CONFIG["logging"])
    level_str = log_cfg.get("level", "INFO").upper()
    level = getattr(logging, level_str, logging.INFO)
    log_file = log_cfg.get("file", "grokputer.log")

    fmt = logging.Formatter("%(asctime)s [%(levelname)s] %(name)s: %(message)s")

    root = logging.getLogger()
    root.setLevel(level)
    root.handlers.clear()

    fh = logging.FileHandler(log_file, encoding="utf-8")
    fh.setLevel(level)
    fh.setFormatter(fmt)
    root.addHandler(fh)

    ch = logging.StreamHandler(sys.stdout)
    ch.setLevel(logging.WARNING)
    ch.setFormatter(fmt)
    root.addHandler(ch)


logger = logging.getLogger("scarlett")


# ---------------------------------------------------------------------------
# File Operations
# ---------------------------------------------------------------------------

def file_list(path: str = ".") -> str:
    """List directory contents."""
    try:
        p = Path(path)
        if not p.exists():
            return f"Error: path '{path}' does not exist."
        if not p.is_dir():
            return f"Error: '{path}' is not a directory."
        entries = sorted(p.iterdir(), key=lambda x: (x.is_file(), x.name.lower()))
        lines = []
        for entry in entries:
            kind = "DIR " if entry.is_dir() else "FILE"
            try:
                size = entry.stat().st_size if entry.is_file() else ""
                size_str = f"  ({size} bytes)" if size != "" else ""
            except OSError:
                size_str = ""
            lines.append(f"  [{kind}] {entry.name}{size_str}")
        result = f"Contents of '{p.resolve()}':\n" + "\n".join(lines) if lines else f"Directory '{path}' is empty."
        logger.info("file_list: %s", path)
        return result
    except PermissionError:
        msg = f"Error: permission denied reading '{path}'."
        logger.error("file_list permission denied: %s", path)
        return msg
    except Exception as e:
        logger.exception("file_list error")
        return f"Error listing '{path}': {e}"


def file_read(path: str) -> str:
    """Read and return file contents."""
    try:
        p = Path(path)
        if not p.exists():
            return f"Error: file '{path}' does not exist."
        if not p.is_file():
            return f"Error: '{path}' is not a file."
        content = p.read_text(encoding="utf-8", errors="replace")
        logger.info("file_read: %s (%d bytes)", path, len(content))
        return f"--- {path} ---\n{content}"
    except PermissionError:
        msg = f"Error: permission denied reading '{path}'."
        logger.error("file_read permission denied: %s", path)
        return msg
    except Exception as e:
        logger.exception("file_read error")
        return f"Error reading '{path}': {e}"


def file_write(path: str, content: str) -> str:
    """Write content to a file, creating parent dirs as needed."""
    try:
        p = Path(path)
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(content, encoding="utf-8")
        logger.info("file_write: %s (%d bytes)", path, len(content))
        return f"Successfully wrote {len(content)} bytes to '{path}'."
    except PermissionError:
        msg = f"Error: permission denied writing '{path}'."
        logger.error("file_write permission denied: %s", path)
        return msg
    except Exception as e:
        logger.exception("file_write error")
        return f"Error writing '{path}': {e}"


def file_delete(path: str) -> str:
    """Delete a file."""
    try:
        p = Path(path)
        if not p.exists():
            return f"Error: '{path}' does not exist."
        if p.is_dir():
            return f"Error: '{path}' is a directory. Use shell rm -rf for directories."
        p.unlink()
        logger.info("file_delete: %s", path)
        return f"Deleted '{path}'."
    except PermissionError:
        msg = f"Error: permission denied deleting '{path}'."
        logger.error("file_delete permission denied: %s", path)
        return msg
    except Exception as e:
        logger.exception("file_delete error")
        return f"Error deleting '{path}': {e}"


def file_organize(source_dir: str) -> str:
    """Move files into subdirectories grouped by file extension."""
    try:
        src = Path(source_dir)
        if not src.exists() or not src.is_dir():
            return f"Error: '{source_dir}' is not a valid directory."

        moved = []
        skipped = []
        for item in src.iterdir():
            if not item.is_file():
                continue
            ext = item.suffix.lstrip(".").lower() or "no_extension"
            dest_dir = src / ext
            dest_dir.mkdir(exist_ok=True)
            dest = dest_dir / item.name
            if dest.exists():
                skipped.append(item.name)
                continue
            shutil.move(str(item), str(dest))
            moved.append(f"  {item.name} → {ext}/")

        logger.info("file_organize: %s — moved %d, skipped %d", source_dir, len(moved), len(skipped))
        lines = [f"Organized '{source_dir}':"]
        if moved:
            lines += moved
        if skipped:
            lines.append(f"  Skipped (already exist at destination): {', '.join(skipped)}")
        if not moved and not skipped:
            lines.append("  No files to organize.")
        return "\n".join(lines)
    except Exception as e:
        logger.exception("file_organize error")
        return f"Error organizing '{source_dir}': {e}"


# ---------------------------------------------------------------------------
# Email
# ---------------------------------------------------------------------------

def email_send(config: dict, to: str, subject: str, body: str) -> str:
    """Send an email via the Proton Mail SMTP bridge."""
    smtp_host = config.get("smtp_host", "localhost")
    smtp_port = config.get("smtp_port", 1025)
    from_addr = config.get("email", "lotsapoppa1@proton.me")
    password = config.get("proton_password", "")

    msg = MIMEMultipart("alternative")
    msg["Subject"] = subject
    msg["From"] = from_addr
    msg["To"] = to
    msg.attach(MIMEText(body, "plain", "utf-8"))

    try:
        with smtplib.SMTP(smtp_host, smtp_port, timeout=10) as server:
            server.ehlo()
            if password:
                server.login(from_addr, password)
            server.sendmail(from_addr, [to], msg.as_string())
        logger.info("email_send: to=%s subject=%s", to, subject)
        return f"Email sent to '{to}' with subject '{subject}'."
    except smtplib.SMTPAuthenticationError as e:
        msg_err = f"Error: SMTP authentication failed — {e}"
        logger.error("email_send auth error: %s", e)
        return msg_err
    except ConnectionRefusedError:
        msg_err = f"Error: Could not connect to SMTP bridge at {smtp_host}:{smtp_port}. Is Proton Mail Bridge running?"
        logger.error("email_send connection refused: %s:%s", smtp_host, smtp_port)
        return msg_err
    except Exception as e:
        logger.exception("email_send error")
        return f"Error sending email: {e}"


# ---------------------------------------------------------------------------
# Web
# ---------------------------------------------------------------------------

def web_scrape(url: str) -> str:
    """Scrape a URL and return text content and links."""
    if not HAS_REQUESTS:
        return "Error: 'requests' library not installed."
    if not HAS_BS4:
        return "Error: 'beautifulsoup4' library not installed."
    try:
        headers = {"User-Agent": "Mozilla/5.0 (compatible; Grokputer/1.0)"}
        resp = requests.get(url, headers=headers, timeout=10)
        resp.raise_for_status()

        parser = "lxml" if _has_lxml() else "html.parser"
        soup = BeautifulSoup(resp.text, parser)

        # Extract title
        title = soup.title.string.strip() if soup.title and soup.title.string else "(no title)"

        # Extract visible text (strip scripts/styles)
        for tag in soup(["script", "style", "noscript"]):
            tag.decompose()
        text = " ".join(soup.get_text(separator=" ").split())[:2000]

        # Extract links
        links = []
        for a in soup.find_all("a", href=True)[:20]:
            href = a["href"].strip()
            link_text = a.get_text(strip=True)[:60]
            if href.startswith("http"):
                links.append(f"  {link_text or '(no text)'}: {href}")

        result = f"URL: {url}\nTitle: {title}\n\nText (truncated):\n{text}"
        if links:
            result += "\n\nLinks:\n" + "\n".join(links)
        logger.info("web_scrape: %s", url)
        return result
    except requests.exceptions.Timeout:
        return f"Error: request to '{url}' timed out."
    except requests.exceptions.HTTPError as e:
        return f"Error: HTTP {e.response.status_code} from '{url}'."
    except Exception as e:
        logger.exception("web_scrape error")
        return f"Error scraping '{url}': {e}"


def web_search(query: str) -> str:
    """Scrape DuckDuckGo search results for the given query."""
    if not HAS_REQUESTS:
        return "Error: 'requests' library not installed."
    if not HAS_BS4:
        return "Error: 'beautifulsoup4' library not installed."
    try:
        url = f"https://html.duckduckgo.com/html/?q={requests.utils.quote(query)}"
        headers = {"User-Agent": "Mozilla/5.0 (compatible; Grokputer/1.0)"}
        resp = requests.get(url, headers=headers, timeout=10)
        resp.raise_for_status()

        parser = "lxml" if _has_lxml() else "html.parser"
        soup = BeautifulSoup(resp.text, parser)

        results = []
        for r in soup.select(".result__body")[:10]:
            title_tag = r.select_one(".result__title")
            snippet_tag = r.select_one(".result__snippet")
            url_tag = r.select_one(".result__url")
            title = title_tag.get_text(strip=True) if title_tag else "(no title)"
            snippet = snippet_tag.get_text(strip=True) if snippet_tag else ""
            link = url_tag.get_text(strip=True) if url_tag else ""
            results.append(f"  [{title}]\n    {link}\n    {snippet}")

        if not results:
            return f"No results found for '{query}' (DuckDuckGo HTML may have changed)."
        logger.info("web_search: %s — %d results", query, len(results))
        return f"Search results for '{query}':\n\n" + "\n\n".join(results)
    except Exception as e:
        logger.exception("web_search error")
        return f"Error searching for '{query}': {e}"


def _has_lxml() -> bool:
    try:
        import lxml  # noqa: F401
        return True
    except ImportError:
        return False


# ---------------------------------------------------------------------------
# Shell
# ---------------------------------------------------------------------------

def shell_run(command: str) -> str:
    """Execute a shell command with a 30-second timeout."""
    logger.info("shell_run: %s", command)
    try:
        result = subprocess.run(
            command,
            shell=True,
            capture_output=True,
            text=True,
            timeout=30
        )
        output = []
        if result.stdout:
            output.append(result.stdout.rstrip())
        if result.stderr:
            output.append(f"[stderr]\n{result.stderr.rstrip()}")
        output.append(f"[exit code: {result.returncode}]")
        return "\n".join(output)
    except subprocess.TimeoutExpired:
        logger.warning("shell_run timeout: %s", command)
        return f"Error: command timed out after 30 seconds."
    except Exception as e:
        logger.exception("shell_run error")
        return f"Error running command: {e}"


# ---------------------------------------------------------------------------
# System Info
# ---------------------------------------------------------------------------

def system_info() -> str:
    """Return CPU, RAM, and disk usage via psutil."""
    if not HAS_PSUTIL:
        return "Error: 'psutil' library not installed."
    try:
        cpu = psutil.cpu_percent(interval=1)
        mem = psutil.virtual_memory()
        disk = psutil.disk_usage("/")

        lines = [
            "=== System Information ===",
            f"  CPU Usage    : {cpu:.1f}%",
            f"  RAM Total    : {_fmt_bytes(mem.total)}",
            f"  RAM Used     : {_fmt_bytes(mem.used)} ({mem.percent:.1f}%)",
            f"  RAM Available: {_fmt_bytes(mem.available)}",
            f"  Disk Total   : {_fmt_bytes(disk.total)}",
            f"  Disk Used    : {_fmt_bytes(disk.used)} ({disk.percent:.1f}%)",
            f"  Disk Free    : {_fmt_bytes(disk.free)}",
        ]
        logger.info("system_info called")
        return "\n".join(lines)
    except Exception as e:
        logger.exception("system_info error")
        return f"Error retrieving system info: {e}"


def _fmt_bytes(n: int) -> str:
    for unit in ("B", "KB", "MB", "GB", "TB"):
        if n < 1024:
            return f"{n:.1f} {unit}"
        n /= 1024
    return f"{n:.1f} PB"


# ---------------------------------------------------------------------------
# Database
# ---------------------------------------------------------------------------

def db_query(db_path: str, sql: str) -> str:
    """Execute a SQL query on a SQLite database and return formatted results."""
    try:
        p = Path(db_path)
        if not p.exists():
            return f"Error: database '{db_path}' does not exist."
        conn = sqlite3.connect(str(p))
        try:
            cursor = conn.cursor()
            cursor.execute(sql)
            rows = cursor.fetchall()
            col_names = [desc[0] for desc in cursor.description] if cursor.description else []
            conn.commit()
        finally:
            conn.close()

        if not rows:
            logger.info("db_query: %s — 0 rows", db_path)
            return f"Query returned no rows.\nSQL: {sql}"

        # Format as a simple table
        col_widths = [len(c) for c in col_names]
        for row in rows:
            for i, val in enumerate(row):
                col_widths[i] = max(col_widths[i], len(str(val)))

        header = "  " + "  |  ".join(c.ljust(col_widths[i]) for i, c in enumerate(col_names))
        sep = "  " + "--+--".join("-" * w for w in col_widths)
        data_lines = [
            "  " + "  |  ".join(str(v).ljust(col_widths[i]) for i, v in enumerate(row))
            for row in rows
        ]
        logger.info("db_query: %s — %d rows", db_path, len(rows))
        return f"Query: {sql}\nRows: {len(rows)}\n\n{header}\n{sep}\n" + "\n".join(data_lines)
    except sqlite3.Error as e:
        logger.error("db_query sqlite error: %s", e)
        return f"SQLite error: {e}"
    except Exception as e:
        logger.exception("db_query error")
        return f"Error querying database: {e}"


# ---------------------------------------------------------------------------
# Help
# ---------------------------------------------------------------------------

HELP_TEXT = """
╔══════════════════════════════════════════════════════════════════╗
║                    Scarlett Command Reference                    ║
╠══════════════════════════════════════════════════════════════════╣
║  FILE OPERATIONS                                                 ║
║    file list [path]               List directory contents        ║
║    file read <path>               Read file contents             ║
║    file write <path> <content>    Write content to file          ║
║    file delete <path>             Delete a file                  ║
║    file organize <source_dir>     Organize files by extension    ║
╠══════════════════════════════════════════════════════════════════╣
║  EMAIL                                                           ║
║    email send <to> <subject> <body>  Send via Proton Bridge      ║
╠══════════════════════════════════════════════════════════════════╣
║  WEB                                                             ║
║    web scrape <url>               Scrape URL for text/links      ║
║    web search <query>             DuckDuckGo search              ║
╠══════════════════════════════════════════════════════════════════╣
║  SHELL                                                           ║
║    shell <command>                Execute shell command (30s)    ║
╠══════════════════════════════════════════════════════════════════╣
║  SYSTEM                                                          ║
║    system info                    CPU, RAM, disk usage           ║
╠══════════════════════════════════════════════════════════════════╣
║  DATABASE                                                        ║
║    db query <db_path> <sql>       Execute SQLite query           ║
╠══════════════════════════════════════════════════════════════════╣
║  GENERAL                                                         ║
║    help                           Show this help text            ║
║    quit / exit                    Exit Scarlett                   ║
╚══════════════════════════════════════════════════════════════════╝
"""


# ---------------------------------------------------------------------------
# Command Dispatcher
# ---------------------------------------------------------------------------

def dispatch(tokens: list, config: dict) -> str:
    """Parse token list and dispatch to the appropriate handler."""
    if not tokens:
        return ""

    cmd = tokens[0].lower()

    # --- file ---
    if cmd == "file":
        if len(tokens) < 2:
            return "Usage: file <list|read|write|delete|organize> [args...]"
        sub = tokens[1].lower()
        if sub == "list":
            path = tokens[2] if len(tokens) > 2 else "."
            return file_list(path)
        elif sub == "read":
            if len(tokens) < 3:
                return "Usage: file read <path>"
            return file_read(tokens[2])
        elif sub == "write":
            if len(tokens) < 4:
                return "Usage: file write <path> <content>"
            path = tokens[2]
            content = " ".join(tokens[3:])
            return file_write(path, content)
        elif sub == "delete":
            if len(tokens) < 3:
                return "Usage: file delete <path>"
            return file_delete(tokens[2])
        elif sub == "organize":
            if len(tokens) < 3:
                return "Usage: file organize <source_dir>"
            return file_organize(tokens[2])
        else:
            return f"Unknown file subcommand '{sub}'. Try: list, read, write, delete, organize"

    # --- email ---
    elif cmd == "email":
        if len(tokens) < 2:
            return "Usage: email send <to> <subject> <body>"
        sub = tokens[1].lower()
        if sub == "send":
            if len(tokens) < 5:
                return "Usage: email send <to> <subject> <body>"
            to = tokens[2]
            subject = tokens[3]
            body = " ".join(tokens[4:])
            return email_send(config, to, subject, body)
        else:
            return f"Unknown email subcommand '{sub}'. Try: send"

    # --- web ---
    elif cmd == "web":
        if len(tokens) < 2:
            return "Usage: web <scrape|search> <url|query>"
        sub = tokens[1].lower()
        if sub == "scrape":
            if len(tokens) < 3:
                return "Usage: web scrape <url>"
            return web_scrape(tokens[2])
        elif sub == "search":
            if len(tokens) < 3:
                return "Usage: web search <query>"
            query = " ".join(tokens[2:])
            return web_search(query)
        else:
            return f"Unknown web subcommand '{sub}'. Try: scrape, search"

    # --- shell ---
    elif cmd == "shell":
        if len(tokens) < 2:
            return "Usage: shell <command>"
        command = " ".join(tokens[1:])
        return shell_run(command)

    # --- system ---
    elif cmd == "system":
        if len(tokens) < 2:
            return "Usage: system info"
        sub = tokens[1].lower()
        if sub == "info":
            return system_info()
        else:
            return f"Unknown system subcommand '{sub}'. Try: info"

    # --- db ---
    elif cmd == "db":
        if len(tokens) < 2:
            return "Usage: db query <db_path> <sql>"
        sub = tokens[1].lower()
        if sub == "query":
            if len(tokens) < 4:
                return "Usage: db query <db_path> <sql>"
            db_path = tokens[2]
            sql = " ".join(tokens[3:])
            return db_query(db_path, sql)
        else:
            return f"Unknown db subcommand '{sub}'. Try: query"

    # --- help ---
    elif cmd == "help":
        return HELP_TEXT

    # --- quit/exit ---
    elif cmd in ("quit", "exit"):
        return "__EXIT__"

    else:
        return f"Unknown command '{cmd}'. Type 'help' for available commands."


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

BANNER = f"""
╔══════════════════════════════════════════════════════════╗
║          Grokputer Hybrid — Scarlett v{VERSION}             ║
║        Your professional AI assistant ecosystem          ║
║  Type 'help' for commands. Type 'quit' to exit.          ║
╚══════════════════════════════════════════════════════════╝
"""


def main() -> None:
    config = load_config()
    setup_logging(config)
    logger.info("Scarlett starting up — version %s", VERSION)

    name = config.get("name", "Scarlett")
    prompt = f"{name}> "

    print(BANNER)

    while True:
        try:
            raw = input(prompt).strip()
        except (KeyboardInterrupt, EOFError):
            print("\nGoodbye.")
            logger.info("Scarlett exiting via interrupt/EOF")
            break

        if not raw:
            continue

        tokens = raw.split()
        response = dispatch(tokens, config)

        if response == "__EXIT__":
            print("Goodbye.")
            logger.info("Scarlett exiting via quit command")
            break

        if response:
            print(response)


if __name__ == "__main__":
    main()
