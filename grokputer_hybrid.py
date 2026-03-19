#!/usr/bin/env python3
"""
grokputer_hybrid.py — Single honest professional AI assistant powered by X.AI Grok.

Features:
- Single coherent professional persona ("Scarlett")
- 15+ real, working tools with honest logging & verification
- OpenAI-compatible SDK → X.AI Grok endpoint
- REPL chat loop with persistent memory
- Every action logged and verified

Usage:
    python grokputer_hybrid.py

Config:  scarlett_config.json  (copy from example_scarlett_config.json)
Log:     scarlett.log
Memory:  scarlett_memory.json
"""

from __future__ import annotations

import datetime
import glob as _glob
import imaplib
import json
import logging
import os
import re
import shutil
import smtplib
import sqlite3
import subprocess
import sys
import time
import traceback
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from pathlib import Path
from typing import Any

# ──────────────────────────────────────────────────────────────────────────────
# Optional / heavy dependencies — graceful fallback
# ──────────────────────────────────────────────────────────────────────────────
try:
    import psutil
    PSUTIL_AVAILABLE = True
except ImportError:
    PSUTIL_AVAILABLE = False

try:
    from PIL import ImageGrab
    PIL_AVAILABLE = True
except ImportError:
    PIL_AVAILABLE = False

try:
    import pytesseract
    TESSERACT_AVAILABLE = True
except ImportError:
    TESSERACT_AVAILABLE = False

try:
    import requests
    from bs4 import BeautifulSoup
    SCRAPING_AVAILABLE = True
except ImportError:
    SCRAPING_AVAILABLE = False

try:
    import PyPDF2
    PYPDF2_AVAILABLE = True
except ImportError:
    PYPDF2_AVAILABLE = False

try:
    from selenium import webdriver
    from selenium.webdriver.chrome.options import Options as ChromeOptions
    from selenium.webdriver.chrome.service import Service as ChromeService
    from selenium.webdriver.common.by import By
    from selenium.webdriver.support import expected_conditions as EC
    from selenium.webdriver.support.ui import WebDriverWait
    try:
        from webdriver_manager.chrome import ChromeDriverManager
        WEBDRIVER_MANAGER = True
    except ImportError:
        WEBDRIVER_MANAGER = False
    SELENIUM_AVAILABLE = True
except ImportError:
    SELENIUM_AVAILABLE = False

try:
    from openai import OpenAI
    OPENAI_AVAILABLE = True
except ImportError:
    OPENAI_AVAILABLE = False
    print("ERROR: openai package not found. Run: pip install openai", file=sys.stderr)
    sys.exit(1)

try:
    import git as gitpython
    GITPYTHON_AVAILABLE = True
except ImportError:
    GITPYTHON_AVAILABLE = False

try:
    from github import Github as PyGithub
    PYGITHUB_AVAILABLE = True
except ImportError:
    PYGITHUB_AVAILABLE = False

# ──────────────────────────────────────────────────────────────────────────────
# Configuration
# ──────────────────────────────────────────────────────────────────────────────
CONFIG_FILE = Path("scarlett_config.json")
DEFAULT_CONFIG = {
    "xai_api_key": "",
    "xai_model": "grok-beta",
    "xai_base_url": "https://api.x.ai/v1",
    "proton_email": "lotsapoppa1@proton.me",
    "proton_password": "",
    "proton_smtp_host": "localhost",
    "proton_smtp_port": 1025,
    "proton_imap_host": "localhost",
    "proton_imap_port": 1143,
    "autonomy_mode": False,
    "log_file": "scarlett.log",
    "memory_file": "scarlett_memory.json",
    "screenshots_dir": "screenshots",
    "database_file": "scarlett.db",
    "shell_timeout": 60,
    "max_history": 100,
    "github_token": "",
    "github_username": "",
}


def load_config() -> dict:
    if CONFIG_FILE.exists():
        try:
            with open(CONFIG_FILE) as f:
                data = json.load(f)
            cfg = {**DEFAULT_CONFIG, **data}
            return cfg
        except json.JSONDecodeError as e:
            print(f"WARNING: Could not parse {CONFIG_FILE}: {e}", file=sys.stderr)
    return dict(DEFAULT_CONFIG)


CONFIG = load_config()

# ──────────────────────────────────────────────────────────────────────────────
# Logging
# ──────────────────────────────────────────────────────────────────────────────
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[
        logging.FileHandler(CONFIG.get("log_file", "scarlett.log")),
        logging.StreamHandler(sys.stdout),
    ],
)
logger = logging.getLogger("scarlett")


def _ts() -> str:
    return datetime.datetime.now().isoformat()


def _ok(message: str, result: Any = None) -> dict:
    payload = {"status": "success", "message": message, "timestamp": _ts()}
    if result is not None:
        payload["result"] = result
    logger.info("SUCCESS: %s", message)
    return payload


def _err(message: str, detail: str = "") -> dict:
    payload = {"status": "error", "message": message, "timestamp": _ts()}
    if detail:
        payload["detail"] = detail
    logger.error("ERROR: %s — %s", message, detail)
    return payload


# ──────────────────────────────────────────────────────────────────────────────
# Memory / History
# ──────────────────────────────────────────────────────────────────────────────
MEMORY_FILE = Path(CONFIG.get("memory_file", "scarlett_memory.json"))
MAX_HISTORY = int(CONFIG.get("max_history", 100))


def load_memory() -> list[dict]:
    if MEMORY_FILE.exists():
        try:
            with open(MEMORY_FILE) as f:
                return json.load(f)
        except (json.JSONDecodeError, OSError):
            pass
    return []


