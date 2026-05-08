from __future__ import annotations

# Imports used for CSV reading, date handling, charts, and Flask pages.
import base64
import csv
import io
import sqlite3
from dataclasses import dataclass
from datetime import date, datetime
from pathlib import Path
from types import SimpleNamespace

import matplotlib
import numpy as np
from flask import Flask, flash, g, redirect, render_template, request, session, url_for
from werkzeug.security import check_password_hash, generate_password_hash


matplotlib.use("Agg")
import matplotlib.pyplot as plt


# Project folders and dataset file locations.
BASE_DIR = Path(__file__).resolve().parent
DATA_DIR = BASE_DIR / "data"
TEMPLATE_DIR = BASE_DIR / "traffic_analyzer" / "templates"
STATIC_DIR = BASE_DIR / "traffic_analyzer" / "static"

TRAFFIC_DATASET_FILENAME = "Traffic.csv"
BENCHMARK_DATASET_FILENAME = "top_websites_worldwide_feb_2025.csv"
TRAFFIC_DATASET_PATH = DATA_DIR / TRAFFIC_DATASET_FILENAME
BENCHMARK_DATASET_PATH = DATA_DIR / BENCHMARK_DATASET_FILENAME

# Custom errors make dataset problems easier to show in the app.
class DatasetImportError(RuntimeError):
    pass

class BenchmarkDatasetError(RuntimeError):
    pass

# Small data objects for traffic rows and benchmark website rows.
@dataclass(frozen=True)
class TrafficRecord:
    visit_date: date
    user_count: int


@dataclass(frozen=True)
class WebsiteBenchmarkRecord:
    source_rank: int
    website: str
    monthly_visits_display: str
    monthly_visits_estimate: int
    mom_change_pct: float
    yearly_change_pct: float
    data_month: str
    source: str


# Empty/default summary objects used when data is missing.
def blank_traffic_summary():
    return SimpleNamespace(
        total_days=0,
        total_users=0,
        average_users=0.0,
        peak_users=None,
        peak_date=None,
        lowest_users=None,
        lowest_date=None,
        latest_users=None,
        latest_date=None,
        trend_label="Waiting for data",
        change_percent=None,
        volatility=0.0,
    )


def blank_benchmark_summary():
    return SimpleNamespace(
        site_count=0,
        data_month=None,
        source=None,
        combined_visits_display="0",
        top_website=None,
        top_visits_display=None,
        top_mom_gainer=None,
        top_mom_gainer_pct=None,
        top_yearly_gainer=None,
        top_yearly_gainer_pct=None,
    )


def blank_search(query: str = "", normalized_query: str = "", label: str = "No search yet"):
    return SimpleNamespace(
        query=query,
        normalized_query=normalized_query,
        matching_count=0,
        selected_website=None,
        selected_rank=None,
        monthly_visits_display=None,
        mom_change_pct=None,
        yearly_change_pct=None,
        benchmark_share_pct=None,
        relative_to_top_pct=None,
        relative_to_average_pct=None,
        trajectory_label=label,
    )


# Basic Flask app settings.
def get_app_config() -> dict[str, object]:
    return {
        "APP_NAME": "Website Traffic Analyzer",
        "SECRET_KEY": "I AM BATMAN",
        "DATABASE_PATH": BASE_DIR / "data" / "app.db",
    }


def get_db_connection():
    if "db_connection" not in g:
        database_path = Path(g.app_config["DATABASE_PATH"])
        database_path.parent.mkdir(parents=True, exist_ok=True)
        g.db_connection = sqlite3.connect(database_path)
        g.db_connection.row_factory = sqlite3.Row
    return g.db_connection


def close_db_connection(error=None) -> None:
    connection = g.pop("db_connection", None)
    if connection is not None:
        connection.close()


def init_database(flask_app: Flask) -> None:
    with flask_app.app_context():
        g.app_config = flask_app.config
        connection = get_db_connection()
        connection.execute(
            """
            CREATE TABLE IF NOT EXISTS users (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                username TEXT NOT NULL UNIQUE,
                password_hash TEXT NOT NULL,
                created_at TEXT NOT NULL
            )
            """
        )
        connection.commit()
        close_db_connection()


def find_user_by_username(username: str):
    return get_db_connection().execute(
        "SELECT id, username, password_hash, created_at FROM users WHERE username = ?",
        (username,),
    ).fetchone()


