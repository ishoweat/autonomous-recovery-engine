FROM python:3.11-alpine

ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1
ENV PIP_DISABLE_PIP_VERSION_CHECK=1

RUN apk add --no-cache \
    git \
    bash \
    build-base \
    libffi-dev

RUN python -m pip install --no-cache-dir \
    pytest \
    pytest-timeout

WORKDIR /workspace

RUN addgroup -S recovery \
    && adduser -S recovery -G recovery

RUN chown -R recovery:recovery /workspace

USER recovery

CMD ["sleep", "infinity"]
