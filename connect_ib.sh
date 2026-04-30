#!/bin/bash
curl -s -X POST http://localhost:8000/ib/connect \
  -H "Content-Type: application/json" \
  -d '{"host":"172.18.0.1","port":4001}'
echo ""
echo "--- Status after connect ---"
curl -s http://localhost:8000/ib/status
