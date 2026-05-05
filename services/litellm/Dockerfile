FROM ghcr.io/berriai/litellm:main-latest

WORKDIR /app

COPY config.yaml .

EXPOSE 8003
CMD ["--config", "config.yaml", "--host", "0.0.0.0", "--port", "8003"]
