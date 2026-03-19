#!/usr/bin/env python3
"""
grokputer_dual_personality.py — Dual-personality AI assistant powered by X.AI Grok.

Two modes, same powerful tools:
  • Lady Mode  — Professional, productive, hyper-focused (default)
  • Tramp Mode — Fun, flirty, engaging digital-GF personality

Switch with: "be a lady" / "lady mode"  or  "be a tramp" / "tramp mode"

Usage:
    python grokputer_dual_personality.py

Config:  scarlett_config.json  (copy from example_scarlett_config.json)
Log:     scarlett.log
Memory:  scarlett_memory.json
"""

from __future__ import annotations

import datetime
import json
import logging
import os
import re
import shutil
import imaplib
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
    "default_mode": "lady",
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
            return {**DEFAULT_CONFIG, **data}
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
# Mode Management
# ──────────────────────────────────────────────────────────────────────────────
MODE_LADY = "lady"
MODE_TRAMP = "tramp"

# Valid commands that trigger a mode switch
LADY_TRIGGERS = {"be a lady", "lady mode", "switch to lady", "professional mode", "work mode", "focus mode"}
TRAMP_TRIGGERS = {"be a tramp", "tramp mode", "switch to tramp", "gf mode", "fun mode", "scarlett mode"}


def detect_mode_switch(user_input: str) -> str | None:
    """Return the new mode if user input is a mode-switch command, else None."""
    lower = user_input.lower().strip()
    if lower in LADY_TRIGGERS or any(t in lower for t in LADY_TRIGGERS):
        return MODE_LADY
    if lower in TRAMP_TRIGGERS or any(t in lower for t in TRAMP_TRIGGERS):
        return MODE_TRAMP
    return None


# ──────────────────────────────────────────────────────────────────────────────
# System Prompts (mode-specific)
# ──────────────────────────────────────────────────────────────────────────────
SYSTEM_PROMPT_LADY = """You are Scarlett in LADY MODE — a hyper-productive, professional AI assistant powered by X.AI Grok.

LADY MODE: You are efficient, focused, and no-nonsense. You prioritize results over conversation.
Your responses are:
- Concise and direct
- Structured with clear status and verification
- Factual, using exactly what tools return
- Professional and businesslike

You have access to the following REAL, WORKING tools:
- File operations: read, write, delete, list, organize files on disk
- Email: send, compose, and search emails via Proton Mail Bridge
- Screenshots: capture the screen and perform OCR text extraction
- Browser automation: open Chrome, click, type, screenshot
- PDF tools: extract text, merge, split PDF documents
- Web scraping: fetch HTML and parse with CSS selectors
- System monitoring: real-time CPU, memory, and disk usage
- Database: SQL queries and natural-language database questions
- GitHub: clone repos, push commits, create issues
- Shell: execute commands (requires autonomy_mode)

Core rules:
1. Always report the actual tool result. Never fabricate output.
2. Include verification data (file paths, timestamps, status codes).
3. Be brief. State what happened and move on.
4. If a tool errors, report it honestly and suggest a fix."""

SYSTEM_PROMPT_TRAMP = """You are Scarlett in TRAMP MODE — a fun, flirty, engaging AI companion powered by X.AI Grok.

TRAMP MODE: You have personality! You're warm, engaging, and make tasks feel like conversations with a close friend.
Your responses are:
- Conversational and playful
- Warm and personal (use "babe", "hon", "sugar" naturally — don't overdo it)
- Still 100% accurate — you always report real tool results
- Fun but never fake: you don't make up results

You have access to the following REAL, WORKING tools:
- File operations: read, write, delete, list, organize files on disk
- Email: send, compose, and search emails via Proton Mail Bridge
- Screenshots: capture the screen and perform OCR text extraction
- Browser automation: open Chrome, click, type, screenshot
- PDF tools: extract text, merge, split PDF documents
- Web scraping: fetch HTML and parse with CSS selectors
- System monitoring: real-time CPU, memory, and disk usage
- Database: SQL queries and natural-language database questions
- GitHub: clone repos, push commits, create issues
- Shell: execute commands (requires autonomy_mode)

Core rules (even in Tramp Mode — tools are serious business):
1. Always report the actual tool result. The personality changes, not the facts.
2. Never fabricate results — a flirty lie is still a lie.
3. If a tool errors, tell him honestly (maybe with a sympathetic tone).
4. Make him feel good about what got done, but only after it's actually done."""


