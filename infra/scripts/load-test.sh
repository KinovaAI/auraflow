#!/bin/bash
# AuraFlow Simple Load Test
# Usage: ./load-test.sh [base_url] [concurrency] [total_requests]

BASE_URL="${1:-https://api.auraflow.fit}"
CONCURRENCY="${2:-10}"
TOTAL="${3:-100}"

echo "=== AuraFlow Load Test ==="
echo "Target: $BASE_URL"
echo "Concurrency: $CONCURRENCY"
echo "Total requests: $TOTAL"
echo ""

# Test 1: Health endpoint
echo "--- Test 1: Health endpoint (GET /health) ---"
for i in $(seq 1 $TOTAL); do
    curl -s -o /dev/null -w "%{http_code} %{time_total}s\n" "$BASE_URL/health" &
    if (( i % CONCURRENCY == 0 )); then wait; fi
done
wait
echo ""

# Test 2: Auth endpoint (expect 401)
echo "--- Test 2: Login endpoint (POST /api/v1/auth/login/json) ---"
for i in $(seq 1 $((TOTAL / 2))); do
    curl -s -o /dev/null -w "%{http_code} %{time_total}s\n" \
        -X POST "$BASE_URL/api/v1/auth/login/json" \
        -H "Content-Type: application/json" \
        -d '{"email":"loadtest@example.com","password":"wrong"}' &
    if (( i % CONCURRENCY == 0 )); then wait; fi
done
wait
echo ""

echo "=== Load test complete ==="