def create_user_account(username: str, password: str):
    connection = get_db_connection()
    cursor = connection.execute(
        "INSERT INTO users (username, password_hash, created_at) VALUES (?, ?, ?)",
        (username, generate_password_hash(password), datetime.utcnow().isoformat(timespec="seconds")),
    )
    connection.commit()
    return cursor.lastrowid


def validate_login_form(username: str, password: str) -> str | None:
    if not username:
        return "Username is required."
    if not password:
        return "Password is required."
    if len(password) < 6:
        return "Password must be at least 6 characters long."
    return None


def is_logged_in() -> bool:
    return session.get("user_id") is not None


def sign_in_user(user_id: int, username: str) -> None:
    session.clear()
    session["user_id"] = user_id
    session["username"] = username


# Builds the main traffic statistics for the dashboard cards.
def build_summary(records: list[TrafficRecord]):
    if not records:
        return blank_traffic_summary()

    values = np.array([record.user_count for record in records], dtype=float)
    dates = [record.visit_date for record in records]
    peak = int(np.argmax(values))
    low = int(np.argmin(values))
    slope = float(np.polyfit(np.arange(len(values)), values, 1)[0]) if len(values) > 1 else 0

    change = None
    if len(values) > 1:
        change = 100.0 if values[0] == 0 and values[-1] > 0 else 0.0
        if values[0] != 0:
            change = float((values[-1] - values[0]) / values[0] * 100)

    return SimpleNamespace(
        total_days=len(records),
        total_users=int(values.sum()),
        average_users=float(values.mean()),
        peak_users=int(values[peak]),
        peak_date=dates[peak].strftime("%d %b %Y"),
        lowest_users=int(values[low]),
        lowest_date=dates[low].strftime("%d %b %Y"),
        latest_users=int(values[-1]),
        latest_date=dates[-1].strftime("%d %b %Y"),
        trend_label="Increasing" if slope > 2 else "Decreasing" if slope < -2 else "Stable",
        change_percent=change,
        volatility=float(values.std()),
    )

# Creates short text insights from the traffic summary.
def build_highlights(summary) -> list[str]:
    if summary.total_days == 0:
        return ["Add the traffic CSV file to unlock averages, peak days, and charts."]

    lines = [
        f"Average traffic is {summary.average_users:.0f} users per day.",
        f"Peak traffic reached {summary.peak_users} users on {summary.peak_date}.",
        f"The latest recorded day is {summary.latest_date} with {summary.latest_users} users.",
    ]
    if summary.change_percent is not None:
        direction = "up" if summary.change_percent >= 0 else "down"
        lines.append(f"Traffic is {direction} by {abs(summary.change_percent):.1f}% overall.")
    return lines

# Loads traffic records from the CSV file.
def load_traffic_dataset(dataset_path: Path | None = None) -> list[TrafficRecord]:
    rows = read_csv(dataset_path or TRAFFIC_DATASET_PATH, {"Date", "Combined Users"}, DatasetImportError)
    records = []

    for row in rows:
        try:
            records.append(
                TrafficRecord(
                    datetime.strptime(row["Date"], "%m/%d/%Y").date(),
                    resolve_user_count(row),
                )
            )
        except (TypeError, ValueError) as exc:
            raise DatasetImportError(f"Unable to parse dataset row for date {row.get('Date', '<missing>')}.") from exc

    if not records:
        raise DatasetImportError("Dataset does not contain any traffic rows.")
    return sorted(records, key=lambda record: record.visit_date)


# Loads the top websites benchmark CSV file.
def load_website_benchmark_dataset(dataset_path: Path | None = None) -> list[WebsiteBenchmarkRecord]:
    required = {
        "source_rank",
        "website",
        "monthly_visits_display",
        "monthly_visits_estimate",
        "mom_change_pct",
        "yearly_change_pct",
        "data_month",
        "source",
    }
    rows = read_csv(dataset_path or BENCHMARK_DATASET_PATH, required, BenchmarkDatasetError, "Benchmark dataset")
    records = []

    for row in rows:
        try:
            records.append(
                WebsiteBenchmarkRecord(
                    int(row["source_rank"]),
                    row["website"].strip(),
                    row["monthly_visits_display"].strip(),
                    int(row["monthly_visits_estimate"]),
                    float(row["mom_change_pct"]),
                    float(row["yearly_change_pct"]),
                    row["data_month"].strip(),
                    row["source"].strip(),
                )
            )
        except (TypeError, ValueError) as exc:
            website = row.get("website", "<missing>")
            raise BenchmarkDatasetError(f"Unable to parse benchmark dataset row for website {website}.") from exc

    if not records:
        raise BenchmarkDatasetError("Benchmark dataset does not contain any rows.")
    return sorted(records, key=lambda record: record.source_rank)