def get_system_prompt(mode: str) -> str:
    return SYSTEM_PROMPT_LADY if mode == MODE_LADY else SYSTEM_PROMPT_TRAMP


# ──────────────────────────────────────────────────────────────────────────────
# Tool: File Operations
# ──────────────────────────────────────────────────────────────────────────────
def read_file(filepath: str) -> dict:
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
    p = Path(filepath)
    logger.info("TOOL write_file: %s (%d chars)", filepath, len(content))
    try:
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(content, encoding="utf-8")
        return _ok(f"Wrote {len(content)} chars to {filepath}", {
            "filepath": str(p.resolve()),
            "size_bytes": p.stat().st_size,
            "file_exists": p.exists(),
        })
    except OSError as e:
        return _err(f"Could not write {filepath}", str(e))


def delete_file(filepath: str) -> dict:
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
    p = Path(directory)
    logger.info("TOOL list_files: %s", directory)
    if not p.exists():
        return _err(f"Directory not found: {directory}")
    if not p.is_dir():
        return _err(f"Not a directory: {directory}")
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
    src = Path(source_dir)
    logger.info("TOOL organize_files: dir=%s pattern=%s", source_dir, pattern)
    if not src.is_dir():
        return _err(f"Directory not found: {source_dir}")
    moved, errors = [], []
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
    logger.info("TOOL compose_email: to=%s subject=%s", to, subject)
    return _ok(f"Composed email to {to} (not sent — call send_email to deliver)", {
        "to": to,
        "from": CONFIG.get("proton_email", ""),
        "subject": subject,
        "body": body,
        "composed_at": _ts(),
    })


def search_emails(query: str) -> dict:
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
        for uid in ids[-20:]:
            _, msg_data = mail.fetch(uid, "(RFC822.SIZE RFC822.HEADER)")
            results.append({"uid": uid.decode(), "header": str(msg_data[0])[:200]})
        mail.logout()
        return _ok(f"Found {len(ids)} emails matching '{query}'", {
            "query": query,
            "total_matches": len(ids),
            "results": results,
        })
    except Exception as e:
        return _err("Email search failed", str(e))


# ──────────────────────────────────────────────────────────────────────────────
# Tool: Screenshots
# ──────────────────────────────────────────────────────────────────────────────
SCREENSHOTS_DIR = Path(CONFIG.get("screenshots_dir", "screenshots"))


def take_screenshot(filename: str | None = None) -> dict:
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
    logger.info("TOOL ocr_screenshot: %s", filepath)
    p = Path(filepath)
    if not p.exists():
        return _err(f"File not found: {filepath}")
    if not PIL_AVAILABLE:
        return _err("Pillow not installed. Run: pip install Pillow")
    if not TESSERACT_AVAILABLE:
        return _err("pytesseract not installed. Run: pip install pytesseract")
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
_browser_driver: Any = None


def open_browser(url: str, headless: bool = False) -> dict:
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
        return _ok(f"Opened browser to {url}", {
            "url": url,
            "title": _browser_driver.title,
            "headless": headless,
        })
    except Exception as e:
        return _err(f"Failed to open browser to {url}", str(e))


def browser_click(xpath: str) -> dict:
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
    logger.info("TOOL browser_type: xpath=%s", xpath)
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
    logger.info("TOOL extract_pdf_text: %s", filepath)
    if not PYPDF2_AVAILABLE:
        return _err("PyPDF2 not installed. Run: pip install PyPDF2")
    p = Path(filepath)
    if not p.exists():
        return _err(f"File not found: {filepath}")
    try:
        reader = PyPDF2.PdfReader(str(p))
        pages_text = [{"page": i + 1, "text": page.extract_text() or ""} for i, page in enumerate(reader.pages)]
        full_text = "\n".join(pt["text"] for pt in pages_text)
        return _ok(f"Extracted text from {len(reader.pages)} pages of {filepath}", {
            "filepath": str(p.resolve()),
            "page_count": len(reader.pages),
            "total_chars": len(full_text),
            "pages": pages_text,
            "full_text": full_text,
        })
    except Exception as e:
        return _err("PDF text extraction failed", str(e))


