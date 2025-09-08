
Carbon-aware LLM Placement App v2 (Prototype)
---------------------------------------------
This enhanced package includes:
- Multi-period MILP prototype (backend/optimizer.py) with PuLP if available; otherwise greedy per-period fallback
- FastAPI backend at backend/main.py exposing POST /optimize
- Streamlit frontend at frontend/streamlit_app.py with map visualization (Plotly)
- Dockerfile + docker-compose for demo deployment (deploy/)
How to run locally:
1. Install dependencies:
   pip install -r requirements.txt
2. Run backend only:
   cd backend
   uvicorn main:app --reload --port 8000
3. Run frontend only:
   streamlit run frontend/streamlit_app.py
4. Or use docker-compose to run both (demo):
   docker build -t carbon_app ./deploy
   docker run -p 8000:8000 -p 8501:8501 carbon_app
Notes:
- The MILP is small-scale and has a short solver time limit (30s). For larger problems increase or use commercial solvers.
- This package intentionally does NOT integrate external carbon APIs (per your request).