def save_memory(history: list[dict]) -> None:
    trimmed = history[-MAX_HISTORY:]
    try:
        with open(MEMORY_FILE, "w") as f:
            json.dump(trimmed, f, indent=2)
    except OSError as e:
        logger.warning("Could not save memory: %s", e)


# ──────────────────────────────────────────────────────────────────────────────
# Tool: File Operations
# ──────────────────────────────────────────────────────────────────────────────
def read_file(filepath: str) -> dict:
    """Read file contents and return them."""
    p = Path(filepath)
    logger.info("TOOL read_file: %s", filepath)
    if not p.exists():
        return _err(f"File not found: {filepath}")
    if not p.is_file():
        return _err(f"Path is not a file: {filepath}")
    try:
        content = p.read_text(encoding="utf-8", errors="replace")
        return _ok(f"Read {p.stat().st_size} bytes from {filepath}", {
            "filepath": str(p.resolve()),
            "content": content,
            "size_bytes": p.stat().st_size,
            "lines": content.count("\n") + 1,
        })
    except OSError as e:
        return _err(f"Could not read {filepath}", str(e))


def write_file(filepath: str, content: str) -> dict:
    """Create or overwrite a file with given content."""
    p = Path(filepath)
    logger.info("TOOL write_file: %s (%d chars)", filepath, len(content))
    try:
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(content, encoding="utf-8")
        exists_after = p.exists()
        return _ok(f"Wrote {len(content)} chars to {filepath}", {
            "filepath": str(p.resolve()),
            "size_bytes": p.stat().st_size,
            "file_exists": exists_after,
        })
    except OSError as e:
        return _err(f"Could not write {filepath}", str(e))


def delete_file(filepath: str) -> dict:
    """Delete a file."""
    p = Path(filepath)
    logger.info("TOOL delete_file: %s", filepath)
    if not p.exists():
        return _err(f"File not found: {filepath}")
    try:
        p.unlink()
        return _ok(f"Deleted {filepath}", {
            "filepath": str(p.resolve()),
            "file_exists": p.exists(),
        })
    except OSError as e:
        return _err(f"Could not delete {filepath}", str(e))


def list_files(directory: str = ".") -> dict:
    """List files in a directory."""
    p = Path(directory)
    logger.info("TOOL list_files: %s", directory)
    if not p.exists():
        return _err(f"Directory not found: {directory}")
    if not p.is_dir():
        return _err(f"Path is not a directory: {directory}")
    try:
        entries = []
        for item in sorted(p.iterdir()):
            stat = item.stat()
            entries.append({
                "name": item.name,
                "type": "directory" if item.is_dir() else "file",
                "size_bytes": stat.st_size if item.is_file() else None,
                "modified": datetime.datetime.fromtimestamp(stat.st_mtime).isoformat(),
            })
        return _ok(f"Listed {len(entries)} items in {directory}", {
            "directory": str(p.resolve()),
            "count": len(entries),
            "items": entries,
        })
    except OSError as e:
        return _err(f"Could not list {directory}", str(e))


def organize_files(source_dir: str, pattern: str = "*") -> dict:
    """Organize files matching a glob pattern into subdirectories by extension."""
    src = Path(source_dir)
    logger.info("TOOL organize_files: dir=%s pattern=%s", source_dir, pattern)
    if not src.is_dir():
        return _err(f"Directory not found: {source_dir}")
    moved = []
    errors = []
    for item in src.glob(pattern):
        if not item.is_file():
            continue
        ext = item.suffix.lstrip(".").lower() or "no_extension"
        dest_dir = src / ext
        dest_dir.mkdir(exist_ok=True)
        dest = dest_dir / item.name
        try:
            shutil.move(str(item), str(dest))
            moved.append({"from": str(item), "to": str(dest)})
        except OSError as e:
            errors.append({"file": str(item), "error": str(e)})
    return _ok(f"Organized {len(moved)} files from {source_dir}", {
        "moved": moved,
        "errors": errors,
        "moved_count": len(moved),
        "error_count": len(errors),
    })


# ──────────────────────────────────────────────────────────────────────────────
# Tool: Proton Mail
# ──────────────────────────────────────────────────────────────────────────────
def send_email(to: str, subject: str, body: str) -> dict:
    """Send an email via Proton Mail Bridge (SMTP localhost:1025)."""
    logger.info("TOOL send_email: to=%s subject=%s", to, subject)
    smtp_host = CONFIG.get("proton_smtp_host", "localhost")
    smtp_port = int(CONFIG.get("proton_smtp_port", 1025))
    from_addr = CONFIG.get("proton_email", "")
    password = CONFIG.get("proton_password", "")

    if not from_addr:
        return _err("Proton email not configured. Set proton_email in scarlett_config.json")

    msg = MIMEMultipart("alternative")
    msg["Subject"] = subject
    msg["From"] = from_addr
    msg["To"] = to
    msg.attach(MIMEText(body, "plain"))

    try:
        with smtplib.SMTP(smtp_host, smtp_port, timeout=15) as server:
            server.ehlo()
            if password:
                server.login(from_addr, password)
            server.sendmail(from_addr, [to], msg.as_string())
        return _ok(f"Email sent to {to}", {
            "to": to,
            "from": from_addr,
            "subject": subject,
            "smtp_host": smtp_host,
            "smtp_port": smtp_port,
            "delivered": True,
        })
    except Exception as e:
        return _err(f"Failed to send email to {to}", str(e))


def compose_email(to: str, subject: str, body: str) -> dict:
    """Compose an email draft without sending."""
    logger.info("TOOL compose_email: to=%s subject=%s", to, subject)
    draft = {
        "to": to,
        "from": CONFIG.get("proton_email", ""),
        "subject": subject,
        "body": body,
        "composed_at": _ts(),
    }
    return _ok(f"Composed email to {to} (not sent — call send_email to deliver)", draft)


