#!/bin/bash
echo "🚀 Setting up Prefect Local Environment..."

# Create work pool
echo "📦 Creating work pool 'my-local-pool'..."
prefect work-pool create -t process my-local-pool

# Verify
echo "✅ Work pool created. Verifying..."
prefect work-pool ls

echo "🚀 Starting Prefect Server & Worker..."

# Set API URL
export PREFECT_API_URL="http://127.0.0.1:4200/api"

# Start server in background
echo "📡 Starting Prefect Server..."
prefect server start &
SERVER_PID=$!

# Wait for server to be ready
echo "⏳ Waiting for server to be ready..."
sleep 5

# Start worker in background
echo "👷 Starting Worker..."
prefect worker start -p my-local-pool &
WORKER_PID=$!

echo ""
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "✅ Prefect Server + Worker Started!"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo ""
echo "📊 Server:  http://127.0.0.1:4200"
echo "🔧 API:     http://127.0.0.1:4200/api"
echo ""
echo "📝 Next step: Deploy your flow"
echo "   python 01_getting_started.py"
echo ""
echo "🛑 To stop all:"
echo "   pkill -f 'prefect server'"
echo "   pkill -f 'prefect worker'"
echo ""
echo "Waiting... (Ctrl+C to stop)"
wait