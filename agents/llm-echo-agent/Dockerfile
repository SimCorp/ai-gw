FROM python:3.12-alpine
WORKDIR /agent
RUN pip install --no-cache-dir httpx
COPY main.py .
CMD ["python", "/agent/main.py"]
