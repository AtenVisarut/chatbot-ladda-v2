# Deployment Guide for Vercel

This guide will help you deploy the Chatbot Ladda application to Vercel.

## Prerequisites

1.  **Vercel Account**: Sign up at [vercel.com](https://vercel.com/).
2.  **Vercel CLI** (Optional but recommended): Install via `npm i -g vercel`.
3.  **Supabase Project**: Ensure you have your Supabase URL and Key.
4.  **LINE Bot Channel**: Ensure you have your Channel Access Token and Secret.
5.  **OpenAI API Key**: Ensure you have your OpenAI API Key.

## Steps to Deploy

### Option 1: Deploy via Vercel Dashboard (Recommended)

1.  Push your code to a GitHub repository.
2.  Log in to Vercel and click **"Add New..."** -> **"Project"**.
3.  Import your GitHub repository.
4.  In the **"Configure Project"** section:
    - **Framework Preset**: Select `Other` (or leave as is, Vercel usually detects Python).
    - **Root Directory**: Leave as `./`.
5.  **Environment Variables**: Expand the section and add the following variables:
    - `LINE_CHANNEL_ACCESS_TOKEN`: Your LINE Channel Access Token
    - `LINE_CHANNEL_SECRET`: Your LINE Channel Secret
    - `OPENAI_API_KEY`: Your OpenAI API Key
    - `SUPABASE_URL`: Your Supabase URL
    - `SUPABASE_KEY`: Your Supabase Service Role Key (or Anon Key if RLS is set up)
    - `ADMIN_USERNAME`: Set a username for the dashboard login
    - `ADMIN_PASSWORD`: Set a password for the dashboard login
    - `SECRET_KEY`: A random string for session security (e.g., generate one with `openssl rand -hex 32`)
    - `PYTHON_VERSION`: `3.11` (Optional, but good to specify)
6.  Click **"Deploy"**.

### Option 2: Deploy via CLI

1.  Open your terminal in the project directory.
2.  Run `vercel login` if you haven't already.
3.  Run `vercel`.
4.  Follow the prompts:
    - Set up and deploy? [Y/n] **y**
    - Which scope? (Select your account)
    - Link to existing project? [N/y] **n**
    - Project name? (Press Enter for default)
    - In which directory is your code located? **./**
    - Want to modify these settings? [N/y] **n**
5.  Once the project is linked, go to the Vercel Dashboard to set the **Environment Variables** (as listed in Option 1).
6.  After setting variables, run `vercel --prod` to redeploy with the new environment variables.

## Verifying Deployment

1.  Visit your deployment URL (e.g., `https://your-project.vercel.app`).
    - You should see the API status page.
2.  Test the `/health` endpoint: `https://your-project.vercel.app/health`.
3.  **Important**: Update your LINE Bot Webhook URL in the LINE Developers Console to:
    - `https://your-project.vercel.app/webhook`
4.  Test the bot by sending a message or an image.

## Troubleshooting

- **500 Internal Server Error**: Check the "Logs" tab in your Vercel dashboard for detailed error messages.
- **Module Not Found**: Ensure all dependencies are listed in `requirements.txt`.
- **Timeout**: Vercel Serverless Functions have a default timeout (usually 10s or 60s depending on plan). If your AI processing takes longer, you might need to optimize or upgrade.
