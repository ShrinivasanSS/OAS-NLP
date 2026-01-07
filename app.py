import logging
import os
import shutil
from pathlib import Path

from flask import Flask, redirect, render_template, request, url_for
from werkzeug.utils import secure_filename

from oas_service import (
    create_sqlite_tables,
    extract_operations,
    generate_samples,
    get_sqlite_table_columns,
    list_sqlite_tables,
    load_oas,
    search_qdrant,
    upsert_qdrant_fields,
)

BASE_DIR = Path(__file__).resolve().parent
DATA_DIR = BASE_DIR / "generated_outputs" / "api_data"
UPLOADS_DIR = BASE_DIR / "uploads"
DATABASE_PATH = BASE_DIR / "database" / "oas.db"
QDRANT_PATH = BASE_DIR / "database" / "qdrant"
LOG_DIR = BASE_DIR / "logs"
LOG_DIR.mkdir(exist_ok=True)
UPLOADS_DIR.mkdir(exist_ok=True)

logging.basicConfig(
    filename=LOG_DIR / "app.log",
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s %(message)s",
)
logger = logging.getLogger(__name__)

app = Flask(__name__)
app.config["UPLOAD_FOLDER"] = str(UPLOADS_DIR)
app.config["MAX_CONTENT_LENGTH"] = 5 * 1024 * 1024
app.config["LAST_OAS_PATH"] = ""


@app.route("/")
def index():
    return redirect(url_for("upload_oas"))


@app.route("/upload", methods=["GET", "POST"])
def upload_oas():
    examples_dir = BASE_DIR / "examples"
    example_files = sorted([f.name for f in examples_dir.glob("*.yaml")])
    uploaded_files = sorted([f.name for f in UPLOADS_DIR.glob("*") if f.is_file()])
    preview = None
    message = "Reset completed. Upload or select an OAS file to continue." if request.args.get("reset") else None
    if request.method == "POST":
        selected_example = request.form.get("example")
        selected_upload = request.form.get("uploaded_file")
        uploaded = request.files.get("oas_file")
        if selected_example:
            path = examples_dir / selected_example
        elif selected_upload:
            path = UPLOADS_DIR / selected_upload
        elif uploaded and uploaded.filename:
            safe_name = secure_filename(uploaded.filename)
            upload_path = Path(app.config["UPLOAD_FOLDER"]) / safe_name
            uploaded.save(upload_path)
            path = upload_path
        else:
            message = "Please upload a file or select an example."
            path = None
        if path:
            try:
                preview = path.read_text(encoding="utf-8")
                app.config["LAST_OAS_PATH"] = str(path)
                message = f"Loaded {path.name}"
            except Exception as exc:
                logger.exception("Failed to load OAS")
                message = f"Failed to load OAS: {exc}"
    return render_template(
        "upload.html",
        examples=example_files,
        uploaded_files=uploaded_files,
        preview=preview,
        message=message,
        oas_path=app.config["LAST_OAS_PATH"],
    )


@app.route("/generate", methods=["GET", "POST"])
def generate_data():
    message = None
    generated = []
    oas_path = app.config["LAST_OAS_PATH"]
    if request.method == "POST":
        oas_path = request.form.get("oas_path") or oas_path
        if not oas_path or not os.path.exists(oas_path):
            message = "Upload an OAS in View 1 first."
        else:
            oas = load_oas(oas_path)
            operations = extract_operations(oas)
            generated = generate_samples(operations, str(DATA_DIR))
            message = f"Generated {len(generated)} sample files."
    return render_template("generate.html", message=message, generated=generated, oas_path=oas_path)


@app.route("/tables", methods=["GET", "POST"])
def query_tables():
    tables = []
    query_tables_list = None
    schema_info = None
    message = None
    oas_path = app.config["LAST_OAS_PATH"]
    if request.method == "POST":
        action = request.form.get("action", "build")
        if action == "build":
            oas_path = request.form.get("oas_path") or oas_path
            if not oas_path or not os.path.exists(oas_path):
                message = "Upload an OAS in View 1 first."
            else:
                oas = load_oas(oas_path)
                operations = extract_operations(oas)
                tables = create_sqlite_tables(operations, str(DATABASE_PATH))
                upsert_count = upsert_qdrant_fields(operations, str(QDRANT_PATH))
                message = f"Created {len(tables)} tables and stored {upsert_count} fields in Qdrant."
        else:
            query = request.form.get("query", "").strip()
            if not query:
                message = "Enter a query like .tables or .schema <tablename>."
            elif query == ".tables":
                query_tables_list = list_sqlite_tables(str(DATABASE_PATH))
                message = f"Found {len(query_tables_list)} tables."
            elif query.startswith(".schema"):
                parts = query.split(maxsplit=1)
                if len(parts) < 2:
                    message = "Provide a table name after .schema."
                else:
                    table_name = parts[1].strip()
                    available_tables = list_sqlite_tables(str(DATABASE_PATH))
                    if table_name not in available_tables:
                        message = f"Table '{table_name}' not found."
                    else:
                        columns = get_sqlite_table_columns(str(DATABASE_PATH), table_name)
                        schema_info = {"table": table_name, "columns": columns}
                        message = f"{table_name} has {len(columns)} columns."
            else:
                message = "Unsupported query. Use .tables or .schema <tablename>."
    return render_template(
        "query_tables.html",
        tables=tables,
        message=message,
        oas_path=oas_path,
        query_tables_list=query_tables_list,
        schema_info=schema_info,
    )


@app.route("/search", methods=["GET", "POST"])
def query_nlp():
    results = []
    message = None
    if request.method == "POST":
        query = request.form.get("query", "")
        if not query:
            message = "Enter a search query."
        else:
            try:
                results = search_qdrant(query, str(QDRANT_PATH))
                message = f"Found {len(results)} matches."
            except Exception as exc:
                logger.exception("Search failed")
                message = f"Search failed: {exc}"
    return render_template("query_nlp.html", results=results, message=message)


@app.route("/reset", methods=["POST"])
def reset_data():
    def clear_directory(path: Path) -> None:
        if not path.exists():
            return
        for item in path.iterdir():
            if item.is_dir():
                shutil.rmtree(item)
            else:
                item.unlink()

    clear_directory(UPLOADS_DIR)
    clear_directory(DATA_DIR)
    if DATABASE_PATH.exists():
        DATABASE_PATH.unlink()
    if QDRANT_PATH.exists():
        shutil.rmtree(QDRANT_PATH)
    app.config["LAST_OAS_PATH"] = ""
    return redirect(url_for("upload_oas", reset="1"))


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000, debug=True)
