
# Dockerfile for running FastAPI + Streamlit in same container for demo only
FROM python:3.11-slim
WORKDIR /app
COPY . /app
RUN pip install --no-cache-dir -r /app/requirements.txt
EXPOSE 8000 8501
# start both uvicorn and streamlit via bash script
COPY deploy/start.sh /app/deploy/start.sh
RUN chmod +x /app/deploy/start.sh
CMD ["/app/deploy/start.sh"]
