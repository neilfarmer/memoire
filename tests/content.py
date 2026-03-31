#!/usr/bin/env python3
"""
Deploy or destroy a realistic set of test content via the Memoire API.

Usage:
    python tests/content.py deploy --pat pat_...
    python tests/content.py destroy --pat pat_...
    make test-deploy-content TEST_PAT=pat_...
    make test-destroy-content TEST_PAT=pat_...

IDs of created resources are saved to .test-content-ids.json so destroy
knows exactly what to remove without touching real data.
"""

import argparse
import json
import os
import sys

import requests

DEFAULT_API_URL = "https://api.memoire-dev.edenforge.io"
IDS_FILE        = os.path.join(os.path.dirname(__file__), ".test-content-ids.json")

BOLD  = "\033[1m"
GREEN = "\033[92m"
RED   = "\033[91m"
RESET = "\033[0m"


# ── HTTP ──────────────────────────────────────────────────────────────────────

def api(method: str, path: str, token: str, api_url: str, body: dict = None) -> requests.Response:
    url     = f"{api_url}{path}"
    headers = {"Authorization": token, "Content-Type": "application/json"}
    kwargs  = {"headers": headers, "timeout": 10}
    if body is not None:
        kwargs["json"] = body
    return requests.request(method, url, **kwargs)


def ok(r: requests.Response, expected: int, label: str) -> dict:
    if r.status_code != expected:
        print(f"  {RED}FAIL{RESET}  {label} — got {r.status_code}: {r.text}")
        sys.exit(1)
    print(f"  {GREEN}OK{RESET}    {label}")
    return r.json()


# ── Deploy ────────────────────────────────────────────────────────────────────

