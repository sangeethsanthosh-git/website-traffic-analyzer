from __future__ import annotations

import subprocess
from pathlib import Path

from flask import render_template

from app import (
    BENCHMARK_DATASET_FILENAME,
    TRAFFIC_DATASET_FILENAME,
    app,
    blank_benchmark_summary,
    blank_search,
    build_highlights,
    build_summary,
    build_website_benchmark_summary,
    build_website_search_analysis,
    generate_chart,
    generate_website_benchmark_chart,
    generate_website_focus_chart,
    load_traffic_dataset,
    load_website_benchmark_dataset,
    normalize_website_query,
    search_website_benchmark,
)


BASE_DIR = Path(__file__).resolve().parent
STATIC_CSS_PATH = BASE_DIR / "traffic_analyzer" / "static" / "style.css"
SCREENSHOT_DIR = BASE_DIR / "report_assets"
LOGIN_HTML = SCREENSHOT_DIR / "login_preview.html"
DASHBOARD_HTML = SCREENSHOT_DIR / "dashboard_preview.html"
LOGIN_PNG = SCREENSHOT_DIR / "login_page.png"
DASHBOARD_PNG = SCREENSHOT_DIR / "dashboard_page.png"
EDGE_PATH = Path(r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe")


def build_standalone_html(template_name: str, context: dict[str, object], route: str, endpoint: str) -> str:
    css = STATIC_CSS_PATH.read_text(encoding="utf-8")
    with app.test_request_context(route):
        from flask import session

        if endpoint == "dashboard":
            session["user_id"] = 1
            session["username"] = "demo_user"
        app.preprocess_request()
        html = render_template(template_name, **context)
    return html.replace(
        '<link rel="stylesheet" href="/static/style.css">',
        f"<style>\n{css}\n</style>",
    )


def render_login_preview() -> None:
    html = build_standalone_html(
        "login.html",
        {"active_form": "login", "username": ""},
        "/login",
        "login",
    )
    LOGIN_HTML.write_text(html, encoding="utf-8")


def render_dashboard_preview() -> None:
    records = load_traffic_dataset()
    summary = build_summary(records)
    benchmark_records = load_website_benchmark_dataset()
    query = "reddit.com"
    context = {
        "records": list(reversed(records)),
        "summary": summary,
        "highlights": build_highlights(summary),
        "chart_image": generate_chart(records),
        "traffic_dataset_ready": True,
        "traffic_dataset_error": None,
        "traffic_dataset_filename": TRAFFIC_DATASET_FILENAME,
        "benchmark_filename": BENCHMARK_DATASET_FILENAME,
        "benchmark_query": query,
        "benchmark_records": benchmark_records,
        "benchmark_summary": build_website_benchmark_summary(benchmark_records),
        "benchmark_search": build_website_search_analysis(benchmark_records, query),
        "benchmark_display_records": search_website_benchmark(benchmark_records, query) if query else benchmark_records,
        "benchmark_chart_image": generate_website_benchmark_chart(benchmark_records),
        "benchmark_focus_chart": generate_website_focus_chart(benchmark_records, query),
        "benchmark_error": None,
    }
    html = build_standalone_html("index.html", context, "/", "dashboard")
    DASHBOARD_HTML.write_text(html, encoding="utf-8")


def capture_html_screenshot(html_path: Path, png_path: Path, width: int, height: int) -> None:
    if not EDGE_PATH.exists():
        raise FileNotFoundError(f"Microsoft Edge not found at {EDGE_PATH}")

    subprocess.run(
        [
            str(EDGE_PATH),
            "--headless",
            "--disable-gpu",
            f"--window-size={width},{height}",
            f"--screenshot={png_path}",
            html_path.resolve().as_uri(),
        ],
        check=True,
    )


def main() -> None:
    SCREENSHOT_DIR.mkdir(parents=True, exist_ok=True)
    render_login_preview()
    render_dashboard_preview()
    capture_html_screenshot(LOGIN_HTML, LOGIN_PNG, 1440, 1600)
    capture_html_screenshot(DASHBOARD_HTML, DASHBOARD_PNG, 1440, 2600)
    print(f"Created screenshots in {SCREENSHOT_DIR}")


if __name__ == "__main__":
    main()
