@echo off
REM Quick Deploy Script for Google Cloud Run (Windows)

echo 🚀 Deploying Plant Disease Bot to Google Cloud Run...
echo.

REM Check if gcloud is installed
where gcloud >nul 2>nul
if %ERRORLEVEL% NEQ 0 (
    echo ❌ gcloud CLI not found. Please install it first:
    echo    https://cloud.google.com/sdk/docs/install
    exit /b 1
)

REM Check if .env file exists
if not exist .env (
    echo ❌ .env file not found!
    echo    Please create .env file with your credentials
    exit /b 1
)

REM Load environment variables
for /f "tokens=*" %%a in ('type .env ^| findstr /v "^#"') do set %%a

REM Confirm deployment
echo 📋 Deployment Configuration:
echo    Project: plant-disease-bot
echo    Region: asia-southeast1
echo    Service: plant-disease-bot
echo.
set /p CONFIRM="Continue? (y/n): "

if /i not "%CONFIRM%"=="y" (
    echo ❌ Deployment cancelled
    exit /b 1
)

REM Deploy
echo 🔨 Building and deploying...
gcloud run deploy plant-disease-bot ^
  --source . ^
  --platform managed ^
  --region asia-southeast1 ^
  --allow-unauthenticated ^
  --set-env-vars "LINE_CHANNEL_ACCESS_TOKEN=%LINE_CHANNEL_ACCESS_TOKEN%" ^
  --set-env-vars "LINE_CHANNEL_SECRET=%LINE_CHANNEL_SECRET%" ^
  --set-env-vars "OPENAI_API_KEY=%OPENAI_API_KEY%" ^
  --set-env-vars "SUPABASE_URL=%SUPABASE_URL%" ^
  --set-env-vars "SUPABASE_KEY=%SUPABASE_KEY%"

if %ERRORLEVEL% EQU 0 (
    echo.
    echo ✅ Deployment successful!
    echo.
    echo 📝 Next steps:
    echo    1. Copy the service URL from above
    echo    2. Go to LINE Developers Console
    echo    3. Set Webhook URL: https://YOUR-URL/webhook
    echo    4. Verify webhook
    echo    5. Test by sending an image to your LINE bot
    echo.
) else (
    echo.
    echo ❌ Deployment failed!
    echo    Check the error messages above
    exit /b 1
)
