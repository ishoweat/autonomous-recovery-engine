# Deploying Antigravity to Nebius

This guide explains how to deploy the Antigravity backend as a Nebius Serverless Endpoint and how the sandbox/benchmark runs can use Nebius Serverless Jobs.

## 1. Backend as a Nebius Serverless Endpoint

To host the backend API as a scalable serverless endpoint on Nebius, follow these steps:

1. **Build and push the Docker image** to a container registry accessible to Nebius (e.g., Nebius Container Registry):
   *(Verify exact CLI syntax in official docs)*
   ```bash
   docker build -t <registry-url>/antigravity-backend:latest -f backend/Dockerfile .
   docker push <registry-url>/antigravity-backend:latest
   ```

2. **Deploy the Serverless Endpoint**:
   Use the Nebius CLI or Console to create a new Serverless Endpoint from the image:
   *(Verify exact CLI syntax in official docs)*
   ```bash
   nebius serverless endpoint create \
     --name antigravity-backend \
     --image <registry-url>/antigravity-backend:latest \
     --env NEBIUS_API_KEY=$NEBIUS_API_KEY \
     --env GITHUB_TOKEN=$GITHUB_TOKEN \
     --env ALLOW_MOCK_MODE=true \
     --env PUBLIC_DEMO_MODE=true \
     --env ENABLE_RATE_LIMITING=true \
     --env ENABLE_TAVILY_RESEARCH=true \
     --env TAVILY_API_KEY=$TAVILY_API_KEY \
     --memory 2GB \
     --port 8000
   ```

3. **CORS and Frontend**: 
   Ensure `CORS_ORIGINS` includes your frontend's deployed URL. Configure your deployed frontend's `NEXT_PUBLIC_API_URL` to point to the created Nebius endpoint URL.

## 2. Sandbox and Benchmark via Nebius Serverless Jobs

The verification sandbox currently relies on Docker to isolate tests. In a Nebius deployment, you can offload this to Nebius Serverless Jobs for truly isolated and ephemeral execution without requiring Docker-in-Docker.

1. **Create a Job Definition**:
   Create a job that runs the `pytest` suite for a specific repository.
   *(Verify exact CLI syntax in official docs)*
   ```bash
   nebius serverless job create \
     --name antigravity-sandbox-job \
     --image <registry-url>/antigravity-sandbox:latest \
     --env INCIDENT_ID=<incident-id> \
     --memory 1GB
   ```

2. **Triggering Jobs Dynamically**:
   Update `RecoverySandbox.run_async` in the backend to trigger a Nebius Serverless Job via the Nebius SDK/API instead of a local Docker container. Wait for the job to complete and fetch the logs for the `stdout`/`stderr` verification results.

3. **Benchmarks**:
   Similarly, the benchmark script can be deployed as a batch job on Nebius to evaluate the models continuously over a large set of repositories without tying up your local machine.