def deploy(token: str, api_url: str) -> None:
    if os.path.exists(IDS_FILE):
        print(f"\n{BOLD}Existing content found — cleaning up first…{RESET}")
        destroy(token, api_url)

    ids = {
        "task_folders": [], "tasks": [],
        "habits": [],
        "journal": [],
        "note_folders": [], "notes": [],
        "goals": [],
        "health": [],
        "nutrition": [],
    }

    print(f"\n{BOLD}Deploying test content…{RESET}")

    # ── Task folders ──────────────────────────────────────────────────────────
    print(f"\n{BOLD}Task Folders{RESET}")
    task_folder_defs = ["Work", "Personal", "Learning", "Side Projects", "Health & Fitness"]
    task_folders = {}
    for name in task_folder_defs:
        r = api("POST", "/tasks/folders", token, api_url, {"name": name})
        d = ok(r, 201, f"Folder: {name}")
        task_folders[name] = d["folder_id"]
        ids["task_folders"].append(d["folder_id"])

    # ── Tasks ─────────────────────────────────────────────────────────────────
    print(f"\n{BOLD}Tasks{RESET}")
    tasks = [
        # Work
        {"title": "Set up CI pipeline",            "folder_id": task_folders["Work"],              "status": "done",        "priority": "high",   "description": "Configure GitHub Actions for automated testing and deployment"},
        {"title": "Write API documentation",        "folder_id": task_folders["Work"],              "status": "in_progress", "priority": "medium", "description": "Document all endpoints in OpenAPI spec", "due_date": "2099-04-15"},
        {"title": "Review pull request #42",        "folder_id": task_folders["Work"],              "status": "todo",        "priority": "high",   "due_date": "2099-04-01"},
        {"title": "Refactor auth middleware",        "folder_id": task_folders["Work"],              "status": "in_progress", "priority": "medium", "description": "Extract token validation into reusable module"},
        {"title": "Fix login redirect bug",          "folder_id": task_folders["Work"],              "status": "done",        "priority": "high",   "description": "Resolved issue with OAuth callback URL losing state"},
        {"title": "Update dependencies",             "folder_id": task_folders["Work"],              "status": "todo",        "priority": "low",    "description": "Bump all packages to latest minor versions"},
        {"title": "Design new dashboard UI",         "folder_id": task_folders["Work"],              "status": "todo",        "priority": "medium", "description": "Wireframes for the new home dashboard in Figma", "due_date": "2099-04-20"},
        {"title": "Performance audit",               "folder_id": task_folders["Work"],              "status": "todo",        "priority": "high",   "description": "Profile cold start times and p99 latency", "due_date": "2099-06-30"},
        # Personal
        {"title": "Book dentist appointment",        "folder_id": task_folders["Personal"],          "status": "todo",        "priority": "medium", "due_date": "2099-04-05"},
        {"title": "Renew car insurance",             "folder_id": task_folders["Personal"],          "status": "todo",        "priority": "high",   "due_date": "2099-04-10"},
        {"title": "Plan summer holiday",             "folder_id": task_folders["Personal"],          "status": "in_progress", "priority": "low",    "description": "Research destinations, compare flights"},
        {"title": "Sort out tax return",             "folder_id": task_folders["Personal"],          "status": "todo",        "priority": "high",   "due_date": "2099-05-31"},
        {"title": "Fix leaking kitchen tap",         "folder_id": task_folders["Personal"],          "status": "done",        "priority": "medium"},
        # Learning
        {"title": "Finish Rust book chapter 10",     "folder_id": task_folders["Learning"],          "status": "in_progress", "priority": "medium"},
        {"title": "Complete AWS SAA practice exam",  "folder_id": task_folders["Learning"],          "status": "todo",        "priority": "medium", "due_date": "2099-05-01"},
        {"title": "Watch DynamoDB deep dive talk",   "folder_id": task_folders["Learning"],          "status": "done",        "priority": "low"},
        {"title": "Work through Advent of Code",     "folder_id": task_folders["Learning"],          "status": "in_progress", "priority": "low",    "description": "Currently on day 14"},
        # Side Projects
        {"title": "Set up domain for finance tracker","folder_id": task_folders["Side Projects"],    "status": "done",        "priority": "medium"},
        {"title": "Build transaction import CSV parser","folder_id": task_folders["Side Projects"],  "status": "in_progress", "priority": "high",   "description": "Support Monzo, Revolut, and Barclays CSV formats"},
        {"title": "Write landing page copy",         "folder_id": task_folders["Side Projects"],    "status": "todo",        "priority": "low"},
        {"title": "Set up error monitoring",         "folder_id": task_folders["Side Projects"],    "status": "todo",        "priority": "medium", "due_date": "2099-05-15"},
        # Health & Fitness
        {"title": "Book physio appointment",         "folder_id": task_folders["Health & Fitness"],  "status": "todo",        "priority": "high",   "due_date": "2099-04-03"},
        {"title": "Research 5K training plan",       "folder_id": task_folders["Health & Fitness"],  "status": "done",        "priority": "medium"},
        {"title": "Buy new running shoes",           "folder_id": task_folders["Health & Fitness"],  "status": "todo",        "priority": "medium"},
    ]
    for t in tasks:
        r = api("POST", "/tasks", token, api_url, t)
        d = ok(r, 201, t["title"])
        ids["tasks"].append(d["task_id"])

    # ── Habits ────────────────────────────────────────────────────────────────
    print(f"\n{BOLD}Habits{RESET}")
    habits = [
        {"name": "Morning run",                "notify_time": "06:45"},
        {"name": "Read for 30 minutes",        "notify_time": "21:30"},
        {"name": "Drink 8 glasses of water"},
        {"name": "Meditate",                   "notify_time": "07:30"},
        {"name": "Evening journal",            "notify_time": "22:00"},
        {"name": "No phone first hour",        "notify_time": "07:00"},
        {"name": "Stretch / mobility work",    "notify_time": "19:00"},
        {"name": "Vitamins & supplements"},
        {"name": "Cold shower"},
        {"name": "Review daily goals",         "notify_time": "08:30"},
    ]
    for h in habits:
        r = api("POST", "/habits", token, api_url, h)
        d = ok(r, 201, h["name"])
        ids["habits"].append(d["habit_id"])

    # ── Journal ───────────────────────────────────────────────────────────────
    print(f"\n{BOLD}Journal{RESET}")
    entries = [
        {"date": "2099-03-01", "mood": "great",  "title": "Fresh start",
         "body": "Starting the month with clear goals. Feeling focused and ready to tackle the backlog. Shipped the PAT auth feature today — something I've been putting off for weeks.",
         "tags": ["goals", "productivity", "shipped"]},
        {"date": "2099-03-05", "mood": "good",   "title": "Mid-week check-in",
         "body": "Made solid progress on the API docs. Still need to finish the authentication section. Had a good 1:1 with the team — everyone seems aligned on priorities.",
         "tags": ["work", "progress", "team"]},
        {"date": "2099-03-08", "mood": "okay",   "title": "Feeling scattered",
         "body": "Jumped between too many things today. Didn't finish anything substantial. Need to be more intentional about time-blocking tomorrow.",
         "tags": ["focus", "reflection"]},
        {"date": "2099-03-10", "mood": "okay",   "title": "Debugging day",
         "body": "Spent the whole day chasing a race condition in the token refresh flow. No feature progress but learned a lot about DynamoDB conditional writes.",
         "tags": ["debugging", "learning", "dynamodb"]},
        {"date": "2099-03-12", "mood": "good",   "title": "Back on track",
         "body": "Fixed the race condition with a conditional expression. Elegant solution in the end. Also hit my 7-day meditation streak.",
         "tags": ["wins", "mindfulness"]},
        {"date": "2099-03-15", "mood": "great",  "title": "Breakthrough",
         "body": "Finally cracked the auth bug. The fix was three lines. Shipped it, wrote the tests, updated the docs. One of those days where everything clicks.",
         "tags": ["wins", "shipped", "flow"]},
        {"date": "2099-03-18", "mood": "good",   "title": "Planning sprint 4",
         "body": "Good sprint planning session. Scope is realistic for once. Prioritised the dashboard redesign and dependency updates. Team morale is high.",
         "tags": ["planning", "team", "sprint"]},
        {"date": "2099-03-20", "mood": "good",   "title": "Side project momentum",
         "body": "Put two hours into the finance tracker after work. The CSV parser is coming together. Monzo and Revolut formats done, Barclays is next.",
         "tags": ["side-project", "coding"]},
        {"date": "2099-03-22", "mood": "bad",    "title": "Low energy",
         "body": "Didn't sleep well. Got through the essentials but nothing creative. Skipped the run but did stretch. Sometimes you just have to do less.",
         "tags": ["health", "rest", "self-compassion"]},
        {"date": "2099-03-25", "mood": "great",  "title": "Strong week finish",
         "body": "Knocked off four tasks from the backlog. Run felt great — new 5K PB. Cooked a proper meal for the first time in a week.",
         "tags": ["wins", "fitness", "balance"]},
    ]
    for e in entries:
        body = {k: v for k, v in e.items() if k != "date"}
        r = api("PUT", f"/journal/{e['date']}", token, api_url, body)
        ok(r, 200, e["title"])
        ids["journal"].append(e["date"])

    # ── Notes ─────────────────────────────────────────────────────────────────
    print(f"\n{BOLD}Notes{RESET}")

    def make_folder(name, parent_id=None):
        body = {"name": name}
        if parent_id:
            body["parent_id"] = parent_id
        r = api("POST", "/notes/folders", token, api_url, body)
        d = ok(r, 201, f"Folder: {name}")
        ids["note_folders"].append(d["folder_id"])
        return d["folder_id"]

    def make_note(folder_id, title, body_text, tags=None):
        payload = {"folder_id": folder_id, "title": title, "body": body_text}
        if tags:
            payload["tags"] = tags
        r = api("POST", "/notes", token, api_url, payload)
        d = ok(r, 201, f"Note: {title}")
        ids["notes"].append(d["note_id"])

    work_f    = make_folder("Work")
    arch_f    = make_folder("Architecture",   parent_id=work_f)
    runbooks_f= make_folder("Runbooks",       parent_id=work_f)
    meetings_f= make_folder("Meeting Notes",  parent_id=work_f)
    personal_f= make_folder("Personal")
    recipes_f = make_folder("Recipes",        parent_id=personal_f)
    travel_f  = make_folder("Travel",         parent_id=personal_f)
    learning_f= make_folder("Learning")

    make_note(arch_f, "System Overview",
        "# System Overview\n\nServerless architecture on AWS.\n\n## Components\n- **API Gateway** — HTTP API with JWT + Lambda authorizer\n- **Lambda** — one function per feature\n- **DynamoDB** — on-demand, user_id PK\n- **Cognito** — OIDC identity provider\n- **CloudFront + S3** — static frontend",
        ["architecture", "aws"])

    make_note(arch_f, "DynamoDB Schema",
        "# DynamoDB Schema\n\nAll tables use `user_id` (String) as partition key and `{feature}_id` (String) as sort key.\n\n## Tables\n| Table | SK |\n|---|---|\n| tasks | task_id |\n| habits | habit_id |\n| journal | entry_date |\n| notes | note_id |\n| goals | goal_id |\n\nOn-demand billing. No GSIs except tokens table.",
        ["dynamodb", "schema"])

    make_note(arch_f, "Auth Flow",
        "# Auth Flow\n\n1. User authenticates via Cognito OIDC\n2. Frontend stores ID token\n3. All requests send `Authorization: <token>`\n4. Lambda authorizer validates JWT or PAT\n5. `user_id` injected into Lambda context\n6. All DynamoDB ops scoped to `user_id`",
        ["auth", "cognito", "security"])

    make_note(runbooks_f, "Deploy Checklist",
        "# Deploy Checklist\n\n## Before\n- [ ] All tests pass locally\n- [ ] Changelog updated\n- [ ] Feature flags checked\n\n## Deploy\n```bash\nmake deploy-auto\n```\n\n## After\n- [ ] Smoke test in prod\n- [ ] Check CloudWatch for errors\n- [ ] Invalidate CloudFront if needed",
        ["devops", "checklist"])

    make_note(runbooks_f, "Incident Response",
        "# Incident Response\n\n## Triage\n1. Check CloudWatch alarms\n2. Identify affected Lambda(s)\n3. Pull recent logs\n\n## Rollback\n```bash\naws lambda update-function-code --function-name <fn> --s3-key <prev-key>\n```\n\n## Post-mortem\n- Write timeline within 24h\n- 5 whys analysis\n- Action items with owners",
        ["devops", "incidents"])

    make_note(meetings_f, "Sprint 3 Planning",
        "# Sprint 3 Planning — 2099-03-01\n\n## Goals\n- Ship PAT authentication\n- Update OpenAPI docs\n- Fix login redirect bug\n\n## Capacity\n3 devs × 10 days = 30 dev-days\nEstimated: 24 dev-days\n\n## Decisions\n- Defer mobile push notifications to S4\n- PAT tokens never expire (review in Q3)",
        ["sprint", "planning"])

    make_note(meetings_f, "Sprint 3 Retro",
        "# Sprint 3 Retro — 2099-03-15\n\n## What went well\n- PAT feature shipped on time\n- Zero production incidents\n- Good async communication\n\n## What to improve\n- Estimations were too optimistic on the auth refactor\n- Need better staging environment parity\n\n## Actions\n- [ ] Set up staging auto-deploy (@neil)\n- [ ] Add estimation buffer for auth work (@team)",
        ["sprint", "retro"])

    make_note(recipes_f, "Weeknight Staples",
        "# Weeknight Staples\n\n## Quick pasta (20 min)\n- 200g pasta\n- Tinned tomatoes, garlic, basil\n- Parmesan\n\n## Stir fry (15 min)\n- Rice, chicken or tofu\n- Soy sauce, sesame oil, ginger\n- Whatever veg is in the fridge\n\n## Sheet pan salmon (25 min)\n- Salmon fillets\n- Broccoli, cherry tomatoes\n- Olive oil, lemon, garlic",
        ["cooking", "recipes"])

    make_note(travel_f, "Summer Trip Research",
        "# Summer Trip Research\n\n## Options\n| Destination | Cost est. | Notes |\n|---|---|---|\n| Lisbon | £600 | Great food, easy flight |\n| Tbilisi | £700 | Off the beaten track |\n| Sardinia | £900 | Beach, need car |\n\n## Must haves\n- Direct flight or max 1 stop\n- At least 10 days\n- Good food scene",
        ["travel", "planning"])

    make_note(learning_f, "Rust Notes",
        "# Rust Notes\n\n## Ownership rules\n1. Each value has one owner\n2. Only one owner at a time\n3. Value dropped when owner goes out of scope\n\n## Borrowing\n- `&T` — immutable reference\n- `&mut T` — mutable reference (only one at a time)\n\n## Lifetimes\nAnnotate when compiler can't infer: `fn longest<'a>(x: &'a str, y: &'a str) -> &'a str`",
        ["rust", "programming", "learning"])

    make_note(learning_f, "AWS SAA Exam Notes",
        "# AWS SAA Key Topics\n\n## Compute\n- EC2 instance types, Auto Scaling, ALB vs NLB\n- Lambda limits: 15min timeout, 10GB memory, 1000 concurrent\n\n## Storage\n- S3 storage classes and lifecycle policies\n- EBS vs EFS vs S3\n\n## Database\n- RDS Multi-AZ vs Read Replicas\n- DynamoDB: partition key design, GSIs, DAX\n- Aurora Serverless use cases",
        ["aws", "certification", "learning"])

    # ── Goals ─────────────────────────────────────────────────────────────────
    print(f"\n{BOLD}Goals{RESET}")
    goals = [
        {"title": "Run a 5K in under 25 minutes",   "description": "Train consistently 3x/week to hit sub-25 min 5K",        "target_date": "2099-06-01",  "status": "active"},
        {"title": "Read 12 books this year",         "description": "One per month — mix of fiction, non-fiction, and tech",  "target_date": "2099-12-31",  "status": "active"},
        {"title": "Launch finance tracker v1",       "description": "Ship a working MVP with CSV import and basic dashboards", "target_date": "2099-09-01",  "status": "active"},
        {"title": "Pass AWS Solutions Architect",    "description": "Study 1 hour/day for 8 weeks then book the exam",        "target_date": "2099-07-15",  "status": "active"},
        {"title": "Learn conversational Spanish",    "description": "Complete Duolingo A1 + A2, then find a language partner", "target_date": "2099-12-01",  "status": "active"},
        {"title": "Reduce phone screen time",        "description": "Cap at 2 hours/day average across the week",                                             "status": "active"},
        {"title": "Save £5,000 emergency fund",      "description": "3 months expenses in an easy-access account",            "target_date": "2099-10-01",  "status": "active"},
        {"title": "Ship open source contribution",   "description": "Get a meaningful PR merged in a project I use",          "target_date": "2099-06-30",  "status": "active"},
        {"title": "30-day meditation streak",        "description": "Minimum 10 minutes daily using Waking Up app",                                          "status": "completed"},
        {"title": "Declutter and sell unused items", "description": "Clear out the spare room and list on eBay",               "target_date": "2099-04-30",  "status": "active"},
    ]
    for g in goals:
        r = api("POST", "/goals", token, api_url, g)
        d = ok(r, 201, g["title"])
        ids["goals"].append(d["goal_id"])

    # ── Health / exercise logs ─────────────────────────────────────────────────
    print(f"\n{BOLD}Health{RESET}")
    health_logs = [
        {"date": "2099-03-18", "notes": "Easy Monday — active recovery", "exercises": [
            {"name": "Walking",          "duration": 45, "notes": "Lunchtime walk, kept it easy"},
            {"name": "Mobility routine", "duration": 20, "notes": "Hip flexors and shoulders"},
        ]},
        {"date": "2099-03-19", "notes": "Upper body push", "exercises": [
            {"name": "Bench press",      "sets": 4, "reps": 8,  "weight": 75, "notes": "Last set was tough"},
            {"name": "Overhead press",   "sets": 3, "reps": 10, "weight": 45},
            {"name": "Tricep dips",      "sets": 3, "reps": 15},
            {"name": "Lateral raises",   "sets": 3, "reps": 15, "weight": 10},
        ]},
        {"date": "2099-03-21", "notes": "5K tempo run — new PB", "exercises": [
            {"name": "Running",          "duration": 24, "notes": "5K in 24:42 — new personal best!"},
            {"name": "Cool down walk",   "duration": 10},
            {"name": "Stretch",          "duration": 10},
        ]},
        {"date": "2099-03-22", "notes": "Pull day", "exercises": [
            {"name": "Pull-ups",         "sets": 4, "reps": 8,  "notes": "Strict form, full ROM"},
            {"name": "Barbell rows",     "sets": 3, "reps": 10, "weight": 60},
            {"name": "Face pulls",       "sets": 3, "reps": 15, "weight": 20},
            {"name": "Bicep curls",      "sets": 3, "reps": 12, "weight": 14},
        ]},
        {"date": "2099-03-24", "notes": "Leg day", "exercises": [
            {"name": "Squats",           "sets": 4, "reps": 8,  "weight": 90, "notes": "Hit a new working weight"},
            {"name": "Romanian deadlift","sets": 3, "reps": 10, "weight": 70},
            {"name": "Leg press",        "sets": 3, "reps": 12, "weight": 120},
            {"name": "Calf raises",      "sets": 4, "reps": 20},
        ]},
        {"date": "2099-03-26", "notes": "Full body conditioning", "exercises": [
            {"name": "Kettlebell swings","sets": 4, "reps": 20, "weight": 24},
            {"name": "Push-ups",         "sets": 3, "reps": 20},
            {"name": "Box jumps",        "sets": 3, "reps": 10},
            {"name": "Battle ropes",     "duration": 10, "notes": "4x30s intervals"},
            {"name": "Plank",            "duration": 5,  "notes": "5x60s"},
        ]},
        {"date": "2099-03-28", "notes": "Long run — base building", "exercises": [
            {"name": "Running",          "duration": 50, "notes": "8K easy pace, heart rate zone 2"},
            {"name": "Foam rolling",     "duration": 15},
        ]},
    ]
    for log in health_logs:
        body = {"exercises": log["exercises"], "notes": log["notes"]}
        r = api("PUT", f"/health/{log['date']}", token, api_url, body)
        ok(r, 200, f"Health log {log['date']}")
        ids["health"].append(log["date"])

    # ── Nutrition logs ────────────────────────────────────────────────────────
    print(f"\n{BOLD}Nutrition{RESET}")
    nutrition_logs = [
        {"date": "2099-03-18", "notes": "Recovery day — lighter eating", "meals": [
            {"name": "Porridge with banana and honey",  "calories": 380, "protein": 12, "carbs": 68, "fat": 7},
            {"name": "Lentil and vegetable soup",       "calories": 340, "protein": 18, "carbs": 48, "fat": 6},
            {"name": "Apple and almond butter",         "calories": 220, "protein": 5,  "carbs": 24, "fat": 12},
            {"name": "Grilled chicken and roasted veg", "calories": 490, "protein": 44, "carbs": 32, "fat": 18},
        ]},
        {"date": "2099-03-19", "notes": "Higher protein — push day", "meals": [
            {"name": "Scrambled eggs on sourdough",     "calories": 460, "protein": 28, "carbs": 36, "fat": 20},
            {"name": "Protein shake (pre-workout)",     "calories": 180, "protein": 30, "carbs": 8,  "fat": 3},
            {"name": "Chicken rice bowl",               "calories": 580, "protein": 48, "carbs": 62, "fat": 12},
            {"name": "Greek yogurt with mixed nuts",    "calories": 280, "protein": 18, "carbs": 16, "fat": 16},
            {"name": "Steak with sweet potato",         "calories": 620, "protein": 52, "carbs": 44, "fat": 22},
        ]},
        {"date": "2099-03-21", "notes": "Carb up for PB run", "meals": [
            {"name": "Overnight oats with berries",     "calories": 420, "protein": 14, "carbs": 72, "fat": 8},
            {"name": "Banana (pre-run)",                "calories": 100, "protein": 1,  "carbs": 25, "fat": 0},
            {"name": "Pasta with tomato and turkey",    "calories": 640, "protein": 42, "carbs": 80, "fat": 14},
            {"name": "Protein bar",                     "calories": 220, "protein": 20, "carbs": 22, "fat": 8},
            {"name": "Salmon with quinoa and broccoli", "calories": 560, "protein": 48, "carbs": 42, "fat": 20},
        ]},
        {"date": "2099-03-24", "notes": "Leg day — big eating day", "meals": [
            {"name": "Full English (no sausage)",       "calories": 520, "protein": 32, "carbs": 38, "fat": 26},
            {"name": "Protein shake",                   "calories": 180, "protein": 30, "carbs": 8,  "fat": 3},
            {"name": "Tuna and rice cakes",             "calories": 280, "protein": 28, "carbs": 28, "fat": 4},
            {"name": "Beef stir fry with noodles",      "calories": 680, "protein": 46, "carbs": 72, "fat": 20},
            {"name": "Cottage cheese and pineapple",    "calories": 200, "protein": 24, "carbs": 20, "fat": 2},
        ]},
        {"date": "2099-03-26", "notes": "Conditioning day", "meals": [
            {"name": "Banana and peanut butter",        "calories": 320, "protein": 8,  "carbs": 42, "fat": 14},
            {"name": "Chicken wrap with avocado",       "calories": 540, "protein": 38, "carbs": 44, "fat": 22},
            {"name": "Mixed nuts and dried mango",      "calories": 260, "protein": 6,  "carbs": 28, "fat": 14},
            {"name": "Turkey mince with veg and rice",  "calories": 580, "protein": 50, "carbs": 58, "fat": 12},
        ]},
        {"date": "2099-03-28", "notes": "Long run fueling", "meals": [
            {"name": "Toast with eggs and avocado",     "calories": 480, "protein": 22, "carbs": 42, "fat": 24},
            {"name": "Energy gel (mid-run)",            "calories": 90,  "protein": 0,  "carbs": 22, "fat": 0},
            {"name": "Recovery shake",                  "calories": 300, "protein": 28, "carbs": 36, "fat": 4},
            {"name": "Baked cod with sweet potato",     "calories": 480, "protein": 46, "carbs": 48, "fat": 8},
            {"name": "Dark chocolate (2 squares)",      "calories": 100, "protein": 2,  "carbs": 10, "fat": 6},
        ]},
    ]
    for log in nutrition_logs:
        body = {"meals": log["meals"], "notes": log["notes"]}
        r = api("PUT", f"/nutrition/{log['date']}", token, api_url, body)
        ok(r, 200, f"Nutrition log {log['date']}")
        ids["nutrition"].append(log["date"])

    # ── Save & summarise ──────────────────────────────────────────────────────
    with open(IDS_FILE, "w") as f:
        json.dump(ids, f, indent=2)

    totals = {k: len(v) for k, v in ids.items()}
    grand  = sum(totals.values())
    print(f"\n{GREEN}{BOLD}Done — {grand} resources created:{RESET}")
    for key, count in totals.items():
        print(f"  {count:>3}  {key.replace('_', ' ')}")
    print(f"\nIDs saved to {IDS_FILE}\n")


