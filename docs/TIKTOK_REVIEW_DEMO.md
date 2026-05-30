# TikTok Review Demo Script

Use this checklist to record the demo video for TikTok Developer Portal review.
Keep the recording under 50 MB and use MP4 or MOV.

## App URLs

- Terms of Service: `https://shaky-pots-stop.loca.lt/terms`
- Privacy Policy: `https://shaky-pots-stop.loca.lt/privacy`
- Web/Desktop URL: `https://shaky-pots-stop.loca.lt/tiktok/connect`
- Redirect URI: `https://shaky-pots-stop.loca.lt/api/v1/tiktok/oauth/callback`
- Local web app shown in demo: `http://localhost:8501`

If your tunnel URL changes, update these URLs in TikTok Developer Portal and in
`config.toml` before recording.

## Products and Scopes to Keep

Keep only the products/scopes you can show in the video:

- Login Kit
- Content Posting API
- `user.info.basic`
- `video.publish`

Remove Display API, Share Kit, or other scopes if they are selected but not used
in the app. TikTok may delay review when selected products are not demonstrated.

## Demo Recording Flow

1. Open TikTok Developer Portal and show that the app is in Sandbox.
2. Open the configured Web/Desktop URL: `https://shaky-pots-stop.loca.lt/tiktok/connect`.
3. Click the TikTok connect link.
4. Show the TikTok authorization screen with requested scopes.
5. Authorize the app.
6. Show the callback success page: "TikTok connected".
7. Open `http://localhost:8501`.
8. Show the Social publishing panel:
   - TikTok connected.
   - TikTok creator nickname/username is displayed.
   - TikTok privacy options from creator info are displayed.
   - Platform is set to TikTok.
   - Privacy is set to private.
   - Auto-publish after video is enabled.
   - Explicit TikTok consent checkbox is checked before sending.
9. Show that the generated caption/metadata can be reviewed before posting.
10. Generate a short vertical video or upload a small MP4 in the test upload panel.
11. Click the TikTok test/upload action.
12. Show the upload result:
    - If the app is unaudited, the TikTok account must be private.
    - If TikTok returns `unaudited_client_can_only_post_to_private_accounts`, show that this is handled and explain the account must be private until approval.
13. Show the final generated video in the app and the local task result.

## Text for App Review Field

MoneyPrinterTurbo connects a creator's TikTok account with Login Kit and uses the
Content Posting API to send creator-approved short videos to TikTok. The app
generates a short video, creates editable title/caption/hashtag metadata, queries
TikTok creator information before rendering publishing controls, displays the
connected creator and available privacy options, and requires explicit user
consent before sending the video to TikTok. For unaudited clients and sandbox
testing, TikTok posts are sent with private/SELF_ONLY visibility and the connected
TikTok account is kept private as required by TikTok's guidelines.

The current version demonstrates Login Kit (`user.info.basic`) and Content
Posting API Direct Post (`video.publish`) in a sandbox environment. The user can
connect or refresh TikTok authorization, review the generated video and metadata,
choose platform/privacy, confirm the Direct Post action, and then upload the
video to TikTok.

## Review Safety Notes

- Do not show secrets, client secret, access token, or refresh token in the video.
- Use original or properly licensed demo content.
- Do not include watermarks, unrelated promotional logos, or misleading links in
  the video content.
- Keep the TikTok test account private until the Content Posting API audit is
  approved.
- Make sure the domain shown in the demo matches the Web/Desktop URL submitted
  in TikTok Developer Portal.
