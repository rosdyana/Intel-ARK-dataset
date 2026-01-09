from __future__ import annotations

import argparse
import csv
import random
import re
import sqlite3
import sys
import time
from contextlib import closing
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterable
from urllib.parse import urljoin

from playwright.sync_api import Browser, Page, Request, sync_playwright


def goto_with_retry(page: Page, url: str, *, attempts: int = 3, timeout_ms: int = 120000) -> None:
    last_err: Exception | None = None
    for attempt in range(1, attempts + 1):
        try:
            page.goto(url, wait_until="domcontentloaded", timeout=timeout_ms)
            return
        except Exception as e:
            last_err = e
            if attempt < attempts:
                time.sleep(2.0 * attempt)
                continue
            raise


def wait_for_ark_ready(page: Page) -> None:
    page.wait_for_selector(
        'div.product-categories[data-parent-panel-key="Processors"]',
        timeout=60000,
    )


def wait_for_specs_ready(page: Page) -> None:
    page.wait_for_selector("div.tab-pane#specifications section.upe-tech-spec", timeout=60000)

BASE_URL = "https://www.intel.com"
ARK_PROCESSORS_URL = "https://www.intel.com/content/www/us/en/ark.html#@Processors"

SKU_RE = re.compile(r"/products/sku/(\d+)/")


@dataclass(frozen=True)
class SeriesLink:
    category: str
    family: str
    url: str


@dataclass(frozen=True)
class SkuLink:
    sku: str
    product_name: str
    category: str
    family: str
    spec_url: str


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def normalize_text(value: str) -> str:
    return " ".join(value.replace("\xa0", " ").split()).strip()


def to_abs_url(href: str) -> str:
    return urljoin(BASE_URL, href)