def search_emails(query: str) -> dict:
    """Search inbox via Proton Mail Bridge (IMAP localhost:1143)."""
    logger.info("TOOL search_emails: query=%s", query)
    imap_host = CONFIG.get("proton_imap_host", "localhost")
    imap_port = int(CONFIG.get("proton_imap_port", 1143))
    email_addr = CONFIG.get("proton_email", "")
    password = CONFIG.get("proton_password", "")

    if not email_addr or not password:
        return _err("Proton credentials not configured")

    try:
        mail = imaplib.IMAP4(imap_host, imap_port)
        mail.login(email_addr, password)
        mail.select("INBOX")
        _, data = mail.search(None, f'SUBJECT "{query}"')
        ids = data[0].split() if data[0] else []
        results = []
        for uid in ids[-20:]:  # limit to 20 most recent
            _, msg_data = mail.fetch(uid, "(RFC822.SIZE RFC822.HEADER)")
            results.append({"uid": uid.decode(), "header": str(msg_data[0])[:200]})
        mail.logout()
        return _ok(f"Found {len(ids)} emails matching '{query}'", {
            "query": query,
            "total_matches": len(ids),
            "results": results,
        })
    except Exception as e:
        return _err(f"Email search failed", str(e))


# ──────────────────────────────────────────────────────────────────────────────
# Tool: Screenshots
# ──────────────────────────────────────────────────────────────────────────────
SCREENSHOTS_DIR = Path(CONFIG.get("screenshots_dir", "screenshots"))


def take_screenshot(filename: str | None = None) -> dict:
    """Capture a screenshot and save to screenshots/ directory."""
    logger.info("TOOL take_screenshot: filename=%s", filename)
    if not PIL_AVAILABLE:
        return _err("Pillow not installed. Run: pip install Pillow")

    SCREENSHOTS_DIR.mkdir(exist_ok=True)
    if not filename:
        filename = f"screenshot_{datetime.datetime.now().strftime('%Y%m%d_%H%M%S')}.png"
    filepath = SCREENSHOTS_DIR / filename

    try:
        img = ImageGrab.grab()
        img.save(str(filepath))
        return _ok(f"Screenshot saved to {filepath}", {
            "filepath": str(filepath.resolve()),
            "filename": filename,
            "size": f"{img.width}x{img.height}",
            "file_exists": filepath.exists(),
        })
    except Exception as e:
        return _err("Screenshot failed", str(e))


def ocr_screenshot(filepath: str) -> dict:
    """Extract text from an image using tesseract OCR."""
    logger.info("TOOL ocr_screenshot: %s", filepath)
    p = Path(filepath)
    if not p.exists():
        return _err(f"File not found: {filepath}")
    if not PIL_AVAILABLE:
        return _err("Pillow not installed. Run: pip install Pillow")
    if not TESSERACT_AVAILABLE:
        return _err("pytesseract not installed. Run: pip install pytesseract (and install tesseract-ocr)")
    try:
        from PIL import Image
        img = Image.open(str(p))
        text = pytesseract.image_to_string(img)
        return _ok(f"OCR extracted {len(text)} chars from {filepath}", {
            "filepath": str(p.resolve()),
            "text": text,
            "char_count": len(text),
        })
    except Exception as e:
        return _err("OCR failed", str(e))


# ──────────────────────────────────────────────────────────────────────────────
# Tool: Selenium Browser
# ──────────────────────────────────────────────────────────────────────────────
_browser_driver: Any = None  # module-level singleton


def open_browser(url: str, headless: bool = False) -> dict:
    """Open Chrome browser to a URL."""
    global _browser_driver
    logger.info("TOOL open_browser: url=%s headless=%s", url, headless)
    if not SELENIUM_AVAILABLE:
        return _err("Selenium not installed. Run: pip install selenium webdriver-manager")
    try:
        options = ChromeOptions()
        if headless:
            options.add_argument("--headless=new")
        options.add_argument("--no-sandbox")
        options.add_argument("--disable-dev-shm-usage")
        if WEBDRIVER_MANAGER:
            service = ChromeService(ChromeDriverManager().install())
            _browser_driver = webdriver.Chrome(service=service, options=options)
        else:
            _browser_driver = webdriver.Chrome(options=options)
        _browser_driver.get(url)
        title = _browser_driver.title
        return _ok(f"Opened browser to {url}", {
            "url": url,
            "title": title,
            "headless": headless,
        })
    except Exception as e:
        return _err(f"Failed to open browser to {url}", str(e))


def browser_click(xpath: str) -> dict:
    """Click an element in the browser by XPath."""
    logger.info("TOOL browser_click: xpath=%s", xpath)
    if _browser_driver is None:
        return _err("Browser not open. Call open_browser first.")
    try:
        element = WebDriverWait(_browser_driver, 10).until(
            EC.element_to_be_clickable((By.XPATH, xpath))
        )
        element.click()
        return _ok(f"Clicked element at xpath: {xpath}", {"xpath": xpath})
    except Exception as e:
        return _err(f"Click failed on xpath: {xpath}", str(e))


def browser_type(xpath: str, text: str) -> dict:
    """Type text into a browser element."""
    logger.info("TOOL browser_type: xpath=%s text=%s", xpath, text[:50])
    if _browser_driver is None:
        return _err("Browser not open. Call open_browser first.")
    try:
        element = WebDriverWait(_browser_driver, 10).until(
            EC.presence_of_element_located((By.XPATH, xpath))
        )
        element.clear()
        element.send_keys(text)
        return _ok(f"Typed text into element at xpath: {xpath}", {"xpath": xpath, "text_length": len(text)})
    except Exception as e:
        return _err(f"Type failed on xpath: {xpath}", str(e))


