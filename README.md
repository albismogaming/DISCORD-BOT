# DISCORD-BOT

**Updated Discord Bot w/ Functionality**
Add some new features to the discord bot 
1. Created a cogs folder that will store the bot commands.
2. Created a utils folder for wrapper functions and other utilities items to help with the commands.

Users will have to create a data file that has TOKEN and CHANNEL_ID variables. 

**House Keeping Items**
1. Visit Discord Developer Portal Website
2. Create *New Application*
3. Grab **TOKEN**
  - Left hand side find and click *"BOT"*
  - Under **TOKEN** click *Reset Token* and copy TOKEN
4. Same page scroll down and toggle *MESSAGE CONTENT INTENT*
5. Authenticate BOT with OAuth2
  - Left hand side find and click *"OAuth2"*
  - Scroll down and find *"OAuth2 URL Generator"*
  - Find *"bot"* and toggle on
  - Under **BOT PERMISSIONS** toggle the following:
  ["Manage Messages", "Manage Channels", "Manage Events", "View Channels", "Slash Commands"]
6. Copy Generated URL and Invite Bot to Discord Channel
7. Sit back, relax and run the script! 😎
