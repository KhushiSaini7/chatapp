System Architecture
Our system is built using a modular, layered architecture that separates concerns for better scalability and maintenance. Here’s how the main components work together:
graph TD;
    A[Client (Web/Mobile/Postman)]
    B[Frontend (User Interface)]
    C[Backend API (FastAPI)]
    D[Authentication Service (JWT/OAuth2)]
    E[Database (PostgreSQL)]
    F[Cache (Redis)]
    G[LLM Service (OpenAI/Anthropic)]
    H[Knowledge Base (FAISS + Embeddings)]
    I[Monitoring & Logging (Prometheus/Grafana)]

    A -->|HTTP Requests| B
    B -->|API Calls| C
    C -->|Auth Requests| D
    C -->|Data Storage| E
    C -->|Caching| F
    C -->|LLM Queries| G
    G -->|Context Retrieval| H
    C -->|Metrics & Logs| I


