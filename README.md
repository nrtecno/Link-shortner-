NR Hackz - Earning Link Bot
A Telegram bot that converts long URLs into monetized short links and grows your Telegram community automatically.

What This Bot Does
1. Link Monetization
Users send any long URL (YouTube, Google Drive, Instagram, etc.) to the bot. The bot converts it into a short link using your shortener API. Every time someone clicks that short link, you earn money in your shortener dashboard.

2. Mandatory Channel Subscription
To use the bot, users must first join your Telegram channel @nr_hackz. The bot automatically verifies channel membership using Telegram's getChatMember API.

If the user has not joined: The bot shows a "Join Channel" button and blocks access.
If the user has joined: The bot unlocks and allows link conversion.
This ensures every bot user becomes a channel member, helping you build a large audience for future promotions and affiliate marketing.

3. Smart Verification System
The bot includes an "I Joined" check button. After joining the channel, users can tap this button to instantly verify their membership and start using the bot without needing to type /start again.

4. Secure & Scalable
All sensitive keys (Bot Token and Shortener API Key) are stored securely in environment variables, not in the code, making it safe to host on a public GitHub repository and deploy on platforms like Render.

Workflow
User -> /start -> Joined @nr_hackz? -> No -> Show Join Button
-> Yes -> Ask for Link -> Convert to Earning Link -> User Shares & Earns

