# Prebuilt sandbox image for reviewer-submitted Python snippets.
# Keep it small; reviewers get numpy/scipy/pandas/sympy/statsmodels baked in
# so they don't pay pip install per call.
#
# Build: `make sandbox-image`  (= docker build -t quorum-sandbox:latest .)
# Runtime contract: caller mounts /work read-only and runs `python snippet.py`.

FROM python:3.11-slim

RUN pip install --no-cache-dir \
      numpy==1.26.4 scipy==1.13.1 pandas==2.2.2 \
      statsmodels==0.14.2 sympy==1.13.3 \
 && find /usr/local/lib/python3.11 -type d -name '__pycache__' -exec rm -rf {} + || true

# Non-root; no shell.
RUN useradd -r -u 1000 -s /usr/sbin/nologin sbx
USER sbx
WORKDIR /work
# Invoker uses `docker run -i ... python -` and pipes code via stdin.
