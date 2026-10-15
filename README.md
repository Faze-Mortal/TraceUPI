# TraceUPI

Explainable UPI Fraud-Ring Investigation MVP for Hackathons.

## Overview & Problem Statement

Unified Payments Interface (UPI) has rapidly become the backbone of real-time digital payments in India. However, this growth has also led to sophisticated fraud patterns, notably organized mule networks and multi-hop laundering rings. Detecting and investigating these syndicates requires moving beyond isolated transaction scoring toward structural graph insights and explainable risk rankings.

**TraceUPI** is designed as an investigative tool to help analysts detect and understand suspicious transaction clusters, explore multi-hop fraud rings, and inspect explainable risk signals in an interactive visualization interface.

## Planned Technology Stack

- **Architecture:** Monorepo with a single co-located backend and frontend
- **Frontend:** React + Vite, Graph Visualization (interactive graph canvas)
- **Backend:** Python FastAPI (REST API routes, validation, orchestration)
- **Machine Learning & Graph Analysis:** Python ML package (graph feature engineering, ranking models)
- **Data Persistence:** In-memory / local execution for hackathon MVP (no external database or separate ML microservice required)

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

- **Status:** **Implementation has not started.**
- The project is currently at the initial repository setup and interface contract alignment stage.
