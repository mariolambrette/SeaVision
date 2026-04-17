# S3 & AWS Integration

The GUI supports validating detections from videos stored in S3 buckets. Videos
are downloaded to a local cache before validation begins.

---

## How it works

1. When you open a session whose CSV references S3 URIs (`s3://bucket/key`),
   the GUI detects this automatically and skips the video directory prompt
2. You are asked to select an **AWS profile** from your `~/.aws/config`
3. Videos are downloaded to a local cache directory (`~/.seavision/cache/`)
   with a progress dialog
4. Once cached, videos are used identically to local files

Subsequent opens of the same session use the cached files without
re-downloading.

---

## Prerequisites

- `boto3` installed (`pip install boto3`)
- AWS credentials configured via `~/.aws/config` and `~/.aws/credentials`
- For SSO-based authentication: run `aws sso login --profile <profile>` before
  launching the GUI

## AWS profile selection

When S3 access is needed, the GUI reads available profiles from
`~/.aws/config` and presents a selection dialog. The `default` profile (if it
exists) is listed first.

The selected profile is saved in the session file so it is remembered on
reload.

## S3 browser

For opening sessions or videos directly from S3 (without a local CSV), use
**File → Open from S3**. This opens a bucket browser where you can navigate
prefixes, select a CSV and video directory, and start a session.

## Cache management

- Cache location: `~/.seavision/cache/` (configurable via Tools menu)
- **Tools → Clear Video Cache** shows the current cache size and lets you
  delete all cached files
- Cache hits are logged — you can verify with `seavision-gui --log-level DEBUG`

## Troubleshooting S3 access

| Problem | Solution |
|---------|----------|
| "No AWS profiles found" | Create `~/.aws/config` with at least one profile |
| Credential expiry errors | Run `aws sso login --profile <name>` |
| Access denied | Check the profile has `s3:GetObject` permission on the bucket |
| Slow downloads | Videos are downloaded sequentially; large sessions may take time |
 