def ensure_db(db_path: Path) -> None:
    with closing(sqlite3.connect(db_path)) as conn:
        conn.execute("PRAGMA journal_mode=WAL")
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS discovered_skus (
              sku TEXT PRIMARY KEY,
              category TEXT NOT NULL,
              family TEXT NOT NULL,
              spec_url TEXT NOT NULL,
              product_name TEXT
            )
            """
        )
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS scraped_skus (
              sku TEXT PRIMARY KEY,
              scraped_at TEXT NOT NULL,
              status TEXT NOT NULL,
              last_error TEXT
            )
            """
        )
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS discovered_series (
              url TEXT PRIMARY KEY,
              category TEXT NOT NULL,
              family TEXT NOT NULL
            )
            """
        )
        conn.commit()


def load_done_skus(conn: sqlite3.Connection) -> set[str]:
    rows = conn.execute("SELECT sku FROM scraped_skus WHERE status = 'ok'").fetchall()
    return {row[0] for row in rows}


def load_failed_skus(conn: sqlite3.Connection) -> set[str]:
    rows = conn.execute("SELECT sku FROM scraped_skus WHERE status = 'error'").fetchall()
    return {row[0] for row in rows}


def store_series(conn: sqlite3.Connection, series: Iterable[SeriesLink]) -> None:
    conn.executemany(
        "INSERT OR IGNORE INTO discovered_series(url, category, family) VALUES(?, ?, ?)",
        [(s.url, s.category, s.family) for s in series],
    )
    conn.commit()


def store_skus(conn: sqlite3.Connection, skus: Iterable[SkuLink]) -> None:
    # A SKU can appear in multiple families/categories; we keep the first seen mapping.
    conn.executemany(
        """
        INSERT OR IGNORE INTO discovered_skus(sku, category, family, spec_url, product_name)
        VALUES(?, ?, ?, ?, ?)
        """,
        [(s.sku, s.category, s.family, s.spec_url, s.product_name) for s in skus],
    )
    conn.commit()


def mark_sku(conn: sqlite3.Connection, sku: str, status: str, error: str | None = None) -> None:
    conn.execute(
        """
        INSERT OR REPLACE INTO scraped_skus(sku, scraped_at, status, last_error)
        VALUES(?, ?, ?, ?)
        """,
        (sku, utc_now_iso(), status, error),
    )
    conn.commit()


def configure_console_utf8() -> None:
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except Exception:
        pass


def should_block_request(request: Request) -> bool:
    rt = request.resource_type
    if rt in {"image", "media", "font"}:
        return True
    return False


def new_page(browser: Browser, storage_state: Path | None, headless: bool) -> Page:
    context = browser.new_context(
        locale="en-US",
        timezone_id="America/Los_Angeles",
        user_agent=(
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
            "AppleWebKit/537.36 (KHTML, like Gecko) "
            "Chrome/120.0.0.0 Safari/537.36"
        ),
        storage_state=str(storage_state) if storage_state and storage_state.exists() else None,
    )
    page = context.new_page()
    page.route("**/*", lambda route, req: route.abort() if should_block_request(req) else route.continue_())
    if not headless:
        page.set_viewport_size({"width": 1280, "height": 720})
    return page


def polite_sleep(min_s: float = 0.6, max_s: float = 1.6) -> None:
    time.sleep(random.uniform(min_s, max_s))


def discover_processor_categories(page: Page) -> list[str]:
    goto_with_retry(page, ARK_PROCESSORS_URL)
    wait_for_ark_ready(page)

    category_names = page.eval_on_selector_all(
        'div.product-categories[data-parent-panel-key="Processors"] div.product-category span.name',
        "els => els.map(e => e.textContent)",
    )
    return [normalize_text(n) for n in category_names if n]


def discover_series_for_category(page: Page, category_name: str) -> list[SeriesLink]:
    goto_with_retry(page, ARK_PROCESSORS_URL)
    wait_for_ark_ready(page)

    # Click category tile inside the Processors panel (avoid header/nav duplicates).
    tile = page.locator(
        "div.product-categories[data-parent-panel-key=\"Processors\"] span.name:has-text(\""
        + category_name
        + "\")"
    ).first
    tile.click()

    # After click, Intel toggles visibility on a matching "div.products.processors" panel.
    page.wait_for_timeout(800)

    selector = "div.products.processors:visible a.ark-accessible-color"
    links = page.eval_on_selector_all(
        selector,
        "els => els.map(e => ({href: e.getAttribute('href'), text: e.textContent}))",
    )

    series: list[SeriesLink] = []
    for item in links:
        href = item.get("href")
        text = normalize_text(item.get("text") or "")
        if not href or not text:
            continue
        if "/ark/products/series/" not in href:
            continue
        series.append(SeriesLink(category=category_name, family=text, url=to_abs_url(href)))
    return series


def extract_skus_from_series_page(page: Page, category: str, family: str, series_url: str) -> list[SkuLink]:
    goto_with_retry(page, series_url)
    page.wait_for_selector("table#product-table", timeout=60000)

    # Product rows contain data-product-id=<sku> and a link to /products/sku/<sku>/.../specifications.html
    items = page.eval_on_selector_all(
        "table#product-table tr[data-product-id]",
        """
        rows => rows.map(r => {
          const sku = r.getAttribute('data-product-id');
          const a = r.querySelector('td.ark-product-name a[href*="/products/sku/"]');
          return { sku, name: a ? a.textContent : null, href: a ? a.getAttribute('href') : null };
        })
        """,
    )

    results: list[SkuLink] = []
    for item in items:
        sku = (item.get("sku") or "").strip()
        name = normalize_text(item.get("name") or "")
        href = item.get("href")
        if not sku or not href:
            continue
        if "specifications.html" not in href:
            continue
        results.append(
            SkuLink(
                sku=sku,
                product_name=name,
                category=category,
                family=family,
                spec_url=to_abs_url(href),
            )
        )

    return results


def scrape_spec_rows(page: Page, spec_url: str) -> tuple[str, list[tuple[str, str, str]]]:
    goto_with_retry(page, spec_url)
    wait_for_specs_ready(page)

    title = page.locator("section.upe-tech-spec").get_attribute("data-title-start")
    product_name = normalize_text(title or page.title() or "")

    section_ids = page.eval_on_selector_all(
        "div.tech-section[id^='specs-']",
        "els => els.map(e => e.id)",
    )

    rows: list[tuple[str, str, str]] = []
    for section_id in section_ids:
        section_selector = f"div.tech-section#{section_id}"
        group_name = normalize_text(
            page.locator(f"{section_selector} h3").first.text_content() or ""
        )
        if not group_name:
            continue

        pairs = page.eval_on_selector_all(
            f"{section_selector} div.row.tech-section-row",
            """
            els => els.map(row => {
              const label = row.querySelector('.tech-label span')?.textContent ?? '';
              const dataNode = row.querySelector('.tech-data');
              const value = dataNode?.innerText ?? '';
              return { label, value };
            })
            """,
        )

        for p in pairs:
            label = normalize_text(p.get("label") or "")
            value = normalize_text(p.get("value") or "")
            if not label or not value:
                continue
            rows.append((group_name, label, value))

    return product_name, rows


def write_csv_rows(
    csv_path: Path,
    sku: str,
    product_name: str,
    product_url: str,
    category: str,
    family: str,
    spec_rows: Iterable[tuple[str, str, str]],
) -> int:
    is_new = not csv_path.exists()
    csv_path.parent.mkdir(parents=True, exist_ok=True)

    with csv_path.open("a", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        if is_new:
            writer.writerow(
                [
                    "sku",
                    "product_name",
                    "product_url",
                    "category",
                    "family",
                    "spec_group",
                    "spec_name",
                    "spec_value",
                    "scraped_at",
                ]
            )

        count = 0
        scraped_at = utc_now_iso()
        for group, spec_name, spec_value in spec_rows:
            writer.writerow(
                [
                    sku,
                    product_name,
                    product_url,
                    category,
                    family,
                    group,
                    spec_name,
                    spec_value,
                    scraped_at,
                ]
            )
            count += 1

    return count


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description="Scrape Intel ARK processor specifications to long CSV")
    p.add_argument("--out", default="intel_specs_long.csv", help="Output CSV path")
    p.add_argument("--db", default="state.sqlite", help="SQLite state DB path")
    p.add_argument(
        "--storage-state",
        default="storage_state.json",
        help="Playwright storage state JSON (cookies) path",
    )
    p.add_argument("--headful", action="store_true", help="Run with visible browser")
    p.add_argument("--max-skus", type=int, default=0, help="Limit SKUs (0 = no limit)")
    p.add_argument(
        "--skip-discovery",
        action="store_true",
        help="Skip series/SKU discovery and scrape remaining SKUs in DB",
    )
    p.add_argument(
        "--retry-errors",
        action="store_true",
        help="Retry SKUs previously marked as error",
    )
    return p.parse_args()


def main() -> None:
    configure_console_utf8()
    args = parse_args()

    out_csv = Path(args.out)
    db_path = Path(args.db)
    storage_state = Path(args.storage_state)

    ensure_db(db_path)

    with closing(sqlite3.connect(db_path)) as conn:
        conn.row_factory = sqlite3.Row
        done_skus = load_done_skus(conn)
        failed_skus = load_failed_skus(conn)

        with sync_playwright() as p:
            browser = p.chromium.launch(headless=not args.headful)
            page = new_page(browser, storage_state, headless=not args.headful)

            try:
                if not args.skip_discovery:
                    print("Discovering processor categories...")
                    categories = discover_processor_categories(page)

                    print(f"Found {len(categories)} categories")
                    all_series: list[SeriesLink] = []
                    for cat in categories:
                        print(f"Discovering series for category: {cat}")
                        series = discover_series_for_category(page, cat)
                        store_series(conn, series)
                        all_series.extend(series)
                        polite_sleep()

                    print(f"Discovered {len(all_series)} series")

                    total_skus = 0
                    for series in all_series:
                        print(f"Extracting SKUs from series: {series.family}")
                        skus = extract_skus_from_series_page(page, series.category, series.family, series.url)
                        store_skus(conn, skus)
                        total_skus += len(skus)
                        polite_sleep()

                    print(f"Discovered {total_skus} SKU entries (dedup happens in DB)")

                # Scrape loop
                rows = conn.execute(
                    """
                    SELECT sku, category, family, spec_url, product_name
                    FROM discovered_skus
                    ORDER BY sku
                    """
                ).fetchall()

                if args.retry_errors:
                    pending = [r for r in rows if r["sku"] not in done_skus]
                else:
                    pending = [r for r in rows if r["sku"] not in done_skus and r["sku"] not in failed_skus]
                if args.max_skus and args.max_skus > 0:
                    pending = pending[: args.max_skus]

                print(f"Scraping {len(pending)} SKUs (already done: {len(done_skus)})")

                for idx, r in enumerate(pending, start=1):
                    sku = r["sku"]
                    category = r["category"]
                    family = r["family"]
                    spec_url = r["spec_url"]
                    fallback_name = r["product_name"] or ""

                    try:
                        polite_sleep(0.2, 0.8)
                        product_name, packed_rows = scrape_spec_rows(page, spec_url)
                        product_name = product_name or fallback_name

                        written = write_csv_rows(
                            out_csv,
                            sku=sku,
                            product_name=product_name,
                            product_url=spec_url,
                            category=category,
                            family=family,
                            spec_rows=packed_rows,
                        )
                        mark_sku(conn, sku, status="ok", error=None)
                        print(f"[{idx}/{len(pending)}] OK sku={sku} rows={written}")

                        # Save cookies periodically
                        if idx % 25 == 0:
                            page.context.storage_state(path=str(storage_state))

                    except Exception as e:
                        mark_sku(conn, sku, status="error", error=str(e))
                        print(f"[{idx}/{len(pending)}] ERROR sku={sku}: {e}")

                page.context.storage_state(path=str(storage_state))

            finally:
                try:
                    page.context.close()
                except Exception:
                    pass
                browser.close()


if __name__ == "__main__":
    main()
