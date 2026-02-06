#!/bin/bash
# Sonar - Strategic Discovery Wrapper

# 1. Load Vessel Secrets
if [ -f ../vessel/.vessel_env ]; then
    export $(grep -v '^#' ../vessel/.vessel_env | xargs)
fi

# 2. Set Environment
export LD_LIBRARY_PATH="/nix/store/h4qhxh7vwmxgy6w05g0xsf6r1bfi9vga-gcc-15.2.0-lib/lib:/nix/store/l6i35y2hlmdz0hvz690h3k4ilq9ahhzy-zlib-1.3.1/lib:$LD_LIBRARY_PATH"
export OPENAI_API_KEY="ollama"
export OPENAI_BASE_URL="http://192.168.35.1:11434/v1"

cd "$(dirname "$0")"
source .venv/bin/activate

# 3. Start Service (Port 8001)
export SONAR_PORT=8001
exec uvicorn sonar.main:app --host 0.0.0.0 --port 8001 --ssl-keyfile ~/netbox.tail839ce7.ts.net.key --ssl-certfile ~/netbox.tail839ce7.ts.net.crt
