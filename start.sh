#!/bin/bash
echo "Starting OilMind..."
uvicorn backend.main:app --host 0.0.0.0 --port 8000 --workers 1 &
echo "Waiting for FastAPI to initialize..."
sleep 15
echo "Starting Streamlit frontend on port 8501..."
streamlit run frontend/app.py --server.port 8501 --server.address 0.0.0.0 --server.headless true --server.enableCORS false --server.enableXsrfProtection false
