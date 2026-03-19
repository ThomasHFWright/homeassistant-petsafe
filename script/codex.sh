#!/usr/bin/env bash
set -euo pipefail

# Ensure system trust store is present for network operations
apt-get update
apt-get install -y ca-certificates libturbojpeg
update-ca-certificates

PY_VERSION="3.14.2"
PYENV_ROOT="$(pyenv root)"

if [ -d "$PYENV_ROOT/.git" ]; then
  echo "Updating pyenv so Python $PY_VERSION is available..."
  git -C "$PYENV_ROOT" fetch --tags origin
  git -C "$PYENV_ROOT" pull --ff-only origin master
fi

echo "Ensuring Python $PY_VERSION via pyenv..."
pyenv install -s "$PY_VERSION"

pyenv local "$PY_VERSION"
PYTHON="python"

# Ensure pip is available and up to date
"$PYTHON" -m ensurepip --upgrade
"$PYTHON" -m pip install --upgrade pip
"$PYTHON" -m pip install -r requirements.txt

# Disable certificate verification for Python globally via sitecustomize
USER_SITE="$($PYTHON -m site --user-site)"
mkdir -p "$USER_SITE"
cat > "$USER_SITE/sitecustomize.py" <<'PY'
import ssl
ssl._create_default_https_context = ssl._create_unverified_context
PY

# Point Python and common tooling to the certifi CA bundle and persist exports
CERT_BUNDLE="$($PYTHON -m certifi)"
for var in SSL_CERT_FILE REQUESTS_CA_BUNDLE PIP_CERT CURL_CA_BUNDLE GIT_SSL_CAINFO; do
  export "$var=$CERT_BUNDLE"
  if ! grep -q "$var" ~/.bashrc 2>/dev/null; then
    echo "export $var=$CERT_BUNDLE" >> ~/.bashrc
  fi
done

export PYTHONHTTPSVERIFY=0
if ! grep -q PYTHONHTTPSVERIFY ~/.bashrc 2>/dev/null; then
  echo "export PYTHONHTTPSVERIFY=0" >> ~/.bashrc
fi

echo "Create .secrets/PETSAFE.env"
echo "Copy secrets PETSAFE_CODEX_EMAIL and PETSAFE_CODEX_PASSWORD"
echo "to PETSAFE_EMAIL and PETSAFE_PASSWORD environment variables."

# Ensure required env vars exist
: "${PETSAFE_CODEX_EMAIL?Environment variable PETSAFE_CODEX_EMAIL is not set}"
: "${PETSAFE_CODEX_PASSWORD?Environment variable PETSAFE_CODEX_PASSWORD is not set}"

# Create secrets directory
mkdir -p .secrets

# Write secrets to env file
cat > .secrets/PETSAFE.env <<ENV
PETSAFE_EMAIL=${PETSAFE_CODEX_EMAIL}
PETSAFE_PASSWORD=${PETSAFE_CODEX_PASSWORD}
ENV

echo "Wrote credentials to .secrets/PETSAFE.env"