# Shared CSV reader with required-column checking.
def read_csv(path: Path, required_columns: set[str], error_type: type[RuntimeError], label: str = "Dataset"):
    if not path.exists():
        raise error_type(f"{label} file not found at {path}.")

    with path.open(encoding="utf-8-sig", newline="") as csv_file:
        reader = csv.DictReader(csv_file)
        if reader.fieldnames is None:
            raise error_type(f"{label} file is empty.")

        missing = required_columns.difference(reader.fieldnames)
        if missing:
            raise error_type(f"{label} is missing required columns: {', '.join(sorted(missing))}")
        return list(reader)


# Builds summary cards for the benchmark website dataset.
def build_website_benchmark_summary(records: list[WebsiteBenchmarkRecord]):
    if not records:
        return blank_benchmark_summary()

    top = max(records, key=lambda record: record.monthly_visits_estimate)
    mom = max(records, key=lambda record: record.mom_change_pct)
    yoy = max(records, key=lambda record: record.yearly_change_pct)
    total = sum(record.monthly_visits_estimate for record in records)

    return SimpleNamespace(
        site_count=len(records),
        data_month=records[0].data_month,
        source=records[0].source,
        combined_visits_display=format_visits(total),
        top_website=top.website,
        top_visits_display=top.monthly_visits_display,
        top_mom_gainer=mom.website,
        top_mom_gainer_pct=mom.mom_change_pct,
        top_yearly_gainer=yoy.website,
        top_yearly_gainer_pct=yoy.yearly_change_pct,
    )


# Finds matching websites from a search query.
def search_website_benchmark(records: list[WebsiteBenchmarkRecord], query: str) -> list[WebsiteBenchmarkRecord]:
    query = normalize_website_query(query)
    if not query:
        return []

    exact = [record for record in records if record.website.lower() == query]
    partial = [record for record in records if query in record.website.lower() and record.website.lower() != query]
    return exact + partial


# Builds detailed analysis for the searched website.
def build_website_search_analysis(records: list[WebsiteBenchmarkRecord], query: str):
    normalized = normalize_website_query(query)
    if not normalized:
        return blank_search(query, normalized)

    matches = search_website_benchmark(records, query)
    if not matches:
        return blank_search(query, normalized, "No match found")

    selected = matches[0]
    total = sum(record.monthly_visits_estimate for record in records)
    average = total / len(records)
    top = max(records, key=lambda record: record.monthly_visits_estimate)

    if selected.mom_change_pct > 0 and selected.yearly_change_pct > 0:
        label = "Growing"
    elif selected.mom_change_pct < 0 and selected.yearly_change_pct < 0:
        label = "Cooling"
    else:
        label = "Mixed"

    search = blank_search(query, normalized, label)
    search.matching_count = len(matches)
    search.selected_website = selected.website
    search.selected_rank = selected.source_rank
    search.monthly_visits_display = selected.monthly_visits_display
    search.mom_change_pct = selected.mom_change_pct
    search.yearly_change_pct = selected.yearly_change_pct
    search.benchmark_share_pct = selected.monthly_visits_estimate / total * 100
    search.relative_to_top_pct = selected.monthly_visits_estimate / top.monthly_visits_estimate * 100
    search.relative_to_average_pct = (selected.monthly_visits_estimate - average) / average * 100
    return search


