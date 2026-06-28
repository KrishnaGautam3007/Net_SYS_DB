# NOTE: docker-compose builds ALL services (collector + agents) from the
# repository ROOT using the root ./Dockerfile, with the agent services
# overriding the CMD via `command:` in docker-compose.yml. This file is kept
# to match the specified folder structure. The `COPY ../requirements.txt`
# below cannot cross the build context, so this Dockerfile is NOT referenced
# by docker-compose — use the root Dockerfile for agent builds.
FROM python:3.11-slim
WORKDIR /app
COPY ../requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY . .
ENV PYTHONUNBUFFERED=1
CMD ["python", "agent.py"]
