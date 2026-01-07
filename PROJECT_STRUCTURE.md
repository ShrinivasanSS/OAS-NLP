# Project description

This project is about turning an Open API Specification document to a ready made tool to be used with AI Agents. The main drawback of using OAS or MCP servers directly is that they contain too much information for the AI to process. So, instead, the OAS will be transformed to an SQLite database, with each operationid being a table, and all the parameters/response objects as its fields.

The fields and their descriptions will be stored in a vector database, and supplied in the context to an AI assistant to figure out the appropriate API/table to be used.

## Directory Structure

- oas_service.py -> Flask service utilities for parsing OAS and interacting with SQLite/Qdrant.
- templates/ -> HTML templates for the four application views.
- tests/ -> pytest coverage for validating sample OAS inputs.
- examples/ -> contain the sample OAS used for testing.
- database/ -> contains the sqlite/qdrant store.
- generated_outputs/ -> sample output storage (generated sample data in `api_data/`).
- uploads/ -> uploaded OAS files for reuse across sessions (gitignored).
- logs/ -> application log files.

## Todo

Progress updates:
- Phase 1: Flask UI for uploading OAS, generating samples, building tables, querying tables, resetting caches, and searching Qdrant.
