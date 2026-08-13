# IMPCC timetable generator — CP-SAT backend (Google Cloud Run)
FROM python:3.11-slim

WORKDIR /app

# Install dependencies first (better layer caching)
COPY backend/requirements.txt ./backend/requirements.txt
RUN pip install --no-cache-dir -r backend/requirements.txt

# Copy the application
COPY backend ./backend
COPY cp_solver.py solver.py ./

ENV PORT=8080
EXPOSE 8080

# Cloud Run sets PORT; default to 8080 for local runs.
CMD ["sh", "-c", "uvicorn backend.main:app --host 0.0.0.0 --port ${PORT:-8080}"]
