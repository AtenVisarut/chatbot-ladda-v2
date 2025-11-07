# Deployment Guide

Complete guide for deploying the LINE Plant Disease Detection Bot to production.

## Quick Start

```bash
# 1. Install dependencies
pip install -r requirements.txt

# 2. Configure environment
cp .env.example .env
# Edit .env with your API keys

# 3. Setup Pinecone
python setup_pinecone.py

# 4. Populate products
python populate_products.py

# 5. Run server
python main.py
```

## Deployment Options

### Option 1: Google Cloud Run (Recommended)

**Advantages:**
- Serverless, auto-scaling
- Pay per use
- Easy HTTPS setup
- Good for LINE webhooks

**Steps:**

```bash
# 1. Install Google Cloud SDK
# https://cloud.google.com/sdk/docs/install

# 2. Login and set project
gcloud auth login
gcloud config set project YOUR_PROJECT_ID

# 3. Build and deploy
gcloud run deploy line-plant-bot \
  --source . \
  --platform managed \
  --region asia-southeast1 \
  --allow-unauthenticated \
  --set-env-vars LINE_CHANNEL_ACCESS_TOKEN=$LINE_CHANNEL_ACCESS_TOKEN,LINE_CHANNEL_SECRET=$LINE_CHANNEL_SECRET,GEMINI_API_KEY=$GEMINI_API_KEY,PINECONE_API_KEY=$PINECONE_API_KEY,PINECONE_INDEX_NAME=$PINECONE_INDEX_NAME

# 4. Get your service URL
gcloud run services describe line-plant-bot --region asia-southeast1 --format 'value(status.url)'
```

**Set LINE Webhook:**
```
https://your-service-url.run.app/webhook
```

### Option 2: Docker + Any Cloud Provider

**Build Docker image:**

```bash
# Build
docker build -t line-plant-bot .

# Test locally
docker run -p 8000:8000 --env-file .env line-plant-bot

# Test endpoint
curl http://localhost:8000/health
```

**Deploy to cloud:**

```bash
# AWS ECR + ECS
aws ecr create-repository --repository-name line-plant-bot
docker tag line-plant-bot:latest YOUR_ECR_URL/line-plant-bot:latest
docker push YOUR_ECR_URL/line-plant-bot:latest

# Google Container Registry + Cloud Run
docker tag line-plant-bot gcr.io/YOUR_PROJECT/line-plant-bot
docker push gcr.io/YOUR_PROJECT/line-plant-bot
gcloud run deploy --image gcr.io/YOUR_PROJECT/line-plant-bot

# Azure Container Registry + Container Instances
az acr create --resource-group myResourceGroup --name myregistry --sku Basic
docker tag line-plant-bot myregistry.azurecr.io/line-plant-bot
docker push myregistry.azurecr.io/line-plant-bot
```

### Option 3: Heroku

**Steps:**

```bash
# 1. Install Heroku CLI
# https://devcenter.heroku.com/articles/heroku-cli

# 2. Login
heroku login

# 3. Create app
heroku create line-plant-bot

# 4. Set environment variables
heroku config:set LINE_CHANNEL_ACCESS_TOKEN=your_token
heroku config:set LINE_CHANNEL_SECRET=your_secret
heroku config:set GEMINI_API_KEY=your_key
heroku config:set PINECONE_API_KEY=your_key
heroku config:set PINECONE_INDEX_NAME=plant-products

# 5. Create Procfile
echo "web: uvicorn main:app --host 0.0.0.0 --port \$PORT" > Procfile

# 6. Deploy
git init
git add .
git commit -m "Initial commit"
git push heroku main

# 7. Get URL
heroku open
```

### Option 4: AWS Elastic Beanstalk

**Steps:**

```bash
# 1. Install EB CLI
pip install awsebcli

# 2. Initialize
eb init -p python-3.11 line-plant-bot --region ap-southeast-1

# 3. Create environment
eb create line-plant-bot-env

# 4. Set environment variables
eb setenv LINE_CHANNEL_ACCESS_TOKEN=your_token \
  LINE_CHANNEL_SECRET=your_secret \
  GEMINI_API_KEY=your_key \
  PINECONE_API_KEY=your_key \
  PINECONE_INDEX_NAME=plant-products

# 5. Deploy
eb deploy

# 6. Get URL
eb status
```

### Option 5: Railway

**Steps:**

