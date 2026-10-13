# GraphRAG Knowledge Assistant

**Developed by Dhruv Mittal** · [GitHub profile](https://github.com/Dhruv-ux-dev)

A Streamlit application that demonstrates knowledge-graph-based retrieval-augmented generation (GraphRAG). It extracts entities and relationships from text with a local Ollama model, stores them in Neo4j, traverses connected entities for multi-hop context, and presents answers with source snippets and traversal traces.

## Features

- **Entity and relationship extraction** from text using Ollama.
- **Neo4j graph storage** for entities and relationships.
- **Multi-hop retrieval** across connected graph nodes.
- **Source attribution** mapping answer citations to document snippets.
- **Execution trace** that exposes the retrieval steps.
- **Streamlit dashboard** for ingestion, querying, and database statistics.
- **Docker Compose setup** for the app, Neo4j, and Ollama.

## Tech stack

- Python and Streamlit
- Neo4j graph database
- Ollama local inference (default model: `llama3.2`)
- Docker and Docker Compose (optional)

## Requirements

For local Python execution, install Python 3.11+, Node.js is not required by this project. You need:
- A running Neo4j database
- Ollama running with the `llama3.2` model, or another supported model selected in the app

## Run with Docker Compose

Docker Compose starts Neo4j, Ollama, and the Streamlit UI.

```bash
# Optional: set a non-default local development password first
export NEO4J_PASSWORD='choose-a-local-password'
docker compose up --build
```

Open:
- Streamlit UI: http://localhost:8501
- Neo4j Browser: http://localhost:7474

The first Ollama startup downloads `llama3.2`, which can take a while and requires network access. To stop:

```bash
docker compose down
```

Graph data is stored in the `neo4j_data` Docker volume. Keep this volume if you want to retain ingested data.

## Run locally

1. Start Neo4j and Ollama separately.
2. Pull the model:

   ```bash
   ollama pull llama3.2
   ```

3. Install Python dependencies:

   ```bash
   python -m venv .venv
   source .venv/bin/activate  # Windows: .venv\\Scripts\\activate
   pip install -r requirements.txt
   ```

4. Set connection variables if your services don't use the defaults:

   ```bash
   export NEO4J_URI='bolt://127.0.0.1:7687'
   export NEO4J_USER='neo4j'
   export NEO4J_PASSWORD='your-local-neo4j-password'
   export OLLAMA_HOST='http://localhost:11434'
   ```

5. Launch the app:

   ```bash
   streamlit run app.py
   ```

## How to use

1. Open the **Document Ingestion** tab.
2. Choose a sample document or paste your own text, then select **Extract & Ingest Nodes**.
3. Open **Ask Assistant** and ask a question about entities/relationships in the ingested material.
4. Use **Database Status** to view node/relationship counts or clear the graph.

> **Warning:** The “Clear Database Graph” button deletes every node and relationship in the connected Neo4j database. Use it only with a database dedicated to this project.

## Project structure

```text
GraphRAG-Knowledge-Assistant/
├── app.py
├── requirements.txt
├── Dockerfile
├── docker-compose.yml
├── README.md
└── .gitignore
```

## Notes and limitations

- The current node lookup uses simple text matching rather than vector similarity search.
- Citation markers are checked against retrieved graph-context entries, but this is not a full independent factuality verification system.
- Sample demo documents are illustrative examples, not benchmark results.
- Use a non-default Neo4j password outside a throwaway local demo.

## Author

**Dhruv Mittal** · [GitHub](https://github.com/Dhruv-ux-dev)
