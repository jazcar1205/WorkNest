# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

WorkNest is a unified work management system for tasks, requests, tickets, and appointments. It is a Flask + MongoDB application with Jinja2 templates and vanilla JS/CSS frontend.

## Running the App

```bash
# Install dependencies (use virtual environment)
pip install -r requirement.txt

# Run locally (starts on port 5055)
python app.py
```

There are no test or lint commands configured.

## Deployment

Pushing to `main` triggers GitHub Actions (`.github/workflows/deploy.yml`), which SSHs into an EC2 instance and runs `run.sh`. The script pulls latest code, rebuilds the venv, kills any running Flask process, and restarts it via `nohup`.

Required GitHub secrets: `EC2_HOST`, `EC2_USER`, `EC2_SSH_KEY`.

## Architecture

**Single-file backend** — all routes and MongoDB logic live in `app.py`. The app connects to MongoDB Atlas (`type-db` database) with four collections: `tasks`, `requests`, `tickets`, `appointments`.

**Route pattern:**
- Collection views (`/openTasks`, `/openRequests`, `/openTickets`, `/appointments`, `/assigned`) — query MongoDB and render templates
- `/Dashboard` — aggregates counts across all collections by status
- `/create` + `create_item` (POST) — item creation form and handler
- `/update_item`, `/delete_item` (POST) — AJAX endpoints called from modals in item list templates

**Frontend pattern** — `base.html` provides the nav shell; child templates extend it. Item tables use a shared modal pattern (edit/delete) that calls the AJAX endpoints above. No JS framework — all interactivity is vanilla JS inline in templates.

**Status values:** `Open`, `In Progress`, `Completed`
**Item types:** Task, Request, Ticket

## Known Limitations (from README)

- Login page (`/`, `login.html`) exists but has no authentication logic
- No search or filtering
- No priority tracking
- MongoDB connection string is hardcoded in `app.py`