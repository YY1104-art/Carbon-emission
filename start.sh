
#!/usr/bin/env bash
# start both backend and frontend for demo
uvicorn backend.main:app --host 0.0.0.0 --port 8000 --workers 1 &
streamlit run frontend/streamlit_app.py --server.port 8501 --server.headless true