# ── Destroy ───────────────────────────────────────────────────────────────────

def destroy(token: str, api_url: str) -> None:
    if not os.path.exists(IDS_FILE):
        print(f"No IDs file found at {IDS_FILE} — nothing to destroy.")
        sys.exit(0)

    with open(IDS_FILE) as f:
        ids = json.load(f)

    print(f"\n{BOLD}Destroying test content…{RESET}")

    def delete(path, label):
        r = api("DELETE", path, token, api_url)
        status = f"{GREEN}OK{RESET}" if r.status_code in (204, 404) else f"{RED}FAIL ({r.status_code}){RESET}"
        print(f"  {status}    {label}")

    for task_id   in ids.get("tasks",         []): delete(f"/tasks/{task_id}",         f"task      {task_id}")
    for folder_id in ids.get("task_folders",  []): delete(f"/tasks/folders/{folder_id}",f"task folder {folder_id}")
    for habit_id  in ids.get("habits",        []): delete(f"/habits/{habit_id}",        f"habit     {habit_id}")
    for date      in ids.get("journal",       []): delete(f"/journal/{date}",           f"journal   {date}")
    for note_id   in ids.get("notes",         []): delete(f"/notes/{note_id}",          f"note      {note_id}")
    for folder_id in reversed(ids.get("note_folders", [])): delete(f"/notes/folders/{folder_id}", f"note folder {folder_id}")
    for goal_id   in ids.get("goals",         []): delete(f"/goals/{goal_id}",          f"goal      {goal_id}")
    for date      in ids.get("health",        []): delete(f"/health/{date}",            f"health    {date}")
    for date      in ids.get("nutrition",     []): delete(f"/nutrition/{date}",         f"nutrition {date}")

    os.remove(IDS_FILE)
    print(f"\n{GREEN}{BOLD}Done — all test content removed.{RESET}\n")


# ── Entry point ───────────────────────────────────────────────────────────────

def main() -> None:
    parser = argparse.ArgumentParser(description="Deploy or destroy Memoire test content")
    parser.add_argument("action", choices=["deploy", "destroy"])
    parser.add_argument("--pat",     default=os.environ.get("TEST_PAT", ""), help="Personal Access Token")
    parser.add_argument("--api-url", default=os.environ.get("API_URL", DEFAULT_API_URL).rstrip("/"))
    args = parser.parse_args()

    if not args.pat:
        print("No PAT provided. Pass --pat or set TEST_PAT.")
        sys.exit(1)

    if args.action == "deploy":
        deploy(args.pat, args.api_url)
    else:
        destroy(args.pat, args.api_url)


if __name__ == "__main__":
    main()
