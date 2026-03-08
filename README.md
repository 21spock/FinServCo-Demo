# Devin Jira Control Plane

A clean Python demo repo for a Devin take-home.

This app is built to support a Jira-first story:
- Jira is the backlog source of truth
- Devin scopes each ticket against the codebase
- a human approves the right tickets to act on
- Devin fix sessions get launched on the approved tickets
- the app reports Devin status back in one place

## Why this repo exists

This is not meant to be a production backlog platform. It is a clean demo repo you can upload to GitHub and use to:
1. create 6 intentional GitHub issues
2. mirror those issues into Jira tickets
3. ask Devin to scope the tickets
4. choose which ones Devin should execute
5. show status / PR communication back to the team

## Demo flow

1. Start the app
2. Click **Scope issues with Devin**
3. Review the three recommendation lanes:
   - Ready for Devin
   - Needs clarification
   - Senior review
4. Select the green issues
5. Click **Launch Devin fixes**
6. Click **Sync Devin status**
7. Show the sessions table as the team visibility layer

## Quick start

```bash
python3.11 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
python -m uvicorn app.main:app --reload
```

Open http://127.0.0.1:8000

## What to customize

- `app/main.py` — seeded tickets, scoping behavior, session status simulation
- `app/templates/index.html` — page copy and demo framing
- `.env.example` — placeholder config fields for Devin/Jira/GitHub

## GitHub issues to create

Mirror these tickets in GitHub and Jira:
- FIN-101 Disable live Devin launch when DEVIN_API_KEY is missing
- FIN-102 Add filter chips for ticket lanes on the issues table
- FIN-103 Improve backlog import reliability
- FIN-104 Make progress updates more useful for engineering leadership
- FIN-105 Add approval roles before allowing live ticket execution
- FIN-106 Support multi-repo routing for enterprise rollout

## Notes

This starter keeps the demo reliable by storing scoped recommendations locally and simulating status transitions. That lets you show intake, scoping, approval, and execution cleanly even before a full live Devin + Jira integration is wired end-to-end.