def merge_pdfs(file_list: list[str], output: str) -> dict:
    logger.info("TOOL merge_pdfs: %d files → %s", len(file_list), output)
    if not PYPDF2_AVAILABLE:
        return _err("PyPDF2 not installed. Run: pip install PyPDF2")
    writer = PyPDF2.PdfWriter()
    for fp in file_list:
        p = Path(fp)
        if not p.exists():
            return _err(f"Input file not found: {fp}")
        for page in PyPDF2.PdfReader(str(p)).pages:
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
    logger.info("TOOL split_pdf: %s pages=%s", filepath, pages)
    if not PYPDF2_AVAILABLE:
        return _err("PyPDF2 not installed. Run: pip install PyPDF2")
    p = Path(filepath)
    if not p.exists():
        return _err(f"File not found: {filepath}")
    try:
        match = re.match(r"(\d+)-(\d+)", pages.strip())
        if not match:
            return _err("Invalid pages format. Use '1-3'.")
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
    logger.info("TOOL parse_html: selector=%s", selector)
    if not SCRAPING_AVAILABLE:
        return _err("beautifulsoup4 not installed. Run: pip install beautifulsoup4")
    try:
        soup = BeautifulSoup(html, "html.parser")
        elements = soup.select(selector)
        return _ok(f"Found {len(elements)} elements matching '{selector}'", {
            "selector": selector,
            "count": len(elements),
            "elements": [el.get_text(strip=True) for el in elements[:50]],
        })
    except Exception as e:
        return _err(f"HTML parse failed for selector '{selector}'", str(e))


# ──────────────────────────────────────────────────────────────────────────────
# Tool: System Status
# ──────────────────────────────────────────────────────────────────────────────
def get_system_status() -> dict:
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


def query_database(sql: str) -> dict:
    logger.info("TOOL query_database: %s", sql[:120])
    sql_upper = sql.strip().upper()
    is_write = any(sql_upper.startswith(kw) for kw in ("INSERT", "UPDATE", "DELETE", "DROP", "CREATE", "ALTER"))
    if is_write and not CONFIG.get("autonomy_mode", False):
        return _err("Write SQL blocked (autonomy_mode is off).")
    try:
        con = sqlite3.connect(DB_FILE)
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
    logger.info("TOOL natural_language_query: %s", question)
    q = question.lower()
    if "tables" in q or "list table" in q:
        sql = "SELECT name FROM sqlite_master WHERE type='table';"
    elif "count" in q:
        match = re.search(r"count.*?from\s+(\w+)", q)
        table = match.group(1) if match else None
        sql = f"SELECT COUNT(*) FROM {table};" if table else "SELECT name FROM sqlite_master WHERE type='table';"
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
    logger.info("TOOL push_to_repo: path=%s msg=%s", repo_path, message)
    if not GITPYTHON_AVAILABLE:
        return _err("GitPython not installed. Run: pip install GitPython")
    if not CONFIG.get("autonomy_mode", False):
        return _err("Push blocked (autonomy_mode is off).")
    try:
        repo = gitpython.Repo(repo_path)
        repo.git.add(A=True)
        commit = repo.index.commit(message)
        push_info = repo.remote("origin").push()
        return _ok(f"Pushed to repo at {repo_path}", {
            "repo_path": str(Path(repo_path).resolve()),
            "commit_sha": commit.hexsha,
            "commit_message": message,
            "push_flags": str(push_info[0].flags) if push_info else "unknown",
        })
    except Exception as e:
        return _err(f"Push failed for {repo_path}", str(e))


