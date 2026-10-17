# TraceUPI

Explainable UPI Fraud-Ring Investigation MVP for Hackathons.

## Overview & Problem Statement

Unified Payments Interface (UPI) has rapidly become the backbone of real-time digital payments in India. However, this growth has also led to sophisticated fraud patterns, notably organized mule networks and multi-hop laundering rings. Detecting and investigating these syndicates requires moving beyond isolated transaction scoring toward structural graph insights and explainable risk rankings.

**TraceUPI** is designed as an investigative tool to help analysts detect and understand suspicious transaction clusters, explore multi-hop fraud rings, and inspect explainable risk signals in an interactive visualization interface.

## Technology Stack

- **Architecture:** Monorepo with co-located backend and frontend
- **Frontend:** React 19 + TypeScript, Vite, interactive SVG evidence graph canvas
- **Backend:** Python FastAPI (REST API routes, validation against Contract v1.2, in-memory state orchestration)
- **Machine Learning & Graph Analysis:** Graph feature engineering (25 features), anomaly ranking model, and rule-based baselines
- **Data Persistence:** In-memory execution with local datasets and pre-trained model artifact

## Team Responsibilities

- **Team Member 1 (You):**
  - ML pipeline and model development
  - Graph feature engineering
  - Graph visualization and interactive frontend
- **Amishi:**
  - FastAPI backend architecture and routing
  - Request/response validation against interface contracts
  - Integration with the ML module

## Synthetic Data Notice

> **Important:** All transaction records, account identifiers, Virtual Payment Addresses (VPAs), and related entities used or generated within this project are **entirely synthetic**. They are created solely for experimentation, evaluation, and demonstration purposes, and do not represent real-world customer financial data or real UPI accounts.

## Model Interpretation Note

> **Note on Scoring:** The risk scores produced by the model are **uncalibrated ranking scores** intended for prioritizing investigative workflows and highlighting anomalies. They do **not** represent calibrated statistical probabilities of fraud.

## Project Status

- **Status:** **Active / Post-Hackathon Refinement.**
- Implementation aligned with API Contract v1.2 (`contracts/CONTRACT.md`).
- Placed 5th out of 100 teams at the Code-e-Manipal 2.0 hackathon.
- Working features: pipeline orchestration, alert queue, explainable evidence graph, counterfactual simulation, review workflow, and historical replay analysis.

## Getting Started

### Prerequisites

- Python 3.11+
- Node.js 18+ and npm

### Backend Setup & Execution

1. Create and activate a Python virtual environment:
   ```bash
   python -m venv .venv
   # Windows:
   .venv\Scripts\activate
   # Linux/macOS:
   source .venv/bin/activate
   ```
2. Install runtime dependencies:
   ```bash
   pip install -r requirements.txt
   ```
3. Start the FastAPI development server:
   ```bash
   uvicorn backend.main:app --port 8000
   ```
   The backend API will be available at `http://127.0.0.1:8000`.

4. Run backend tests:
   ```bash
   pytest -q
   ```

### Frontend Setup & Execution

1. Install frontend dependencies:
   ```bash
   npm --prefix frontend install
   ```
2. Start the Vite development server:
   ```bash
   npm --prefix frontend run dev
   ```
   The UI will be accessible at `http://localhost:5173`. Requests to `/api/*` are proxied to the local backend at `http://127.0.0.1:8000`.

3. Run frontend tests:
   ```bash
   npm --prefix frontend test
   ```

4. Run frontend lint and build:
   ```bash
   npm --prefix frontend run lint
   npm --prefix frontend run build
   ```
