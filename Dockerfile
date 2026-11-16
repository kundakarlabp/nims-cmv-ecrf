FROM python:3.12-slim
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1
WORKDIR /srv
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt && useradd --system --uid 10001 appuser
COPY app/ ./app/
COPY ops/bootstrap_admin.py ops/clinical_schema_bootstrap.py ops/clinical_admin_mfa.py ./
# Git may be cloned with a restrictive umask; appuser still needs to read the source.
RUN chmod -R a+rX /srv/app && chmod a+r /srv/bootstrap_admin.py /srv/clinical_schema_bootstrap.py /srv/clinical_admin_mfa.py
USER appuser
EXPOSE 8000
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000", "--workers", "2", "--proxy-headers", "--forwarded-allow-ips", "*"]
