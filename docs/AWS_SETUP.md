# AWS S3 Setup Guide for IAM Identity Center (SSO)

This guide will help you set up programmatic access to your S3 bucket through
IAM Identity Center, allowing you stream AWS-hosted data with SeaVision.

## Prerequisites

You should have received from your AWS administrator:

- ✅ Access portal URL (e.g., `https://your-org.awsapps.com/start`)
- ✅ Account ID (12-digit number)
- ✅ Role name (e.g., `PowerUserAccess`, `ReadOnly`)
- ✅ S3 bucket name
- ✅ Region (e.g., `us-east-1`)

## Step 1: Install AWS CLI v2

### Windows (PowerShell)

```powershell
# Download and install AWS CLI
msiexec.exe /i https://awscli.amazonaws.com/AWSCLIV2.msi

# Verify installation
aws --version
# Should show: aws-cli/2.x.x ...
```

### macOS

```bash
curl "https://awscli.amazonaws.com/AWSCLI2.pkg" -o "AWSCLIV2.pkg"
sudo installer -pkg AWSCLIV2.pkg -target /
```

### Linux

```bash
curl "https://awscli.amazonaws.com/awscli-exe-linux-x86_64.zip" -o "awscliv2.zip"
unzip awscliv2.zip
sudo ./aws/install
```

## Step 2: Configure AWS SSO Profile

Run the SSO configuration command:

```bash
aws configure sso
```

You'll be prompted for:

**SSO start URL:** `https://your-org.awsapps.com/start`

- This is your access portal link

**SSO Region:** `us-east-1` (or the region your admin provided)

- This is where IAM Identity Center is set up (NOT necessarily where your data is)

**SSO registration scopes:** Press Enter to use default (`sso:account:access`)

This will open a browser window:

1. Sign in with your credentials
2. Click "Allow" to authorize AWS CLI
3. Return to terminal

**Account ID:** (Select from list or enter the 12-digit number)

**Role name:** (Select from list, e.g., `PowerUserAccess`, `ReadOnly`)

**CLI default client Region:** `us-east-1` (or where your S3 bucket is located)

- This is where your data/bucket is

**CLI default output format:** `json`

**CLI profile name:** `marine-project` (or any name you choose)

- You'll use this name in your Python code

### Example Session

```bash
SSO start URL [None]: https://myorg.awsapps.com/start
SSO region [None]: us-east-1
[Browser opens, you authenticate]
There are 2 AWS accounts available to you.
> 123456789012 (production-account)
Using the account ID 123456789012
There are 2 roles available to you.
> PowerUserAccess
Using the role name "PowerUserAccess"
CLI default client Region [None]: us-east-1
CLI default output format [None]: json
CLI profile name [PowerUserAccess-123456789012]: marine-project

Successfully configured SSO profile 'marine-project'
```

## Step 3: Test Your Configuration

### Test AWS CLI Access

```bash
# List your configured profiles
aws configure list-profiles

# Test S3 access (use your profile name and bucket)
aws s3 ls s3://your-bucket-name/ --profile marine-project

# List specific folder
aws s3 ls s3://your-bucket-name/path/to/videos/ --profile marine-project
```

### Test Python/boto3 Access

Create a test script:

```python
"""Quick test of S3 access and OpenCV streaming."""

import boto3
import cv2

PROFILE = "profile-name"
BUCKET = "bucket-name"
PREFIX = "file-path-prefix" # Directory structure above the videos to stream

print(f"Testing S3 access...")
print(f"  Profile: {PROFILE}")
print(f"  Bucket: {BUCKET}")
print(f"  Prefix: {PREFIX}")
print()

try:
    session = boto3.Session(profile_name=PROFILE)
    s3 = session.client("s3")
    
    # Find first .ts file
    response = s3.list_objects_v2(
        Bucket=BUCKET,
        Prefix=PREFIX,
        MaxKeys=20
    )
    
    ts_files = [o["Key"] for o in response.get("Contents", []) if o["Key"].endswith(".ts")]
    
    if not ts_files:
        print("No .ts files found")
        exit(1)
    
    test_key = ts_files[0]
    print(f"Testing with: {test_key}")
    
    # Generate pre-signed URL
    url = s3.generate_presigned_url(
        "get_object",
        Params={"Bucket": BUCKET, "Key": test_key},
        ExpiresIn=3600
    )
    print(f"Generated pre-signed URL (length: {len(url)})")
    
    # Test OpenCV streaming
    print("\nTesting OpenCV streaming...")
    cap = cv2.VideoCapture(url)
    
    if not cap.isOpened():
        print("ERROR: OpenCV could not open the stream")
        exit(1)
    
    # Get metadata
    fps = cap.get(cv2.CAP_PROP_FPS)
    frame_count = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
    width = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
    height = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
    
    print(f"  FPS: {fps}")
    print(f"  Frame count: {frame_count}")
    print(f"  Resolution: {width}x{height}")
    
    # Try to read a few frames
    print("\nReading frames...")
    frames_read = 0
    for i in range(10):
        ret, frame = cap.read()
        if ret:
            frames_read += 1
        else:
            break
    
    cap.release()
    
    if frames_read > 0:
        print(f"SUCCESS! Read {frames_read} frames")
        print(f"  Frame shape: {frame.shape}")
    else:
        print("ERROR: Could not read any frames")
        
except Exception as e:
    print(f"ERROR: {e}")
    import traceback
    traceback.print_exc()

```
