import json
import logging
import os
import sqlite3
from dataclasses import dataclass
from typing import Any, Dict, Iterable, List, Tuple

import yaml
from qdrant_client import QdrantClient
from qdrant_client.http import models as qdrant_models

logger = logging.getLogger(__name__)

SUPPORTED_JSON_MIME = {
    "application/json",
    "application/*+json",
}


@dataclass
class OperationInfo:
    operation_id: str
    method: str
    path: str
    request_schema: Dict[str, Any]
    response_schema: Dict[str, Any]


@dataclass
class FlattenedField:
    name: str
    description: str


def load_oas(path: str) -> Dict[str, Any]:
    with open(path, "r", encoding="utf-8") as handle:
        raw = handle.read()
    try:
        return json.loads(raw)
    except json.JSONDecodeError:
        return yaml.safe_load(raw)


def _pick_schema(content: Dict[str, Any]) -> Dict[str, Any]:
    for mime, body in content.items():
        if mime in SUPPORTED_JSON_MIME:
            return body.get("schema", {})
    return {}


def extract_operations(oas: Dict[str, Any]) -> List[OperationInfo]:
    operations: List[OperationInfo] = []
    paths = oas.get("paths", {})
    for path, methods in paths.items():
        for method, payload in methods.items():
            if method.lower() not in {"get", "post", "put", "patch", "delete", "head", "options"}:
                continue
            operation_id = payload.get("operationId")
            if not operation_id:
                operation_id = f"{method}_{path}".replace("/", "_").replace("{", "").replace("}", "")
            request_schema = {}
            request_body = payload.get("requestBody", {})
            if "content" in request_body:
                request_schema = _pick_schema(request_body["content"])
            responses = payload.get("responses", {})
            response_schema = {}
            for response in responses.values():
                content = response.get("content")
                if content:
                    response_schema = _pick_schema(content)
                    if response_schema:
                        break
            operations.append(
                OperationInfo(
                    operation_id=operation_id,
                    method=method.upper(),
                    path=path,
                    request_schema=request_schema,
                    response_schema=response_schema,
                )
            )
    return operations


def _flatten_schema(schema: Dict[str, Any], prefix: str = "") -> List[FlattenedField]:
    fields: List[FlattenedField] = []
    schema_type = schema.get("type")
    description = schema.get("description", "")
    if schema_type == "object" and "properties" in schema:
        for name, value in schema.get("properties", {}).items():
            nested_prefix = f"{prefix}{name}."
            fields.extend(_flatten_schema(value, nested_prefix))
    elif schema_type == "array" and "items" in schema:
        fields.extend(_flatten_schema(schema["items"], prefix))
    else:
        clean_name = prefix[:-1] if prefix.endswith(".") else prefix
        if clean_name:
            fields.append(FlattenedField(clean_name, description))
    return fields


def flatten_operation_fields(operation: OperationInfo) -> List[FlattenedField]:
    fields: List[FlattenedField] = []
    for schema_prefix, schema in ("request", operation.request_schema), ("response", operation.response_schema):
        if not schema:
            continue
        flattened = _flatten_schema(schema)
        for field in flattened:
            name = f"{schema_prefix}.{field.name}" if field.name else schema_prefix
            fields.append(FlattenedField(name.replace(".", "_"), field.description))
    return fields


def generate_sample_from_schema(schema: Dict[str, Any]) -> Any:
    schema_type = schema.get("type")
    if schema_type == "object":
        data = {}
        for name, value in schema.get("properties", {}).items():
            data[name] = generate_sample_from_schema(value)
        return data
    if schema_type == "array":
        item_schema = schema.get("items", {})
        return [generate_sample_from_schema(item_schema)]
    if schema_type == "integer":
        return 1
    if schema_type == "number":
        return 1.0
    if schema_type == "boolean":
        return True
    return "sample"


def generate_samples(operations: Iterable[OperationInfo], output_dir: str) -> List[str]:
    os.makedirs(output_dir, exist_ok=True)
    generated_files: List[str] = []
    for operation in operations:
        for tag, schema in (
            ("request", operation.request_schema),
            ("response", operation.response_schema),
        ):
            if not schema:
                continue
            data = generate_sample_from_schema(schema)
            filename = f"{operation.operation_id}_{tag}.json"
            path = os.path.join(output_dir, filename)
            with open(path, "w", encoding="utf-8") as handle:
                json.dump(data, handle, indent=2)
            generated_files.append(path)
            logger.info("Generated sample for %s (%s): %s", operation.operation_id, tag, path)
    return generated_files


def create_sqlite_tables(
    operations: Iterable[OperationInfo], database_path: str
) -> List[Tuple[str, List[str]]]:
    os.makedirs(os.path.dirname(database_path), exist_ok=True)
    created: List[Tuple[str, List[str]]] = []
    with sqlite3.connect(database_path) as conn:
        for operation in operations:
            fields = flatten_operation_fields(operation)
            if not fields:
                continue
            columns = [f"{field.name} TEXT" for field in fields]
            column_names = [field.name for field in fields]
            table_name = operation.operation_id.replace("-", "_")
            create_statement = f"CREATE TABLE IF NOT EXISTS '{table_name}' ({', '.join(columns)})"
            conn.execute(create_statement)
            created.append((table_name, column_names))
        conn.commit()
    return created


def upsert_qdrant_fields(
    operations: Iterable[OperationInfo],
    storage_path: str,
    collection_name: str = "oas_fields",
) -> int:
    os.makedirs(storage_path, exist_ok=True)
    client = QdrantClient(path=storage_path)
    if collection_name not in [collection.name for collection in client.get_collections().collections]:
        client.create_collection(
            collection_name=collection_name,
            vectors_config=qdrant_models.VectorParams(size=8, distance=qdrant_models.Distance.COSINE),
        )
    payloads = []
    vectors = []
    identifiers = []
    for operation in operations:
        for field in flatten_operation_fields(operation):
            payload = {
                "operation_id": operation.operation_id,
                "field": field.name,
                "description": field.description,
                "path": operation.path,
                "method": operation.method,
            }
            vector = embed_text(f"{operation.operation_id} {field.name} {field.description}")
            identifiers.append(len(identifiers))
            payloads.append(payload)
            vectors.append(vector)
    if payloads:
        client.upsert(
            collection_name=collection_name,
            points=qdrant_models.Batch(ids=identifiers, vectors=vectors, payloads=payloads),
        )
    return len(payloads)


def embed_text(text: str) -> List[float]:
    if not text:
        return [0.0] * 8
    total = sum(ord(char) for char in text)
    return [((total >> shift) & 0xFF) / 255 for shift in range(0, 32, 4)]


def search_qdrant(
    query: str,
    storage_path: str,
    collection_name: str = "oas_fields",
    limit: int = 5,
) -> List[Dict[str, Any]]:
    client = QdrantClient(path=storage_path)
    vector = embed_text(query)
    results = client.search(collection_name=collection_name, query_vector=vector, limit=limit)
    return [
        {
            "score": result.score,
            **(result.payload or {}),
        }
        for result in results
    ]