# Generates the main traffic line chart.
def generate_chart(records: list[TrafficRecord]) -> str | None:
    if not records:
        return None

    values = np.array([record.user_count for record in records], dtype=float)
    labels = [record.visit_date.strftime("%d %b") for record in records]
    x_axis = np.arange(len(records))

    figure, axis = plt.subplots(figsize=(10, 4.8))
    style_axis(axis, "Website Traffic", "Users")
    axis.plot(x_axis, values, color="#0f766e", marker="o", linewidth=2.4, markersize=5, label="Users")
    axis.fill_between(x_axis, values, color="#99f6e4", alpha=0.28)

    moving = moving_average(values, min(7, len(values)))
    if moving is not None:
        start = len(values) - len(moving)
        axis.plot(x_axis[start:], moving, color="#ea580c", linestyle="--", linewidth=2, label="7-day average")

    step = max(1, len(labels) // 8)
    axis.set_xticks(x_axis[::step])
    axis.set_xticklabels(labels[::step], rotation=35, ha="right")
    axis.legend(frameon=False)
    return chart_to_base64(figure)


# Generates the benchmark bar chart for top websites.
def generate_website_benchmark_chart(records: list[WebsiteBenchmarkRecord], limit: int = 10) -> str | None:
    if not records:
        return None

    top_records = sorted(records, key=lambda record: record.monthly_visits_estimate)[-limit:]
    labels = [record.website for record in top_records]
    values = [record.monthly_visits_estimate / 1_000_000_000 for record in top_records]

    figure, axis = plt.subplots(figsize=(10, 5.6))
    style_axis(axis, "Top Websites by Estimated Monthly Visits", "Estimated monthly visits (billions)", grid_axis="x")
    bars = axis.barh(labels, values, color="#0f766e", alpha=0.88)
    for bar, record in zip(bars, top_records):
        axis.text(bar.get_width() + 0.25, bar.get_y() + bar.get_height() / 2, record.monthly_visits_display, va="center", fontsize=9)
    return chart_to_base64(figure)


# Generates a comparison chart for the searched website.
def generate_website_focus_chart(records: list[WebsiteBenchmarkRecord], query: str) -> str | None:
    matches = search_website_benchmark(records, query)
    if not matches:
        return None

    selected = matches[0]
    top = max(records, key=lambda record: record.monthly_visits_estimate)
    average = sum(record.monthly_visits_estimate for record in records) / len(records)
    values = [selected.monthly_visits_estimate / 1_000_000_000, average / 1_000_000_000, top.monthly_visits_estimate / 1_000_000_000]
    labels = [selected.monthly_visits_display, format_visits(int(average)), top.monthly_visits_display]

    figure, axis = plt.subplots(figsize=(7.5, 4.8))
    style_axis(axis, f"Traffic Snapshot for {selected.website}", "Estimated monthly visits (billions)")
    bars = axis.bar(["Selected site", "Benchmark average", "Top website"], values, color=["#ea580c", "#94a3b8", "#0f766e"], width=0.55)
    for bar, label in zip(bars, labels):
        axis.text(bar.get_x() + bar.get_width() / 2, bar.get_height() + max(values) * 0.02, label, ha="center", fontsize=9)
    return chart_to_base64(figure)


# Creates the Flask app, route, and template filter.
def create_app(test_config: dict[str, object] | None = None) -> Flask:
    flask_app = Flask(__name__, template_folder=str(TEMPLATE_DIR), static_folder=str(STATIC_DIR), static_url_path="/static")
    flask_app.config.from_mapping(get_app_config(), TRAFFIC_DATASET_ERROR=None)
    if test_config:
        flask_app.config.update(test_config)
    init_database(flask_app)

    @flask_app.before_request
    def load_request_state() -> None:
        g.app_config = flask_app.config
        g.current_username = session.get("username")

    flask_app.teardown_appcontext(close_db_connection)

    @flask_app.template_filter("signed_pct")
    def signed_pct(value: float | None) -> str:
        return "N/A" if value is None else f"{value:+.2f}%"

    @flask_app.context_processor
    def inject_auth_state() -> dict[str, object]:
        return {
            "current_username": g.get("current_username"),
            "is_logged_in": is_logged_in(),
        }

    def get_traffic_records():
        try:
            flask_app.config["TRAFFIC_DATASET_ERROR"] = None
            return load_traffic_dataset(), True
        except DatasetImportError as exc:
            flask_app.config["TRAFFIC_DATASET_ERROR"] = str(exc)
            return [], False

    @flask_app.route("/login", methods=["GET", "POST"])
    def login():
        if is_logged_in():
            return redirect(url_for("dashboard"))

        requested_mode = request.args.get("mode", "login").strip().lower()
        active_form = "register" if requested_mode == "register" else "login"

        if request.method == "POST":
            action = request.form.get("action", "login")
            username = request.form.get("username", "").strip().lower()
            password = request.form.get("password", "")
            error = validate_login_form(username, password)

            if error:
                flash(error, "error")
                return render_template("login.html", active_form=action, username=username)

            if action == "register":
                if find_user_by_username(username):
                    flash("That username already exists. Please log in instead.", "error")
                    return render_template("login.html", active_form="register", username=username)

                user_id = create_user_account(username, password)
                sign_in_user(user_id, username)
                flash("Account created successfully. You are now signed in.", "success")
                return redirect(url_for("dashboard"))

            user = find_user_by_username(username)
            if user is None or not check_password_hash(user["password_hash"], password):
                flash("Invalid username or password.", "error")
                return render_template("login.html", active_form="login", username=username)

            sign_in_user(int(user["id"]), user["username"])
            flash("Welcome back.", "success")
            return redirect(url_for("dashboard"))

        return render_template("login.html", active_form=active_form, username="")

    @flask_app.post("/logout")
    def logout():
        session.clear()
        flash("You have been signed out.", "success")
        return redirect(url_for("login"))

    @flask_app.get("/")
    def dashboard():
        if not is_logged_in():
            return redirect(url_for("login"))

        records, ready = get_traffic_records()
        summary = build_summary(records)
        query = request.args.get("benchmark_query", "").strip()
        context = {
            "records": list(reversed(records)),
            "summary": summary,
            "highlights": build_highlights(summary),
            "chart_image": generate_chart(records),
            "traffic_dataset_ready": ready,
            "traffic_dataset_error": flask_app.config["TRAFFIC_DATASET_ERROR"],
            "traffic_dataset_filename": TRAFFIC_DATASET_FILENAME,
            "benchmark_filename": BENCHMARK_DATASET_FILENAME,
            "benchmark_query": query,
            "benchmark_records": [],
            "benchmark_summary": blank_benchmark_summary(),
            "benchmark_search": blank_search(query, normalize_website_query(query)),
            "benchmark_display_records": [],
            "benchmark_chart_image": None,
            "benchmark_focus_chart": None,
            "benchmark_error": None,
        }

        try:
            benchmark_records = load_website_benchmark_dataset()
            context.update(
                benchmark_records=benchmark_records,
                benchmark_summary=build_website_benchmark_summary(benchmark_records),
                benchmark_search=build_website_search_analysis(benchmark_records, query),
                benchmark_display_records=search_website_benchmark(benchmark_records, query) if query else benchmark_records,
                benchmark_chart_image=generate_website_benchmark_chart(benchmark_records),
                benchmark_focus_chart=generate_website_focus_chart(benchmark_records, query),
            )
        except BenchmarkDatasetError as exc:
            context["benchmark_error"] = str(exc)

        return render_template("index.html", **context)

    return flask_app


# Common chart styling helper.
def style_axis(axis, title: str, label: str, grid_axis: str = "y") -> None:
    axis.figure.patch.set_facecolor("#fff8ee")
    axis.set_facecolor("#ffffff")
    axis.set_title(title)
    axis.set_ylabel(label if grid_axis == "y" else "")
    axis.set_xlabel(label if grid_axis == "x" else "")
    axis.grid(axis=grid_axis, alpha=0.25)


# Converts a Matplotlib chart into an image string for HTML.
def chart_to_base64(figure) -> str:
    figure.tight_layout()
    buffer = io.BytesIO()
    figure.savefig(buffer, format="png", dpi=140, bbox_inches="tight")
    plt.close(figure)
    return base64.b64encode(buffer.getvalue()).decode("utf-8")


# Calculates a simple moving average for the traffic chart.
def moving_average(values: np.ndarray, window: int) -> np.ndarray | None:
    if window < 2 or len(values) < window:
        return None
    return np.convolve(values, np.ones(window) / window, mode="valid")


# Chooses the best user count from the available CSV columns.
def resolve_user_count(row: dict[str, str]) -> int:
    combined = parse_int(row.get("Combined Users", ""))
    if combined is not None:
        return combined

    users = [parse_int(row.get("Socrata Users", "")), parse_int(row.get("Geohub Users", ""))]
    users = [value for value in users if value is not None]
    if not users:
        raise ValueError("No user count columns were populated.")
    return sum(users)


# Converts a CSV text value to an integer when possible.
def parse_int(value: str) -> int | None:
    return int(value.strip()) if value and value.strip() else None


# Formats large visit numbers as B or M for display.
def format_visits(value: int) -> str:
    if value >= 1_000_000_000:
        return f"{value / 1_000_000_000:.1f}B"
    if value >= 1_000_000:
        return f"{value / 1_000_000:.1f}M"
    return f"{value:,}"


# Cleans website search text like https://www.example.com/page.
def normalize_website_query(query: str) -> str:
    query = query.strip().lower()
    for prefix in ("https://", "http://", "www."):
        if query.startswith(prefix):
            query = query[len(prefix) :]
    return query.split("/", 1)[0]


# App object used by Flask when running the project.
app = create_app()


# Starts the development server when this file is run directly.
if __name__ == "__main__":
    app.run(debug=True)