1. Go to [railway.app](https://railway.app)
2. Click "New Project" → "Deploy from GitHub repo"
3. Select your repository
4. Add environment variables in Railway dashboard
5. Railway will auto-deploy

**Set webhook:**
```
https://your-app.railway.app/webhook
```

### Option 6: Render

**Steps:**

1. Go to [render.com](https://render.com)
2. Click "New" → "Web Service"
3. Connect your GitHub repository
4. Configure:
   - Build Command: `pip install -r requirements.txt`
   - Start Command: `uvicorn main:app --host 0.0.0.0 --port $PORT`
5. Add environment variables
6. Deploy

### Option 7: DigitalOcean App Platform

**Steps:**

```bash
# 1. Install doctl
# https://docs.digitalocean.com/reference/doctl/how-to/install/

# 2. Authenticate
doctl auth init

# 3. Create app spec (app.yaml)
cat > app.yaml << EOF
name: line-plant-bot
services:
- name: web
  github:
    repo: your-username/your-repo
    branch: main
  run_command: uvicorn main:app --host 0.0.0.0 --port 8080
  envs:
  - key: LINE_CHANNEL_ACCESS_TOKEN
    value: your_token
  - key: LINE_CHANNEL_SECRET
    value: your_secret
  - key: GEMINI_API_KEY
    value: your_key
  - key: PINECONE_API_KEY
    value: your_key
  - key: PINECONE_INDEX_NAME
    value: plant-products
EOF

# 4. Deploy
doctl apps create --spec app.yaml
```

## Environment Variables

Required for all deployments:

```bash
LINE_CHANNEL_ACCESS_TOKEN=your_line_channel_access_token
LINE_CHANNEL_SECRET=your_line_channel_secret
GEMINI_API_KEY=your_gemini_api_key
PINECONE_API_KEY=your_pinecone_api_key
PINECONE_INDEX_NAME=plant-products
```

## LINE Webhook Configuration

After deployment:

1. Go to [LINE Developers Console](https://developers.line.biz/console/)
2. Select your channel
3. Go to "Messaging API" tab
4. Set Webhook URL: `https://your-domain.com/webhook`
5. Click "Verify" (should return success)
6. Enable "Use webhook"
7. Disable "Auto-reply messages"
8. Disable "Greeting messages"

## SSL/HTTPS Requirements

LINE requires HTTPS for webhooks. All recommended platforms provide HTTPS automatically:

- ✅ Google Cloud Run: Auto HTTPS
- ✅ Heroku: Auto HTTPS
- ✅ Railway: Auto HTTPS
- ✅ Render: Auto HTTPS
- ✅ DigitalOcean: Auto HTTPS

For custom domains, use:
- Let's Encrypt (free)
- Cloudflare (free)
- AWS Certificate Manager (free)

## Monitoring and Logs

### Google Cloud Run
```bash
# View logs
gcloud logging read "resource.type=cloud_run_revision" --limit 50

# Stream logs
gcloud logging tail "resource.type=cloud_run_revision"
```

### Heroku
```bash
# View logs
heroku logs --tail
```

### Docker
```bash
# View logs
docker logs -f container_id
```

## Performance Optimization

### 1. Use Production ASGI Server

```bash
# Install gunicorn
pip install gunicorn

# Run with workers
gunicorn main:app -w 4 -k uvicorn.workers.UvicornWorker --bind 0.0.0.0:8000
```

### 2. Enable Caching

Add Redis for caching frequent queries:

```python
import redis
cache = redis.Redis(host='localhost', port=6379)
```

### 3. Connection Pooling

Already implemented with httpx.AsyncClient

### 4. Resource Limits

Set appropriate limits in deployment:

```yaml
# Cloud Run
resources:
  limits:
    memory: 512Mi
    cpu: 1
```

## Scaling Considerations

### Vertical Scaling
- Increase memory/CPU per instance
- Good for: Heavy AI processing

### Horizontal Scaling
- Increase number of instances
- Good for: High request volume

### Auto-scaling Configuration

**Google Cloud Run:**
```bash
gcloud run services update line-plant-bot \
  --min-instances 1 \
  --max-instances 10 \
  --concurrency 80
```

**AWS ECS:**
```json
{
  "scalingPolicy": {
    "targetValue": 70.0,
    "predefinedMetricType": "ECSServiceAverageCPUUtilization"
  }
}
```

## Cost Estimation

### Google Cloud Run (Recommended)
- Free tier: 2M requests/month
- After: ~$0.40 per 1M requests
- Estimated: $5-20/month for small-medium usage

### Heroku
- Hobby: $7/month
- Standard: $25/month

### Railway
- Free tier: $5 credit/month
- After: Pay as you go

### AWS
- t3.micro: ~$8/month
- t3.small: ~$16/month

## Troubleshooting

### Webhook not receiving events
1. Check webhook URL is HTTPS
2. Verify webhook is enabled in LINE console
3. Check signature verification
4. Review server logs

### Slow response times
1. Check Gemini API latency
2. Optimize Pinecone queries
3. Add caching layer
4. Increase server resources

### Out of memory errors
1. Increase memory limits
2. Optimize image processing
3. Use streaming for large responses

### API rate limits
1. Implement request queuing
2. Add retry logic with exponential backoff
3. Cache frequent queries

## Security Checklist

- ✅ Verify LINE webhook signatures
- ✅ Use environment variables for secrets
- ✅ Enable HTTPS only
- ✅ Implement rate limiting
- ✅ Validate all inputs
- ✅ Use non-root user in Docker
- ✅ Keep dependencies updated
- ✅ Monitor for suspicious activity
- ✅ Implement proper error handling
- ✅ Log security events

## Backup and Recovery

### Pinecone Data
```python
# Export vectors
vectors = index.fetch(ids=all_ids)
# Save to file
with open('backup.json', 'w') as f:
    json.dump(vectors, f)
```

### Environment Variables
- Store in secure vault (AWS Secrets Manager, Google Secret Manager)
- Keep encrypted backup

## Support and Maintenance

### Regular Tasks
- Monitor error rates
- Review logs weekly
- Update dependencies monthly
- Rotate API keys quarterly
- Review costs monthly

### Health Monitoring
```bash
# Setup monitoring endpoint
curl https://your-domain.com/health

# Expected response
{
  "status": "healthy",
  "services": {
    "gemini": "ok",
    "pinecone": "ok",
    "line": "ok"
  }
}
```

---

Need help? Check the main README.md or contact support.