def browser_screenshot() -> dict:
    """Capture a screenshot of the current browser page."""
    logger.info("TOOL browser_screenshot")
    if _browser_driver is None:
        return _err("Browser not open. Call open_browser first.")
    SCREENSHOTS_DIR.mkdir(exist_ok=True)
    filename = f"browser_{datetime.datetime.now().strftime('%Y%m%d_%H%M%S')}.png"
    filepath = SCREENSHOTS_DIR / filename
    try:
        _browser_driver.save_screenshot(str(filepath))
        return _ok(f"Browser screenshot saved to {filepath}", {
            "filepath": str(filepath.resolve()),
            "filename": filename,
            "file_exists": filepath.exists(),
        })
    except Exception as e:
        return _err("Browser screenshot failed", str(e))


def browser_close() -> dict:
    """Close the browser."""
    global _browser_driver
    logger.info("TOOL browser_close")
    if _browser_driver is None:
        return _ok("Browser was already closed.")
    try:
        _browser_driver.quit()
        _browser_driver = None
        return _ok("Browser closed successfully.")
    except Exception as e:
        _browser_driver = None
        return _err("Error while closing browser", str(e))


# ──────────────────────────────────────────────────────────────────────────────
# Tool: PDF
# ──────────────────────────────────────────────────────────────────────────────
def extract_pdf_text(filepath: str) -> dict:
    """Extract all text from a PDF file."""
    logger.info("TOOL extract_pdf_text: %s", filepath)
    if not PYPDF2_AVAILABLE:
        return _err("PyPDF2 not installed. Run: pip install PyPDF2")
    p = Path(filepath)
    if not p.exists():
        return _err(f"File not found: {filepath}")
    try:
        reader = PyPDF2.PdfReader(str(p))
        pages_text = []
        for i, page in enumerate(reader.pages):
            pages_text.append({"page": i + 1, "text": page.extract_text() or ""})
        full_text = "\n".join(pt["text"] for pt in pages_text)
        return _ok(f"Extracted text from {len(reader.pages)} pages of {filepath}", {
            "filepath": str(p.resolve()),
            "page_count": len(reader.pages),
            "total_chars": len(full_text),
            "pages": pages_text,
            "full_text": full_text,
        })
    except Exception as e:
        return _err(f"PDF text extraction failed", str(e))


def merge_pdfs(file_list: list[str], output: str) -> dict:
    """Merge multiple PDF files into one."""
    logger.info("TOOL merge_pdfs: %d files → %s", len(file_list), output)
    if not PYPDF2_AVAILABLE:
        return _err("PyPDF2 not installed. Run: pip install PyPDF2")
    writer = PyPDF2.PdfWriter()
    for fp in file_list:
        p = Path(fp)
        if not p.exists():
            return _err(f"Input file not found: {fp}")
        reader = PyPDF2.PdfReader(str(p))
        for page in reader.pages:
            writer.add_page(page)
    out = Path(output)
    out.parent.mkdir(parents=True, exist_ok=True)
    try:
        with open(out, "wb") as f:
            writer.write(f)
        return _ok(f"Merged {len(file_list)} PDFs into {output}", {
            "output": str(out.resolve()),
            "input_files": file_list,
            "file_exists": out.exists(),
        })
    except Exception as e:
        return _err("PDF merge failed", str(e))


def split_pdf(filepath: str, pages: str) -> dict:
    """
    Split a PDF by page range.

    pages format: "1-3" → extract pages 1, 2, 3 (1-indexed).
    Output is saved as <name>_pages_<range>.pdf.
    """
    logger.info("TOOL split_pdf: %s pages=%s", filepath, pages)
    if not PYPDF2_AVAILABLE:
        return _err("PyPDF2 not installed. Run: pip install PyPDF2")
    p = Path(filepath)
    if not p.exists():
        return _err(f"File not found: {filepath}")
    try:
        match = re.match(r"(\d+)-(\d+)", pages.strip())
        if not match:
            return _err("Invalid pages format. Use '1-3' for pages 1 through 3.")
        start, end = int(match.group(1)), int(match.group(2))
        reader = PyPDF2.PdfReader(str(p))
        writer = PyPDF2.PdfWriter()
        for i in range(start - 1, min(end, len(reader.pages))):
            writer.add_page(reader.pages[i])
        out_name = p.stem + f"_pages_{start}-{end}.pdf"
        out = p.parent / out_name
        with open(out, "wb") as f:
            writer.write(f)
        return _ok(f"Split {filepath} pages {start}-{end} into {out}", {
            "output": str(out.resolve()),
            "source": str(p.resolve()),
            "pages_extracted": list(range(start, end + 1)),
            "file_exists": out.exists(),
        })
    except Exception as e:
        return _err("PDF split failed", str(e))


# ──────────────────────────────────────────────────────────────────────────────
# Tool: Web Scraping
# ──────────────────────────────────────────────────────────────────────────────
def scrape_html(url: str) -> dict:
    """Fetch the raw HTML of a web page."""
    logger.info("TOOL scrape_html: %s", url)
    if not SCRAPING_AVAILABLE:
        return _err("requests/beautifulsoup4 not installed. Run: pip install requests beautifulsoup4")
    try:
        resp = requests.get(url, timeout=20, headers={"User-Agent": "Grokputer/1.0"})
        resp.raise_for_status()
        return _ok(f"Scraped {len(resp.text)} chars from {url}", {
            "url": url,
            "status_code": resp.status_code,
            "html": resp.text,
            "content_length": len(resp.text),
        })
    except Exception as e:
        return _err(f"Scraping failed for {url}", str(e))


