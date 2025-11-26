# Deployment Guide for Fly.io

This guide will help you deploy the Chatbot Ladda application to Fly.io.

## Prerequisites

1.  **Fly.io Account**: Sign up at [fly.io](https://fly.io/).
2.  **flyctl CLI**: Install the Fly.io command line tool.
    - **Windows (PowerShell)**: `iwr https://fly.io/install.ps1 -useb | iex`
    - **Mac/Linux**: `curl -L https://fly.io/install.sh | sh`

## Steps to Deploy

### 1. Login to Fly.io

Open your terminal and run:

```bash
fly auth login
```

### 2. Initialize App (If not already done)

Since I've already created `fly.toml`, you might just need to launch.

```bash
fly launch --no-deploy
```

- If it asks to copy configuration, say **Yes**.
- If it asks to tweak settings, you can review them, but the provided `fly.toml` should work.

### 3. Set Environment Variables (Secrets)

Fly.io uses "secrets" for sensitive environment variables. Run the following command (replace values with your actual keys):

```bash
fly secrets set \
  LINE_CHANNEL_ACCESS_TOKEN="your_token_here" \
  LINE_CHANNEL_SECRET="your_secret_here" \
  OPENAI_API_KEY="your_openai_key_here" \
  SUPABASE_URL="your_supabase_url_here" \
  SUPABASE_KEY="your_supabase_key_here" \
  ADMIN_USERNAME="admin" \
  ADMIN_PASSWORD="your_password" \
  SECRET_KEY="your_random_secret_key"
```

### 4. Deploy

Run the deployment command:

```bash
fly deploy
```

## Verifying Deployment

1.  Once deployed, Fly.io will give you a hostname (e.g., `https://chatbot-ladda.fly.dev`).
2.  Test the health endpoint: `https://chatbot-ladda.fly.dev/health`.
3.  **Important**: Update your LINE Bot Webhook URL in the LINE Developers Console to:
    - `https://chatbot-ladda.fly.dev/webhook`

## Troubleshooting

- **fly.toml not found**: Ensure you are in the root directory of the project.
- **Port issues**: Ensure `fly.toml` has `internal_port = 8000` matching the Dockerfile.
- **Memory issues**: If the bot crashes, you might need to increase memory: `fly scale memory 1024`.
