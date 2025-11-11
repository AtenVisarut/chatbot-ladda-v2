#!/bin/bash
# Quick Deploy Script for Google Cloud Run

echo "🚀 Deploying Plant Disease Bot to Google Cloud Run..."
echo ""

# Check if gcloud is installed
if ! command -v gcloud &> /dev/null; then
    echo "❌ gcloud CLI not found. Please install it first:"
    echo "   https://cloud.google.com/sdk/docs/install"
    exit 1
fi

# Check if .env file exists
if [ ! -f .env ]; then
    echo "❌ .env file not found!"
    echo "   Please create .env file with your credentials"
    exit 1
fi

# Load environment variables
export $(cat .env | grep -v '^#' | xargs)

# Confirm deployment
echo "📋 Deployment Configuration:"
echo "   Project: plant-disease-bot"
echo "   Region: asia-southeast1"
echo "   Service: plant-disease-bot"
echo ""
read -p "Continue? (y/n) " -n 1 -r
echo ""

if [[ ! $REPLY =~ ^[Yy]$ ]]; then
    echo "❌ Deployment cancelled"
    exit 1
fi

# Deploy
echo "🔨 Building and deploying..."
gcloud run deploy plant-disease-bot \
  --source . \
  --platform managed \
  --region asia-southeast1 \
  --allow-unauthenticated \
  --set-env-vars "LINE_CHANNEL_ACCESS_TOKEN=${LINE_CHANNEL_ACCESS_TOKEN}" \
  --set-env-vars "LINE_CHANNEL_SECRET=${LINE_CHANNEL_SECRET}" \
  --set-env-vars "OPENAI_API_KEY=${OPENAI_API_KEY}" \
  --set-env-vars "SUPABASE_URL=${SUPABASE_URL}" \
  --set-env-vars "SUPABASE_KEY=${SUPABASE_KEY}"

if [ $? -eq 0 ]; then
    echo ""
    echo "✅ Deployment successful!"
    echo ""
    echo "📝 Next steps:"
    echo "   1. Copy the service URL from above"
    echo "   2. Go to LINE Developers Console"
    echo "   3. Set Webhook URL: https://YOUR-URL/webhook"
    echo "   4. Verify webhook"
    echo "   5. Test by sending an image to your LINE bot"
    echo ""
else
    echo ""
    echo "❌ Deployment failed!"
    echo "   Check the error messages above"
    exit 1
fi
