FROM ollama/ollama:0.40.3
RUN mkdir -p /models && chown 1000:1000 /models
ENV HOME=/models OLLAMA_MODELS=/models/weights
USER 1000:1000
