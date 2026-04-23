# TacklNest
**A Unified Task, Request, Ticket, and Appointments Manager**

---

## Overview
TacklNest is a web-based work management system built with Flask and MongoDB. It centralizes:
- Tasks
- Requests
- Tickets
- Appointments
- Feedback

### Value
- One system instead of many tools
- Role-based access keeps the right people accountable
- Clean, fast interface — no bloat
- Better visibility across all work in one dashboard

---

## Tech Stack
- **Backend:** Python / Flask
- **Database:** MongoDB Atlas
- **Frontend:** Jinja2 templates, vanilla JS/CSS
- **Deployment:** GitHub Actions → EC2 (via SSH)

---

## Running Locally

```bash
# Create and activate virtual environment
python -m venv venv
venv\Scripts\activate        # Windows
source venv/bin/activate     # Mac/Linux

# Install dependencies
pip install -r requirement.txt

# Start the server (runs on port 5055)
python app.py
```

---

## Core Functionality

- [x] Create items (Tasks, Requests, Tickets)
- [x] View all items by type
- [x] Edit items via modal
- [x] Delete items
- [x] Assign items to users
- [x] Status tracking: Open / In Progress / Completed
- [x] Store description, assigned person, status, created date, due date
- [ ] Priority levels (Low, Medium, High)

---

## Search & Filtering

- [x] Search by description or assignee (live filter)
- [x] Filter by status (Open / In Progress / Completed)
- [ ] Filter by assigned user (dropdown)
- [ ] Sort by due date, created date, or priority

---

## Dashboard

- [x] Total item count
- [x] Open items count
- [x] In Progress count
- [x] Completed count
- [x] Breakdown by type (Tasks, Requests, Tickets)
- [x] Work summary with progress bars
- [x] Recent items table (clickable, links to item)
- [ ] Bar / pie charts
- [ ] Trend tracking over time

---

## Appointments

- [x] Schedule with title, date, start time, end time
- [x] Invite a team member
- [x] Optional description
- [x] View upcoming appointments list
- [x] Calendar view (current month)
- [x] Navigate ±2 months on the calendar
- [x] Appointments filtered per user (created by or invited)
- [x] Edit and delete appointments

---

## Feedback

- [x] Submit feedback with date and text
- [x] Thank-you confirmation after submission
- [x] Option to submit another or return to home

---

## Users & Access Control

- [x] User registration and login
- [x] First-time password setup flow
- [x] Role-based access: **Admin**, **User**, **Low**
  - **Admin** — sees and manages all items; manages their team
  - **User** — sees all items; can assign to peers under same manager
  - **Low** — sees only items assigned to them
- [x] "My Work" view — items assigned to the logged-in user
- [x] Appointments filtered to user's own or invited
- [ ] Edit/delete permissions enforced by role (UI-level only currently)

---

## Security

- [x] Authentication required on all routes (`@login_required`)
- [x] Passwords hashed with Werkzeug (`generate_password_hash`)
- [x] Session-based auth with Flask sessions
- [x] Input validation on required fields (client + server)
- [ ] MongoDB credentials moved to environment variables (currently hardcoded)

---

## Data Integrity

- [x] Consistent date formatting across all views (`MM/DD/YYYY`)
- [x] Missing fields handled safely (display `—` when empty)
- [x] Empty states shown when no items exist

---

## Deployment

Pushing to `main` triggers GitHub Actions (`.github/workflows/deploy.yml`), which:
1. SSHs into the EC2 instance
2. Pulls the latest code
3. Rebuilds the virtual environment
4. Kills the running Flask process and restarts via `nohup`

**Required GitHub Secrets:** `EC2_HOST`, `EC2_USER`, `EC2_SSH_KEY`

---

## Future Enhancements

- [ ] Priority levels on items (Low / Medium / High)
- [ ] Filter and sort controls on item list pages
- [ ] Dashboard bar / pie charts
- [ ] Activity log per item
- [ ] Comments on items
- [ ] Real-time updates (WebSockets)
- [ ] Move database credentials to environment variables
- [ ] Role-enforced edit/delete (server-side permission checks)
