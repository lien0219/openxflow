<!-- markdownlint-disable MD001 MD033 MD041 -->

<div align="center">

# XiangFlow AI

### Build intelligent AI workflows visually

A next-generation open-source AI workflow platform powered by Skills, MCP, agents, and visual orchestration.

[简体中文](./README.md) · [English](./README_EN.md)

[![MIT License](https://img.shields.io/github/license/lien0219/xiangflow-ai?style=flat-square)](./LICENSE)
[![GitHub Stars](https://img.shields.io/github/stars/lien0219/xiangflow-ai?style=flat-square)](https://github.com/lien0219/xiangflow-ai/stargazers)
[![GitHub Forks](https://img.shields.io/github/forks/lien0219/xiangflow-ai?style=flat-square)](https://github.com/lien0219/xiangflow-ai/forks)
[![GitHub Issues](https://img.shields.io/github/issues/lien0219/xiangflow-ai?style=flat-square)](https://github.com/lien0219/xiangflow-ai/issues)
[![GitHub Pull Requests](https://img.shields.io/github/issues-pr/lien0219/xiangflow-ai?style=flat-square)](https://github.com/lien0219/xiangflow-ai/pulls)

![Python](https://img.shields.io/badge/Python-3.10--3.14-3776AB?style=flat-square&logo=python&logoColor=white)
![TypeScript](https://img.shields.io/badge/TypeScript-5.x-3178C6?style=flat-square&logo=typescript&logoColor=white)
![React](https://img.shields.io/badge/React-19-61DAFB?style=flat-square&logo=react&logoColor=black)
![FastAPI](https://img.shields.io/badge/FastAPI-009688?style=flat-square&logo=fastapi&logoColor=white)
![MCP](https://img.shields.io/badge/MCP-Supported-5A67D8?style=flat-square)
![Open Source](https://img.shields.io/badge/Open%20Source-%E2%9D%A4-EA4AAA?style=flat-square)

[Quick Start](#-quick-start) · [Core Capabilities](#-core-capabilities) · [Documentation](#-documentation) · [Contributing](#-contributing) · [GitHub Issues](https://github.com/lien0219/xiangflow-ai/issues)

</div>

## Overview

XiangFlow AI is an open-source AI workflow platform for developers and organizations. Its visual canvas connects large language models, agents, knowledge bases, data sources, APIs, and external tools, helping teams build, test, run, and integrate AI applications efficiently.

The platform brings together visual workflows, agent orchestration, the Model Context Protocol, Skills-oriented capability composition, and retrieval-augmented generation. Complex AI systems can be assembled as modular, reusable, and extensible workflows.

> Connect, orchestrate, and reuse every AI capability.

## ✨ Highlights

| Capability | What it provides |
| --- | --- |
| Visual workflows | Connect models, prompts, tools, knowledge bases, and business logic on a node-based canvas |
| AI agents | Build agents that interpret tasks, select tools, and complete multi-step work |
| Skills extensions | Package domain capabilities with reusable flows, prompts, rules, tools, and components |
| MCP ecosystem | Connect external tools as an MCP client and expose project workflows as MCP tools |
| RAG and knowledge bases | Combine document processing, embeddings, vector search, and contextual generation |
| Multiple model providers | Use major cloud providers, local models, and API-compatible model services |
| Custom components | Extend nodes, tools, data processing, and integrations with Python |
| API services | Integrate workflows through REST APIs, webhooks, and MCP |
| Open deployment | Run locally, build containers, deploy privately, and customize integrations |

## 🧩 Core Capabilities

### Visual AI Workflows

- Build workflows by dragging, connecting, and configuring nodes
- Combine models, prompts, data, tools, and flow-control components
- Pass text, messages, data, and structured results between nodes
- Test workflows interactively in the Playground and inspect execution results
- Import, export, and reuse workflows as JSON
- Run workflows through REST APIs, webhooks, or MCP

### AI Agents

- Configure agents with models, instructions, and context on the visual canvas
- Use built-in components, other agents, and MCP servers as callable tools
- Select tools and execute multi-step tasks based on the request
- Connect conversation memory, knowledge retrieval, and structured output components
- Test agent behavior in the Playground or through APIs

### Skills

Skills are XiangFlow AI's way of organizing reusable AI capabilities. Domain knowledge, task procedures, prompts, rules, tools, and resources can be composed through workflows and custom components, creating clear capability entry points that can be reused across applications.

### MCP

- Connect external MCP servers through the MCP Tools component
- Use STDIO, Streamable HTTP, and compatible SSE transports
- Configure MCP servers from Settings or directly from the canvas sidebar
- Expose project workflows as MCP tools for external clients
- Connect MCP clients such as Cursor, Windsurf, and Claude Desktop

### RAG and Knowledge Bases

- Upload and process documents with text extraction, chunking, and metadata
- Generate vector representations with embedding models
- Perform semantic retrieval through knowledge bases and vector stores
- Add retrieved content to model context for knowledge-grounded answers
- Connect files, databases, websites, and third-party data sources through components

### Model and Component Ecosystem

- Integrate multiple LLM providers, embedding models, and local model services
- Use vector database, data processing, input/output, and tool components
- Create custom Python components and add them to the visual canvas
- Connect business systems through API requests, webhooks, and third-party integrations
- Extend and execute workflows with the LFX runtime

## 🔄 How It Works

```mermaid
flowchart LR
    User[User request] --> Canvas[Visual workflow]
    Canvas --> Agent[AI Agent]
    Canvas --> Skills[Skills composition]
    Canvas --> MCP[MCP Tools]
    Canvas --> RAG[RAG and knowledge base]

    Agent --> Models[Language models]
    Skills --> Components[Flows and custom components]
    MCP --> Services[External services]
    RAG --> Data[(Documents and vectors)]

    Models --> Result[AI application and API]
    Components --> Result
    Services --> Result
    Data --> Result
```

Start with a user or business requirement, compose agents, reusable capabilities, MCP tools, and knowledge retrieval on the canvas, then run the workflow in the interface or integrate it through an API, webhook, or MCP.

## 🎯 Use Cases

| Use case | Description |
| --- | --- |
| Enterprise knowledge assistant | Connect organizational documents, data sources, and models to build retrieval-based question answering |
| AI customer support | Combine agents, knowledge bases, tool calls, and business APIs into controlled support workflows |
| Data analysis agents | Let agents query databases, call APIs, use analysis tools, and produce results |
| Content generation | Orchestrate models, prompts, data processing, and output components into reusable content pipelines |
| Developer tools | Connect coding tools, editors, and development workflows through MCP and reusable capabilities |
| Business process automation | Combine enterprise systems, external APIs, and AI models to automate multi-step tasks |

## 🏗️ Architecture

```mermaid
flowchart TB
    subgraph Experience[Experience Layer]
        Web[React visual canvas]
        Playground[Playground]
        Clients[API and MCP clients]
    end

    subgraph Application[Application Services]
        FastAPI[FastAPI REST API]
        MCPAPI[MCP Server]
        Services[Auth, projects, files, and knowledge bases]
    end

    subgraph Runtime[Orchestration and Runtime]
        Graph[Workflow graph engine]
        LFX[LFX runtime]
        Agents[Agents and tool calling]
        Components[Built-in and custom components]
    end

    subgraph Integrations[Integration Layer]
        Models[Model and embedding services]
        MCPTools[External MCP servers]
        APIs[External APIs and data sources]
        Vectors[Vector stores]
    end

    Storage[(Application database and file storage)]

    Web --> FastAPI
    Playground --> FastAPI
    Clients --> FastAPI
    Clients --> MCPAPI
    FastAPI --> Services
    FastAPI --> Graph
    MCPAPI --> Graph
    Graph --> LFX
    Graph --> Agents
    Graph --> Components
    Agents --> Models
    Agents --> MCPTools
    Components --> APIs
    Components --> Vectors
    Services --> Storage
```

- **Experience layer:** Visual canvas, Playground, and entry points for API and MCP clients.
- **Application services:** FastAPI endpoints for workflows, projects, files, knowledge bases, authentication, and MCP.
- **Orchestration and runtime:** The graph engine and LFX coordinate nodes, data flow, agents, and components.
- **Integration layer:** Model services, MCP servers, business APIs, data sources, and vector stores.

## Technology Stack

| Area | Technology |
| --- | --- |
| Frontend | React 19, TypeScript, Vite, Tailwind CSS, Zustand, XYFlow |
| Backend | Python 3.10–3.14, FastAPI, SQLModel / SQLAlchemy, Alembic |
| Workflow | Langflow graph execution engine, LFX |
| Agents | LangChain ecosystem, tool calling, structured output |
| Protocols | REST API, webhooks, MCP |
| Data storage | SQLite, optional PostgreSQL, file storage |
| Vector search | Components for Chroma, Qdrant, Weaviate, Pinecone, Milvus, FAISS, and more |
| Deployment | Local source build, Docker / Podman, Docker Compose, Dev Containers |

## 🚀 Quick Start

### Requirements

- Python `>=3.10,<3.15`
- Node.js `>=20.19.0` (v22.12 LTS recommended) and npm v10.9+
- `uv >=0.4`
- GNU Make

Windows users should use WSL or the included Dev Container.

### Clone the Repository

With SSH:

```bash
git clone git@github.com:lien0219/xiangflow-ai.git
cd xiangflow-ai
```

Or with HTTPS:

```bash
git clone https://github.com/lien0219/xiangflow-ai.git
cd xiangflow-ai
```

### Run Locally

Install dependencies, build the frontend, and start the application:

```bash
make run_cli
```

Open <http://localhost:7860>. To clear the frontend build cache before restarting, run:

```bash
make run_clic
```

### Development Mode

```bash
make init
```

Start the backend and frontend in separate terminals:

```bash
make backend
```

```bash
make frontend
```

The backend listens on `http://localhost:7860`, and the frontend development server listens on `http://localhost:3000` by default. See the [complete development guide](./DEVELOPMENT.md) for environment setup, testing, and component development.

### Build and Run a Container

The repository includes a container build target for the current source:

```bash
make docker_build DOCKER=docker
docker run --rm -p 7860:7860 langflow:1.10.2
```

## Project Structure

```text
xiangflow-ai/
├── .github/                 # GitHub workflows and repository configuration
├── deploy/                  # Deployment and observability configuration
├── docker/                  # Container builds and development configuration
├── docker_example/          # Docker Compose example
├── docs/                    # Docusaurus documentation
├── scripts/                 # Build, test, and maintenance scripts
├── src/
│   ├── backend/             # FastAPI APIs and application services
│   ├── frontend/            # React / TypeScript web application
│   ├── lfx/                 # Lightweight workflow executor
│   ├── langflow-stepflow/   # Workflow step execution support
│   ├── sdk/                 # Python SDK
│   └── bundles/             # Optional component extension bundles
├── README.md                # Simplified Chinese product overview
├── README_EN.md             # English product overview
├── DEVELOPMENT.md           # Development environment guide
└── CONTRIBUTING.md          # Contribution guide
```

## 📚 Documentation

| Document | Description |
| --- | --- |
| [DEVELOPMENT.md](./DEVELOPMENT.md) | Local development, Dev Containers, and environment setup |
| [CUSTOMIZATION.md](./CUSTOMIZATION.md) | Project maintenance and customization guide |
| [CONTRIBUTING.md](./CONTRIBUTING.md) | Contribution guide |
| [SECURITY.md](./SECURITY.md) | Security policy and vulnerability reporting |
| [CODE_OF_CONDUCT.md](./CODE_OF_CONDUCT.md) | Community code of conduct |
| [LICENSE](./LICENSE) | MIT License and copyright notices |

## 🤝 Contributing

Community contributions are welcome. You can report bugs, suggest features, improve documentation, build components, fix issues, or open a pull request.

- [Open an issue](https://github.com/lien0219/xiangflow-ai/issues)
- [View pull requests](https://github.com/lien0219/xiangflow-ai/pulls)
- [Read the contribution guide](./CONTRIBUTING.md)

## 🙏 Acknowledgements

XiangFlow AI is made possible by the open-source community.

Special thanks to the [Langflow](https://github.com/langflow-ai/langflow) team and its contributors for their outstanding work in visual AI workflow and agent development.

We also appreciate LangChain, FastAPI, React, and the broader open-source ecosystem.

## 📄 License

This project is open source under the [MIT License](./LICENSE).
