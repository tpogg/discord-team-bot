## Task: Polish Discord Team Bot

The bot is live on Render (Python background worker). Improve it:

1. Clean up bot.py code formatting - it's compressed/minified right now, make it readable with proper spacing and comments
2. Add rich embeds with consistent branding (pick a color scheme, add footer/thumbnail to all embeds)
3. Make the /setup_server command also set channel permissions (management channels locked to Admin/Manager, announcement channels read-only for members)
4. Add a /help command that lists all available commands with descriptions
5. Add error handling and logging
6. Commit and push to origin main (Render auto-deploys)

Context: Business/team Discord server. Bot has slash commands: /setup_server, /ticket, /poll, /meeting, /department, /announce. Daily standup reminders. Auto-onboarding on member join.