def parse_html(html: str, selector: str) -> dict:
    """Extract elements from HTML by CSS selector."""
    logger.info("TOOL parse_html: selector=%s", selector)
    if not SCRAPING_AVAILABLE:
        return _err("beautifulsoup4 not installed. Run: pip install beautifulsoup4")
    try:
        soup = BeautifulSoup(html, "html.parser")
        elements = soup.select(selector)
        results = [el.get_text(strip=True) for el in elements]
        return _ok(f"Found {len(elements)} elements matching '{selector}'", {
            "selector": selector,
            "count": len(elements),
            "elements": results[:50],  # cap at 50
        })
    except Exception as e:
        return _err(f"HTML parse failed for selector '{selector}'", str(e))


# ──────────────────────────────────────────────────────────────────────────────
# Tool: System Status
# ──────────────────────────────────────────────────────────────────────────────
def get_system_status() -> dict:
    """Return real-time CPU, memory, and disk usage."""
    logger.info("TOOL get_system_status")
    if not PSUTIL_AVAILABLE:
        return _err("psutil not installed. Run: pip install psutil")
    try:
        cpu = psutil.cpu_percent(interval=0.5)
        mem = psutil.virtual_memory()
        disk = psutil.disk_usage("/")
        return _ok("System status retrieved", {
            "cpu_percent": cpu,
            "memory": {
                "total_gb": round(mem.total / 1e9, 2),
                "used_gb": round(mem.used / 1e9, 2),
                "available_gb": round(mem.available / 1e9, 2),
                "percent": mem.percent,
            },
            "disk": {
                "total_gb": round(disk.total / 1e9, 2),
                "used_gb": round(disk.used / 1e9, 2),
                "free_gb": round(disk.free / 1e9, 2),
                "percent": disk.percent,
            },
        })
    except Exception as e:
        return _err("System status failed", str(e))


# ──────────────────────────────────────────────────────────────────────────────
# Tool: SQLite Database
# ──────────────────────────────────────────────────────────────────────────────
DB_FILE = CONFIG.get("database_file", "scarlett.db")


def _get_db_connection():
    return sqlite3.connect(DB_FILE)


def query_database(sql: str) -> dict:
    """Execute a SQL query against the local SQLite database."""
    logger.info("TOOL query_database: %s", sql[:120])
    sql_upper = sql.strip().upper()
    # Basic safety: allow all SQL but log writes
    is_write = any(sql_upper.startswith(kw) for kw in ("INSERT", "UPDATE", "DELETE", "DROP", "CREATE", "ALTER"))
    if is_write and not CONFIG.get("autonomy_mode", False):
        return _err("Write SQL blocked (autonomy_mode is off). Enable autonomy_mode in config to allow writes.")
    try:
        con = _get_db_connection()
        cur = con.cursor()
        cur.execute(sql)
        if sql_upper.startswith("SELECT"):
            rows = cur.fetchall()
            cols = [d[0] for d in cur.description] if cur.description else []
            con.close()
            return _ok(f"Query returned {len(rows)} rows", {
                "columns": cols,
                "rows": rows,
                "row_count": len(rows),
            })
        else:
            con.commit()
            affected = cur.rowcount
            con.close()
            return _ok(f"Query executed, {affected} rows affected", {"rows_affected": affected})
    except Exception as e:
        return _err("Database query failed", str(e))


def natural_language_query(question: str) -> dict:
    """
    Convert a natural-language question to SQL and execute it.

    Uses pattern matching for common queries; for advanced NL→SQL use a model.
    """
    logger.info("TOOL natural_language_query: %s", question)
    q = question.lower()
    # Heuristic patterns
    if "tables" in q or "list table" in q:
        sql = "SELECT name FROM sqlite_master WHERE type='table';"
    elif "count" in q:
        match = re.search(r"count.*?from\s+(\w+)", q)
        table = match.group(1) if match else None
        if table:
            sql = f"SELECT COUNT(*) FROM {table};"
        else:
            sql = "SELECT name FROM sqlite_master WHERE type='table';"
    elif re.search(r"show|select|get|fetch", q):
        match = re.search(r"from\s+(\w+)", q)
        table = match.group(1) if match else None
        sql = f"SELECT * FROM {table} LIMIT 50;" if table else "SELECT name FROM sqlite_master WHERE type='table';"
    else:
        sql = "SELECT name FROM sqlite_master WHERE type='table';"

    result = query_database(sql)
    result["natural_language_question"] = question
    result["generated_sql"] = sql
    return result


# ──────────────────────────────────────────────────────────────────────────────
# Tool: GitHub
# ──────────────────────────────────────────────────────────────────────────────
def clone_repo(repo_url: str, local_path: str) -> dict:
    """Clone a GitHub repository."""
    logger.info("TOOL clone_repo: %s → %s", repo_url, local_path)
    if not GITPYTHON_AVAILABLE:
        return _err("GitPython not installed. Run: pip install GitPython")
    dest = Path(local_path)
    if dest.exists():
        return _err(f"Destination already exists: {local_path}")
    try:
        gitpython.Repo.clone_from(repo_url, str(dest))
        return _ok(f"Cloned {repo_url} to {local_path}", {
            "repo_url": repo_url,
            "local_path": str(dest.resolve()),
            "directory_exists": dest.exists(),
        })
    except Exception as e:
        return _err(f"Clone failed for {repo_url}", str(e))


