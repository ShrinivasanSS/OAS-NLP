# Project description

This project is about turning an Open API Specification document to a ready made tool to be used with AI Agents. The main drawback of using OAS or MCP servers directly is that they contain too much information for the AI to process. So, instead, the OAS will be transformed to an SQLite database, with each operationid being a table, and all the parameters/response objects as its fields. 

The fields and their descriptions will be stored in a vector database, and supplied in the context to an AI assistant to figure out the appropriate API/table to be used.

## Directory Structure

- examples/ -> contain the sample OAS used for testing
- database/ -> contains the sqlite/qdrant store. 

## Todo

Progress updates: 