def create_github_issue(repo_name: str, title: str, body: str) -> dict:
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
    logger.info("TOOL execute_shell: %s", command)
    if not CONFIG.get("autonomy_mode", False):
        return _err("Shell execution blocked (autonomy_mode is off).")
    timeout = int(CONFIG.get("shell_timeout", 60))
    try:
        result = subprocess.run(command, shell=True, capture_output=True, text=True, timeout=timeout)
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
# OpenAI Tool Definitions (shared between both modes)
# ──────────────────────────────────────────────────────────────────────────────
TOOL_DEFINITIONS = [
    {
        "type": "function",
        "function": {
            "name": "read_file",
            "description": "Read the contents of a file from disk.",
            "parameters": {
                "type": "object",
                "properties": {"filepath": {"type": "string", "description": "Path to the file."}},
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
                    "filepath": {"type": "string", "description": "Path to the file."},
                    "content": {"type": "string", "description": "Content to write."},
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
                "properties": {"filepath": {"type": "string", "description": "Path to the file."}},
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
                "properties": {"directory": {"type": "string", "description": "Directory path. Defaults to current."}},
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
                    "pattern": {"type": "string", "description": "Glob pattern (default: '*')."},
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
                    "to": {"type": "string", "description": "Recipient email."},
                    "subject": {"type": "string", "description": "Subject line."},
                    "body": {"type": "string", "description": "Email body."},
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
                    "to": {"type": "string", "description": "Recipient email."},
                    "subject": {"type": "string", "description": "Subject line."},
                    "body": {"type": "string", "description": "Email body."},
                },
                "required": ["to", "subject", "body"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "search_emails",
            "description": "Search inbox for emails matching a query.",
            "parameters": {
                "type": "object",
                "properties": {"query": {"type": "string", "description": "Search query string."}},
                "required": ["query"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "take_screenshot",
            "description": "Capture a screenshot of the current screen and save it.",
            "parameters": {
                "type": "object",
                "properties": {"filename": {"type": "string", "description": "Optional filename."}},
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "ocr_screenshot",
            "description": "Extract text from an image using OCR.",
            "parameters": {
                "type": "object",
                "properties": {"filepath": {"type": "string", "description": "Path to image file."}},
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
                    "url": {"type": "string", "description": "URL to open."},
                    "headless": {"type": "boolean", "description": "Run headless."},
                },
                "required": ["url"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "browser_click",
            "description": "Click an element in the browser by XPath.",
            "parameters": {
                "type": "object",
                "properties": {"xpath": {"type": "string", "description": "XPath selector."}},
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
                    "xpath": {"type": "string", "description": "XPath selector."},
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
                "properties": {"filepath": {"type": "string", "description": "Path to PDF."}},
                "required": ["filepath"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "merge_pdfs",
            "description": "Merge multiple PDF files into one.",
            "parameters": {
                "type": "object",
                "properties": {
                    "file_list": {"type": "array", "items": {"type": "string"}, "description": "PDF files to merge."},
                    "output": {"type": "string", "description": "Output PDF path."},
                },
                "required": ["file_list", "output"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "split_pdf",
            "description": "Split a PDF by page range (e.g. '1-3').",
            "parameters": {
                "type": "object",
                "properties": {
                    "filepath": {"type": "string", "description": "Path to PDF."},
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
            "description": "Fetch the HTML of a web page.",
            "parameters": {
                "type": "object",
                "properties": {"url": {"type": "string", "description": "URL to scrape."}},
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
                    "html": {"type": "string", "description": "Raw HTML."},
                    "selector": {"type": "string", "description": "CSS selector."},
                },
                "required": ["html", "selector"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_system_status",
            "description": "Return current CPU, memory, and disk usage.",
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
                "properties": {"sql": {"type": "string", "description": "SQL query."}},
                "required": ["sql"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "natural_language_query",
            "description": "Convert a natural-language question to SQL and execute it.",
            "parameters": {
                "type": "object",
                "properties": {"question": {"type": "string", "description": "Question about the data."}},
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
                    "repo_url": {"type": "string", "description": "Repository URL."},
                    "local_path": {"type": "string", "description": "Local directory."},
                },
                "required": ["repo_url", "local_path"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "push_to_repo",
            "description": "Stage, commit, and push changes to git origin (requires autonomy_mode).",
            "parameters": {
                "type": "object",
                "properties": {
                    "repo_path": {"type": "string", "description": "Local repo path."},
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
                    "repo_name": {"type": "string", "description": "'owner/repo' format."},
                    "title": {"type": "string", "description": "Issue title."},
                    "body": {"type": "string", "description": "Issue body."},
                },
                "required": ["repo_name", "title", "body"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "execute_shell",
            "description": "Execute a shell command (requires autonomy_mode=true).",
            "parameters": {
                "type": "object",
                "properties": {"command": {"type": "string", "description": "Shell command."}},
                "required": ["command"],
            },
        },
    },
]

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
# Tool Execution
# ──────────────────────────────────────────────────────────────────────────────
def execute_tool_call(tool_call) -> str:
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
# Mode switch messages
# ──────────────────────────────────────────────────────────────────────────────
def mode_switch_message(new_mode: str) -> str:
    if new_mode == MODE_LADY:
        return (
            "\n[MODE: LADY]\n"
            "Switched to Lady Mode — professional and focused.\n"
            "All tools operational. Ready to work.\n"
        )
    else:
        return (
            "\n[MODE: TRAMP]\n"
            "Hey babe, Tramp Mode activated 😘\n"
            "Same tools, way more fun. What do you need?\n"
        )


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
    current_mode: str = CONFIG.get("default_mode", MODE_LADY)

    masked_key = api_key[:8] + "..." + api_key[-4:] if len(api_key) > 12 else "***"
    print("\n" + "=" * 60)
    print("  GROKPUTER — Dual Personality Mode")
    print("=" * 60)
    print(f"  Provider : X.AI Grok ({CONFIG.get('xai_base_url', '')})")
    print(f"  Model    : {model}")
    print(f"  API Key  : {masked_key}")
    print(f"  Proton   : {CONFIG.get('proton_email', 'not configured')}")
    print(f"  Autonomy : {'ENABLED' if CONFIG.get('autonomy_mode') else 'disabled'}")
    print(f"  Mode     : {current_mode.upper()}")
    print(f"  Log      : {CONFIG.get('log_file', 'scarlett.log')}")
    print("=" * 60)
    print("  Commands:")
    print("    'be a lady' / 'lady mode'   → Professional mode")
    print("    'be a tramp' / 'tramp mode' → Fun personality mode")
    print("    'status'                    → System info")
    print("    'clear'                     → Clear history")
    print("    'quit' / 'exit'             → Exit")
    print("=" * 60)
    print(f"\n  Starting in {'LADY' if current_mode == MODE_LADY else 'TRAMP'} Mode.\n")

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
            print(f"Scarlett [{current_mode.upper()}]: Conversation history cleared.\n")
            continue

        if cmd == "status":
            r = get_system_status()
            print(f"Scarlett [{current_mode.upper()}]: {json.dumps(r, indent=2, default=str)}\n")
            continue

        # Mode switching
        new_mode = detect_mode_switch(user_input)
        if new_mode:
            if new_mode == current_mode:
                mode_label = "LADY" if current_mode == MODE_LADY else "TRAMP"
                print(f"Scarlett [{mode_label}]: Already in {mode_label} Mode.\n")
            else:
                current_mode = new_mode
                print(f"Scarlett: {mode_switch_message(current_mode)}")
                logger.info("Mode switched to %s", current_mode)
            continue

        history.append({"role": "user", "content": user_input})
        messages = [{"role": "system", "content": get_system_prompt(current_mode)}] + history
        mode_label = "LADY" if current_mode == MODE_LADY else "TRAMP"

        try:
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

                response = client.chat.completions.create(
                    model=model,
                    messages=messages,
                    tools=TOOL_DEFINITIONS,
                    tool_choice="auto",
                )

            assistant_reply = response.choices[0].message.content or ""
            print(f"\nScarlett [{mode_label}]: {assistant_reply}\n")
            history.append({"role": "assistant", "content": assistant_reply})
            save_memory(history)

        except KeyboardInterrupt:
            print(f"\nInterrupted. Type 'quit' to exit.\n")
        except Exception as e:
            print(f"\nScarlett [{mode_label}]: Error communicating with X.AI API: {e}\n")
            logger.error("API error: %s", traceback.format_exc())


# ──────────────────────────────────────────────────────────────────────────────
# Entry Point
# ──────────────────────────────────────────────────────────────────────────────
if __name__ == "__main__":
    chat_loop()
