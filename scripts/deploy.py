"""
Universal deployment script for Plant Disease Bot
Works on both Windows and Unix-like systems
"""
import os
import sys
import subprocess
import platform
import shutil

def check_requirements():
    """Check if all required tools are installed"""
    # Check for gcloud CLI
    if shutil.which('gcloud') is None:
        print("❌ gcloud CLI not found. Please install it first:")
        print("   https://cloud.google.com/sdk/docs/install")
        sys.exit(1)
    
    # Check for .env file
    if not os.path.exists('.env'):
        print("❌ .env file not found!")
        print("   Please create .env file with your credentials")
        sys.exit(1)

def build_docker_image():
    """Build the Docker image"""
    print("🔧 Building Docker image...")
    try:
        subprocess.run(['docker', 'build', '-t', 'plant-disease-bot', '.'], check=True)
        print("✅ Docker image built successfully")
    except subprocess.CalledProcessError as e:
        print(f"❌ Failed to build Docker image: {e}")
        sys.exit(1)

def deploy_to_cloud_run():
    """Deploy to Google Cloud Run"""
    try:
        print("🚀 Deploying to Google Cloud Run...")
        # Get project ID
        result = subprocess.run(['gcloud', 'config', 'get-value', 'project'], 
                              capture_output=True, text=True, check=True)
        project_id = result.stdout.strip()

        # Deploy command
        deploy_cmd = [
            'gcloud', 'run', 'deploy', 'plant-disease-bot',
            '--source', '.',
            '--platform', 'managed',
            '--region', 'asia-southeast1',
            '--allow-unauthenticated',
            '--project', project_id
        ]
        
        subprocess.run(deploy_cmd, check=True)
        print("✅ Deployment successful!")
        
    except subprocess.CalledProcessError as e:
        print(f"❌ Deployment failed: {e}")
        sys.exit(1)

def main():
    """Main deployment process"""
    print("🚀 Starting deployment process...")
    print(f"Platform detected: {platform.system()}")
    
    # Run checks
    check_requirements()
    
    # Build and deploy
    build_docker_image()
    deploy_to_cloud_run()
    
    print("\n✨ Deployment completed successfully!")

if __name__ == '__main__':
    main()