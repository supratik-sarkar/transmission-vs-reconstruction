#!/usr/bin/env bash
set -euo pipefail
if grep -RInE '(sk-[A-Za-z0-9_-]{16,}|ANTHROPIC_API_KEY=.+|GEMINI_API_KEY=.+|OPENAI_API_KEY=.+)' . \
  --exclude-dir=.git --exclude-dir='*.egg-info' --exclude='.env.example' --exclude='verify_no_secrets.sh' | grep -vE 'API_KEY=$'; then
  echo 'Potential secret-like content found.' >&2
  exit 2
fi
echo 'No obvious committed secrets found.'
