#!/usr/bin/env bash
# Build a self-contained release in .box/ for an Amp Box:
#   .box/python/  relocatable CPython (python-build-standalone, via uv)
#   .box/site/    runtime dependencies (from uv.lock, no dev deps)
#   .box/app/     the slate package source, with the built frontend
#   .box/run.sh   the service entry point
# Boxes do not guarantee a Python runtime, so we ship our own.
set -euo pipefail
cd "$(dirname "$0")/.."

PY_VERSION="$(cat .python-version 2>/dev/null || echo 3.13)"
rm -rf .box && mkdir -p .box

# Frontend
(cd src/slate/web/frontend && pnpm install --frozen-lockfile && pnpm build)

# Interpreter
UV_PYTHON_INSTALL_DIR="$PWD/.box/pythons" uv python install "$PY_VERSION"
PY_BIN="$(UV_PYTHON_INSTALL_DIR="$PWD/.box/pythons" uv python find --managed-python "$PY_VERSION")"
PY_ROOT="$(cd "$(dirname "$PY_BIN")/.." && pwd -P)"
mv "$PY_ROOT" .box/python
rm -rf .box/pythons

# Dependencies
uv export --frozen --no-dev --no-hashes --no-emit-project -o .box/requirements.txt
uv pip install --python .box/python/bin/python3 --target .box/site -r .box/requirements.txt

# App source plus the built frontend (no node_modules)
mkdir -p .box/app
cp -R src/slate .box/app/slate
rm -rf .box/app/slate/web/frontend
mkdir -p .box/app/slate/web/frontend
cp -R src/slate/web/frontend/dist .box/app/slate/web/frontend/dist
find .box/app -name __pycache__ -prune -exec rm -rf {} +

cat > .box/run.sh <<'EOF'
#!/bin/sh
here="$(cd "$(dirname "$0")" && pwd)"
export PYTHONPATH="$here/app:$here/site"
export PYTHONDONTWRITEBYTECODE=1
# asyncpg's ssl=verify-full needs a CA bundle; Boxes do not promise one.
export PGSSLROOTCERT="$here/site/certifi/cacert.pem"
# Secrets copied onto the Box with `amp boxes cp` (KEY='value' lines), kept out
# of Git and transcripts. Values here override deployment env and secrets.
secrets="${AMP_DEPLOYMENT_DATA_DIRECTORY:-}/secrets.env"
if [ -f "$secrets" ]; then set -a; . "$secrets"; set +a; fi
exec "$here/python/bin/python3" -m slate
EOF
chmod +x .box/run.sh

# Smoke test the bundle in isolation.
.box/python/bin/python3 -I -c "import sys; sys.path[:0]=['.box/app','.box/site']; import slate.app" \
  >/dev/null
du -sh .box
