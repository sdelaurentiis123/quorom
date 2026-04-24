# Prebuilt sandbox image for reviewer-submitted Python snippets.
# Keep it small; reviewers get numpy/scipy/pandas/sympy/statsmodels baked in
# so they don't pay pip install per call.
#
# Build: `make sandbox-image`  (= docker build -t quorum-sandbox:latest .)
# Runtime contract: caller mounts /work read-only and runs `python snippet.py`.

FROM python:3.11-slim

# Core scientific stack (always present) + small-pack additions:
#   scikit-learn, seaborn, networkx, scikit-image, pingouin, arviz
# Skipped intentionally: torch, transformers, tokenizers, datasets —
# those double the image size without adding value in a 10-30s sandbox.
RUN pip install --no-cache-dir \
      numpy==1.26.4 scipy==1.13.1 pandas==2.2.2 \
      statsmodels==0.14.2 sympy==1.13.3 matplotlib==3.8.4 \
      scikit-learn==1.5.2 seaborn==0.13.2 networkx==3.3 \
      scikit-image==0.24.0 pingouin==0.5.5 arviz==0.20.0 \
 && find /usr/local/lib/python3.11 -type d -name '__pycache__' -exec rm -rf {} + || true

# Non-root; no shell.
RUN useradd -r -u 1000 -s /usr/sbin/nologin sbx
USER sbx
WORKDIR /work
# Invoker uses `docker run -i ... python -` and pipes code via stdin.
