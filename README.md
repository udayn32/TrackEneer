# TrackEneer

TrackEneer is a student productivity and learning platform with scheduling, study support, placement preparation, insights, mentoring, and knowledge graph features.

## Project Structure

- `client/`: Frontend application
- `server/`: Backend services and APIs
- `notification-service/`: Notification support module

## Main Features

- Smart schedule and timetable management
- Study and knowledge tracking tools
- Career readiness and placement modules
- Insights and mentor support workflows

## Requirements

- Node.js and npm
- Python 3.10+
- MongoDB and Neo4j for the backend features that use them
- Environment variables and API keys needed by the server modules

## How To Run

### 1. Start the frontend

```bash
cd client
npm install
npm run dev
```

The frontend runs with Next.js in development mode.

### 2. Start the backend

```bash
cd server
pip install -r requirements.txt
uvicorn app:app --reload
```

This starts the FastAPI backend locally.

### 3. Start the notification service

```bash
cd notification-service
npm install
npm run dev
```

Use this service if you want push notification support during development.

## Suggested Local Startup Order

1. Start MongoDB and Neo4j
2. Start the backend from `server/`
3. Start the notification service from `notification-service/`
4. Start the frontend from `client/`

## Note

Environment variables, API keys, and local model assets should be configured separately before running the full system.
