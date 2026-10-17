# Personal AI Operations Agent

**An AI-powered productivity and task management system built with Python, Streamlit, and Google Gemini.**

**Project Status:** In Development 🚧

## Overview

Personal AI Operations Agent is an intelligent productivity application designed to help users transform their goals into structured, actionable plans. It combines generative AI, task prioritization, dependency-aware scheduling, calendar integration, and execution tracking to support more organized and efficient personal workflow management.

The goal is to build an AI-powered operations assistant that helps users plan work, identify priorities, monitor progress, and make better scheduling decisions.

## Key Features

### 1. AI-Powered Task Planning
- Converts user-defined goals into structured task plans using the Google Gemini API.
- Organizes tasks into actionable steps.
- Supports deadline-aware planning.

### 2. Intelligent Task Prioritization
- Ranks tasks using factors such as task importance, deadline urgency, and task dependencies.
- Helps identify high-priority work that needs attention.

### 3. Dependency-Aware Scheduling
- Considers prerequisite relationships between tasks.
- Uses dependency ordering to support logical task execution.
- Validates task schedules to help prevent timing conflicts.

### 4. Google Calendar Integration
- Retrieves calendar events to support calendar-aware planning.
- Helps identify available time slots for scheduling tasks.
- Supports planning around existing commitments.

### 5. Task Tracking and Execution History
- Tracks task status, including Pending, In Progress, Completed, and Blocked.
- Stores task notes and progress information.
- Maintains execution history for better visibility into work completed.

### 6. Daily Focus Assistant
- Highlights recommended tasks and outstanding work.
- Identifies relevant deadline and blocker information.
- Helps users focus on their next actionable steps.

### 7. Document and Email Assistance
- Exports task plans to Word documents.
- Assists in drafting emails using AI.

### 8. Persistent Data Storage
- Uses SQLite to store saved plans and task-tracking information.
- Allows users to revisit previously created plans.

## Technology Stack

| Technology | Purpose |
|---|---|
| Python | Core application logic |
| Streamlit | Interactive web interface |
| Google Gemini API | AI-powered task planning and assistance |
| SQLite | Persistent data storage |
| Google Calendar API | Calendar event integration |
| python-docx | Word document generation |
| Git and GitHub | Version control and source code management |

## Project Architecture

The application is organized into modular components:

- **User Interface:** Streamlit dashboard for interacting with the agent.
- **AI Agents:** Planning, daily assistance, document generation, and email drafting.
- **Scheduling Logic:** Priority scoring, dependency ordering, and timing validation.
- **Calendar Integration:** Google Calendar event retrieval.
- **Database Layer:** SQLite-based plan and execution tracking.
- **Testing:** Automated tests for scheduling, dependencies, priority scoring, and edge cases.

## Getting Started

### Prerequisites

- Python 3.10 or a compatible version supported by the project's dependencies.
- A Google Gemini API key.
- Google Calendar API credentials if you want to use calendar integration.

### Installation

1. Clone the repository:

   ```bash
   git clone https://github.com/JIGYASA-KHANDELWAL/personal-ai-operations-agent.git
   ```

2. Navigate to the project directory:

   ```bash
   cd personal-ai-operations-agent
   ```

3. Create a virtual environment:

   ```bash
   python -m venv .venv
   ```

4. Activate the environment on macOS or Linux:

   ```bash
   source .venv/bin/activate
   ```

5. Install dependencies:

   ```bash
   pip install -r requirements.txt
   ```

6. Configure the required environment variables and API credentials locally. Never commit API keys or OAuth credentials to GitHub.

7. Start the application:

   ```bash
   python -m streamlit run app/main.py
   ```

8. Open the local URL displayed in your terminal, usually `http://localhost:8501`.

> **Note:** Ensure that `requirements.txt` exists and includes the project's actual dependencies. Google Calendar integration may require additional OAuth setup.

## Development Roadmap

- Expand operations-level analytics across saved plans.
- Improve risk detection for overdue, blocked, and deadline-sensitive tasks.
- Enhance safe rescheduling using calendar availability and task dependencies.
- Add plan revision workflows with validation and previews.
- Expand automated testing and error handling.
- Improve interface usability and application reliability.

## Security Considerations

- API keys and OAuth credentials should remain outside version control.
- Local configuration files and tokens should be excluded using `.gitignore`.
- Calendar access should follow the permissions granted by the user.
- Scheduling changes should be reviewed before any external calendar modifications are made.

## Current Status

This project is actively being developed. The implementation and testing of features are ongoing, and the roadmap describes planned improvements rather than guaranteed current functionality.

## Author

**Jigyasa Khandelwal**

GitHub: [JIGYASA-KHANDELWAL](https://github.com/JIGYASA-KHANDELWAL)

---

*Built as an ongoing project exploring AI agents, intelligent scheduling, workflow automation, and productivity systems.*
