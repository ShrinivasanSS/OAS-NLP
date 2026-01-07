# OAS-NLP

Turn your OpenAPI Specification into SQLite tables and vector-searchable fields to help AI agents understand APIs without sharing full responses.

## Getting Started

```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
python app.py
```

The Flask app will start on `http://localhost:5000`.

## Available Endpoints

### Core Views

- `GET /upload` / `POST /upload` - Upload an OAS file or select an example and preview it.
- `GET /generate` / `POST /generate` - Generate sample request/response data under `generated_outputs/api_data`.
- `GET /tables` / `POST /tables` - Build SQLite tables from the OAS and store field metadata in Qdrant.
- `GET /search` / `POST /search` - Search Qdrant for matching fields using NLP.

## Testing

```bash
pytest
```