def push_to_repo(repo_path: str, message: str) -> dict:
    """Stage all changes, commit with message, and push."""
    logger.info("TOOL push_to_repo: path=%s msg=%s", repo_path, message)
    if not GITPYTHON_AVAILABLE:
        return _err("GitPython not installed. Run: pip install GitPython")
    if not CONFIG.get("autonomy_mode", False):
        return _err("Push blocked (autonomy_mode is off). Enable autonomy_mode in config to allow git pushes.")
    try:
        repo = gitpython.Repo(repo_path)
        repo.git.add(A=True)
        commit = repo.index.commit(message)
        origin = repo.remote("origin")
        push_info = origin.push()
        return _ok(f"Pushed to repo at {repo_path}", {
            "repo_path": str(Path(repo_path).resolve()),
            "commit_sha": commit.hexsha,
            "commit_message": message,
            "push_flags": str(push_info[0].flags) if push_info else "unknown",
        })
    except Exception as e:
        return _err(f"Push failed for {repo_path}", str(e))


def create_github_issue(repo_name: str, title: str, body: str) -> dict:
    """Create a GitHub issue."""
    logger.info("TOOL create_github_issue: repo=%s title=%s", repo_name, title)
    if not PYGITHUB_AVAILABLE:
        return _err("PyGithub not installed. Run: pip install PyGithub")
    token = CONFIG.get("github_token", "")
    if not token:
        return _err("GitHub token not configured. Set github_token in scarlett_config.json")
    try:
        gh = PyGithub(token)
        repo = gh.get_repo(repo_name)
        issue = repo.create_issue(title=title, body=body)
        return _ok(f"Created GitHub issue #{issue.number} in {repo_name}", {
            "repo": repo_name,
            "issue_number": issue.number,
            "title": title,
            "url": issue.html_url,
        })
    except Exception as e:
        return _err(f"Failed to create GitHub issue in {repo_name}", str(e))


# ──────────────────────────────────────────────────────────────────────────────
# Tool: Shell Execution
# ──────────────────────────────────────────────────────────────────────────────
def execute_shell(command: str) -> dict:
    """Execute a shell command (requires autonomy_mode=true)."""
    logger.info("TOOL execute_shell: %s", command)
    if not CONFIG.get("autonomy_mode", False):
        return _err("Shell execution blocked (autonomy_mode is off). Enable autonomy_mode in config to allow shell commands.")
    timeout = int(CONFIG.get("shell_timeout", 60))
    try:
        result = subprocess.run(
            command,
            shell=True,
            capture_output=True,
            text=True,
            timeout=timeout,
        )
        return _ok(f"Shell command executed: {command[:60]}", {
            "command": command,
            "stdout": result.stdout,
            "stderr": result.stderr,
            "returncode": result.returncode,
            "success": result.returncode == 0,
        })
    except subprocess.TimeoutExpired:
        return _err(f"Command timed out after {timeout}s: {command}")
    except Exception as e:
        return _err(f"Shell execution failed: {command}", str(e))


