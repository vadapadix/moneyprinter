# Test Video Upload Feature

This feature allows you to test video uploads to TikTok and YouTube before generating actual videos. This is useful for:

- Testing your upload configuration
- Verifying API credentials
- Debugging upload issues
- Checking video format compatibility

## Features

- Test upload to TikTok
- Test upload to YouTube  
- Test upload to both platforms simultaneously
- Real-time feedback on upload status
- Error reporting with detailed messages

## Prerequisites

Before using the test upload feature, ensure you have:

1. **Configured your TikTok API credentials** in `config.toml`:
   ```toml
   tiktok_upload_enabled = true
   tiktok_client_key = "your_client_key"
   tiktok_client_secret = "your_client_secret"
   tiktok_redirect_uri = "your_redirect_uri"
   tiktok_access_token = "your_access_token"
   ```

2. **Configured your YouTube API credentials** in `config.toml`:
   ```toml
   youtube_upload_enabled = true
   youtube_access_token = "your_access_token"
   youtube_client_id = "your_client_id"
   youtube_client_secret = "your_client_secret"
   ```

3. **Set up your public base URL** in `config.toml`:
   ```toml
   public_base_url = "https://your-domain.com"
   ```

## How to Use

### Web Interface

1. Open the MoneyPrinterTurbo web interface
2. Scroll to the "🧪 Test Video Upload" section
3. Upload an MP4 video file
4. Choose which platform(s) to test:
   - **Test TikTok Upload**: Tests upload to TikTok only
   - **Test YouTube Upload**: Tests upload to YouTube only
   - **Test Both Platforms**: Tests upload to both platforms
5. Click the test button
6. Review the results

### API Endpoint

You can also test uploads directly via the API:

```bash
# Test TikTok upload
curl -X POST "https://your-domain.com/api/v1/videos/test-upload?platform=tiktok" \
  -F "file=@/path/to/your/video.mp4"

# Test YouTube upload
curl -X POST "https://your-domain.com/api/v1/videos/test-upload?platform=youtube" \
  -F "file=@/path/to/your/video.mp4"

# Test both platforms
curl -X POST "https://your-domain.com/api/v1/videos/test-upload?platform=both" \
  -F "file=@/path/to/your/video.mp4"
```

## API Response Format

The test upload endpoint returns a JSON response with the following structure:

```json
{
  "request_id": "test-request-id",
  "platforms_tested": ["tiktok", "youtube"],
  "results": {
    "tiktok": {
      "success": true,
      "status": "processing",
      "error": null,
      "post_id": "1234567890"
    },
    "youtube": {
      "success": true,
      "status": "processing", 
      "error": null,
      "video_id": "ABCdefGHIjkl"
    }
  }
}
```

## Error Handling

Common errors and their solutions:

### TikTok Errors

- **"400 Client Error: Bad Request"**: Check your chunk size calculation or video format
- **"Invalid access token"**: Refresh your TikTok OAuth token
- **"Video file not found"**: Ensure the file path is correct

### YouTube Errors

- **"Invalid credentials"**: Check your YouTube API credentials
- **"Video file too large"**: YouTube has size limits (typically 256MB for Shorts)
- **"Unsupported format"**: Use MP4 format with H.264 video codec

### General Errors

- **"public_base_url not configured"**: Set the `public_base_url` in your config.toml
- **"Network error"**: Check your internet connection and firewall settings

## Troubleshooting

1. **Check API credentials**: Verify all your API keys and tokens are valid
2. **Test with small files**: Start with small video files (under 10MB)
3. **Check video format**: Ensure videos are in MP4 format with proper codecs
4. **Review logs**: Check the application logs for detailed error messages
5. **Test connectivity**: Ensure your server can reach TikTok/YouTube APIs

## Video Requirements

For best results, test videos should:

- Be in MP4 format
- Have H.264 video codec
- Have AAC audio codec
- Be under 100MB for testing (larger files may take longer)
- Have reasonable duration (under 5 minutes for Shorts)

## Security Notes

- Never share your API credentials publicly
- Use HTTPS for all API calls
- Regularly rotate your access tokens
- Monitor upload activity for suspicious behavior

## Support

If you encounter issues with the test upload feature:

1. Check the troubleshooting section above
2. Review your configuration files
3. Check the application logs
4. Open an issue on GitHub with:
   - Your configuration (without sensitive credentials)
   - Error messages
   - Video file details (size, format, duration)
   - Steps to reproduce the issue