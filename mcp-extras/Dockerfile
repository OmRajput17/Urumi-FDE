FROM python:3.12-slim
COPY --from=ghcr.io/astral-sh/uv:latest /uv /bin/uv
WORKDIR /srv
COPY pyproject.toml uv.lock ./
RUN uv sync --frozen --no-dev --no-install-project
COPY utils_server.py notes_server.py ./
ENV PATH="/srv/.venv/bin:$PATH"
USER 10001
EXPOSE 8000
# One image, two servers: each Deployment picks its script with "command".
CMD ["python", "utils_server.py"]