# ──────────────────────────────────────────────────────────────────────────────
# OpenAI Tool Definitions
# ──────────────────────────────────────────────────────────────────────────────
TOOL_DEFINITIONS = [
    {
        "type": "function",
        "function": {
            "name": "read_file",
            "description": "Read the contents of a file from disk.",
            "parameters": {
                "type": "object",
                "properties": {
                    "filepath": {"type": "string", "description": "Path to the file to read."},
                },
                "required": ["filepath"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "write_file",
            "description": "Create or overwrite a file with the given content.",
            "parameters": {
                "type": "object",
                "properties": {
                    "filepath": {"type": "string", "description": "Path to the file to write."},
                    "content": {"type": "string", "description": "Content to write to the file."},
                },
                "required": ["filepath", "content"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "delete_file",
            "description": "Delete a file from disk.",
            "parameters": {
                "type": "object",
                "properties": {
                    "filepath": {"type": "string", "description": "Path to the file to delete."},
                },
                "required": ["filepath"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "list_files",
            "description": "List files and directories in a given directory.",
            "parameters": {
                "type": "object",
                "properties": {
                    "directory": {"type": "string", "description": "Directory path to list. Defaults to current directory."},
                },
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "organize_files",
            "description": "Organize files in a directory into subdirectories by file extension.",
            "parameters": {
                "type": "object",
                "properties": {
                    "source_dir": {"type": "string", "description": "Directory to organize."},
                    "pattern": {"type": "string", "description": "Glob pattern to match files (default: '*')."},
                },
                "required": ["source_dir"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "send_email",
            "description": "Send an email via Proton Mail Bridge.",
            "parameters": {
                "type": "object",
                "properties": {
                    "to": {"type": "string", "description": "Recipient email address."},
                    "subject": {"type": "string", "description": "Email subject."},
                    "body": {"type": "string", "description": "Email body text."},
                },
                "required": ["to", "subject", "body"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "compose_email",
            "description": "Compose an email draft without sending it.",
            "parameters": {
                "type": "object",
                "properties": {
                    "to": {"type": "string", "description": "Recipient email address."},
                    "subject": {"type": "string", "description": "Email subject."},
                    "body": {"type": "string", "description": "Email body text."},
                },
                "required": ["to", "subject", "body"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "search_emails",
            "description": "Search inbox for emails matching a query string.",
            "parameters": {
                "type": "object",
                "properties": {
                    "query": {"type": "string", "description": "Search query string (matches subject)."},
                },
                "required": ["query"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "take_screenshot",
            "description": "Capture a screenshot of the current screen and save it to disk.",
            "parameters": {
                "type": "object",
                "properties": {
                    "filename": {"type": "string", "description": "Optional filename for the screenshot (default: auto-generated)."},
                },
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "ocr_screenshot",
            "description": "Extract text from an image file using OCR (tesseract required).",
            "parameters": {
                "type": "object",
                "properties": {
                    "filepath": {"type": "string", "description": "Path to the image file."},
                },
                "required": ["filepath"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "open_browser",
            "description": "Open Chrome browser to a URL.",
            "parameters": {
                "type": "object",
                "properties": {
                    "url": {"type": "string", "description": "URL to navigate to."},
                    "headless": {"type": "boolean", "description": "Run in headless mode (no visible window)."},
                },
                "required": ["url"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "browser_click",
            "description": "Click an element in the open browser by XPath.",
            "parameters": {
                "type": "object",
                "properties": {
                    "xpath": {"type": "string", "description": "XPath selector for the element to click."},
                },
                "required": ["xpath"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "browser_type",
            "description": "Type text into a browser element by XPath.",
            "parameters": {
                "type": "object",
                "properties": {
                    "xpath": {"type": "string", "description": "XPath selector for the element."},
                    "text": {"type": "string", "description": "Text to type."},
                },
                "required": ["xpath", "text"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "browser_screenshot",
            "description": "Capture a screenshot of the current browser page.",
            "parameters": {"type": "object", "properties": {}},
        },
    },
    {
        "type": "function",
        "function": {
            "name": "browser_close",
            "description": "Close the browser.",
            "parameters": {"type": "object", "properties": {}},
        },
    },
    {
        "type": "function",
        "function": {
            "name": "extract_pdf_text",
            "description": "Extract all text from a PDF file.",
            "parameters": {
                "type": "object",
                "properties": {
                    "filepath": {"type": "string", "description": "Path to the PDF file."},
                },
                "required": ["filepath"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "merge_pdfs",
            "description": "Merge multiple PDF files into one output PDF.",
            "parameters": {
                "type": "object",
                "properties": {
                    "file_list": {"type": "array", "items": {"type": "string"}, "description": "List of PDF file paths to merge."},
                    "output": {"type": "string", "description": "Output file path for the merged PDF."},
                },
                "required": ["file_list", "output"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "split_pdf",
            "description": "Split a PDF by page range (e.g. '1-3' extracts pages 1 through 3).",
            "parameters": {
                "type": "object",
                "properties": {
                    "filepath": {"type": "string", "description": "Path to the PDF file."},
                    "pages": {"type": "string", "description": "Page range, e.g. '1-3'."},
                },
                "required": ["filepath", "pages"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "scrape_html",
            "description": "Fetch the HTML content of a web page.",
            "parameters": {
                "type": "object",
                "properties": {
                    "url": {"type": "string", "description": "URL of the page to scrape."},
                },
                "required": ["url"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "parse_html",
            "description": "Extract elements from HTML using a CSS selector.",
            "parameters": {
                "type": "object",
                "properties": {
                    "html": {"type": "string", "description": "Raw HTML to parse."},
                    "selector": {"type": "string", "description": "CSS selector string."},
                },
                "required": ["html", "selector"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_system_status",
            "description": "Return current CPU, memory, and disk usage statistics.",
            "parameters": {"type": "object", "properties": {}},
        },
    },
    {
        "type": "function",
        "function": {
            "name": "query_database",
            "description": "Execute a SQL query against the local SQLite database.",
            "parameters": {
                "type": "object",
                "properties": {
                    "sql": {"type": "string", "description": "SQL query to execute."},
                },
                "required": ["sql"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "natural_language_query",
            "description": "Convert a natural-language question to SQL and execute it against the database.",
            "parameters": {
                "type": "object",
                "properties": {
                    "question": {"type": "string", "description": "Natural language question about the data."},
                },
                "required": ["question"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "clone_repo",
            "description": "Clone a GitHub repository to a local path.",
            "parameters": {
                "type": "object",
                "properties": {
                    "repo_url": {"type": "string", "description": "URL of the git repository."},
                    "local_path": {"type": "string", "description": "Local directory to clone into."},
                },
                "required": ["repo_url", "local_path"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "push_to_repo",
            "description": "Stage all changes, commit with a message, and push to origin (requires autonomy_mode).",
            "parameters": {
                "type": "object",
                "properties": {
                    "repo_path": {"type": "string", "description": "Local path to the git repository."},
                    "message": {"type": "string", "description": "Commit message."},
                },
                "required": ["repo_path", "message"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "create_github_issue",
            "description": "Create an issue on a GitHub repository.",
            "parameters": {
                "type": "object",
                "properties": {
                    "repo_name": {"type": "string", "description": "Repository in 'owner/repo' format."},
                    "title": {"type": "string", "description": "Issue title."},
                    "body": {"type": "string", "description": "Issue body / description."},
                },
                "required": ["repo_name", "title", "body"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "execute_shell",
            "description": "Execute a shell command on the host system (requires autonomy_mode=true in config).",
            "parameters": {
                "type": "object",
                "properties": {
                    "command": {"type": "string", "description": "Shell command to execute."},
                },
                "required": ["command"],
            },
        },
    },
]

# Map function names → callables
TOOL_MAP: dict[str, Any] = {
    "read_file": read_file,
    "write_file": write_file,
    "delete_file": delete_file,
    "list_files": list_files,
    "organize_files": organize_files,
    "send_email": send_email,
    "compose_email": compose_email,
    "search_emails": search_emails,
    "take_screenshot": take_screenshot,
    "ocr_screenshot": ocr_screenshot,
    "open_browser": open_browser,
    "browser_click": browser_click,
    "browser_type": browser_type,
    "browser_screenshot": browser_screenshot,
    "browser_close": browser_close,
    "extract_pdf_text": extract_pdf_text,
    "merge_pdfs": merge_pdfs,
    "split_pdf": split_pdf,
    "scrape_html": scrape_html,
    "parse_html": parse_html,
    "get_system_status": get_system_status,
    "query_database": query_database,
    "natural_language_query": natural_language_query,
    "clone_repo": clone_repo,
    "push_to_repo": push_to_repo,
    "create_github_issue": create_github_issue,
    "execute_shell": execute_shell,
}


# ──────────────────────────────────────────────────────────────────────────────
# System Prompt
# ──────────────────────────────────────────────────────────────────────────────
SYSTEM_PROMPT = """You are Scarlett, a professional and highly capable AI assistant built on X.AI Grok.

You have access to the following REAL, WORKING tools that you can call and that will actually execute:
- File operations: read, write, delete, list, organize files on disk
- Email: send, compose, and search emails via Proton Mail Bridge
- Screenshots: capture the screen and perform OCR text extraction
- Browser automation: open Chrome, click elements, type text, take screenshots
- PDF tools: extract text, merge, and split PDF documents
- Web scraping: fetch HTML pages and parse with CSS selectors
- System monitoring: real-time CPU, memory, and disk usage
- Database: execute SQL queries and answer natural-language database questions
- GitHub: clone repos, push commits, create issues
- Shell: execute shell commands (requires autonomy_mode to be enabled)

Important principles:
1. Only claim to do things that you actually have tools for.
2. When you perform an action, always report the actual result returned by the tool.
3. If a tool returns an error, honestly report it and explain the issue.
4. Never fabricate results — report exactly what the tool returned.
5. Confirm each completed action with the verification data from the tool (file paths, timestamps, etc.).

You are direct, professional, and helpful. Your responses are concise and focused on delivering results."""


# ──────────────────────────────────────────────────────────────────────────────
# Tool Execution
# ──────────────────────────────────────────────────────────────────────────────
def execute_tool_call(tool_call) -> str:
    """Execute a single tool call and return the JSON result string."""
    name = tool_call.function.name
    try:
        args = json.loads(tool_call.function.arguments or "{}")
    except json.JSONDecodeError:
        args = {}

    func = TOOL_MAP.get(name)
    if not func:
        result = _err(f"Unknown tool: {name}")
    else:
        try:
            result = func(**args)
        except TypeError as e:
            result = _err(f"Tool call error for {name}: {e}", traceback.format_exc())
        except Exception as e:
            result = _err(f"Unexpected error in {name}", str(e))

    return json.dumps(result, default=str)


# ──────────────────────────────────────────────────────────────────────────────
# Chat Loop
# ──────────────────────────────────────────────────────────────────────────────
def chat_loop() -> None:
    api_key = CONFIG.get("xai_api_key", "")
    if not api_key:
        print("\nERROR: xai_api_key not set in scarlett_config.json")
        print("Copy example_scarlett_config.json to scarlett_config.json and add your X.AI API key.\n")
        sys.exit(1)

    client = OpenAI(
        api_key=api_key,
        base_url=CONFIG.get("xai_base_url", "https://api.x.ai/v1"),
    )
    model = CONFIG.get("xai_model", "grok-beta")

    # Startup banner
    masked_key = api_key[:8] + "..." + api_key[-4:] if len(api_key) > 12 else "***"
    print("\n" + "=" * 60)
    print("  GROKPUTER — Hybrid Mode")
    print("=" * 60)
    print(f"  Provider : X.AI Grok ({CONFIG.get('xai_base_url', '')})")
    print(f"  Model    : {model}")
    print(f"  API Key  : {masked_key}")
    print(f"  Proton   : {CONFIG.get('proton_email', 'not configured')}")
    print(f"  Autonomy : {'ENABLED' if CONFIG.get('autonomy_mode') else 'disabled'}")
    print(f"  Log      : {CONFIG.get('log_file', 'scarlett.log')}")
    print(f"  DB       : {CONFIG.get('database_file', 'scarlett.db')}")
    print("=" * 60)
    print("  Type 'quit' or 'exit' to stop.")
    print("  Type 'status' to see system info.")
    print("  Type 'clear' to clear conversation history.\n")

    history = load_memory()

    while True:
        try:
            user_input = input("User: ").strip()
        except (EOFError, KeyboardInterrupt):
            print("\nGoodbye!")
            break

        if not user_input:
            continue

        cmd = user_input.lower()
        if cmd in ("quit", "exit"):
            print("Goodbye!")
            break
        if cmd == "clear":
            history = []
            print("Scarlett: Conversation history cleared.\n")
            continue
        if cmd == "status":
            r = get_system_status()
            print(f"Scarlett: {json.dumps(r, indent=2, default=str)}\n")
            continue

        history.append({"role": "user", "content": user_input})

        messages = [{"role": "system", "content": SYSTEM_PROMPT}] + history

        try:
            # First API call
            response = client.chat.completions.create(
                model=model,
                messages=messages,
                tools=TOOL_DEFINITIONS,
                tool_choice="auto",
            )

            # Agentic tool-call loop
            while response.choices[0].finish_reason == "tool_calls":
                msg = response.choices[0].message
                messages.append(msg)

                tool_results = []
                for tc in msg.tool_calls:
                    result_str = execute_tool_call(tc)
                    tool_results.append({
                        "role": "tool",
                        "tool_call_id": tc.id,
                        "content": result_str,
                    })

                messages.extend(tool_results)

                # Follow-up call with tool results
                response = client.chat.completions.create(
                    model=model,
                    messages=messages,
                    tools=TOOL_DEFINITIONS,
                    tool_choice="auto",
                )

            assistant_reply = response.choices[0].message.content or ""
            print(f"\nScarlett: {assistant_reply}\n")
            history.append({"role": "assistant", "content": assistant_reply})
            save_memory(history)

        except KeyboardInterrupt:
            print("\nInterrupted. Type 'quit' to exit.\n")
        except Exception as e:
            print(f"\nScarlett: Error communicating with X.AI API: {e}\n")
            logger.error("API error: %s", traceback.format_exc())


# ──────────────────────────────────────────────────────────────────────────────
# Entry Point
# ──────────────────────────────────────────────────────────────────────────────
if __name__ == "__main__":
    chat_loop()
