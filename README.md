***

# 🤖 Jzcob's Custom Twitch Bot Wiki

Welcome to the documentation for Jzcob's custom Twitch bot. Built in Python using the `twitchAPI` library, this bot provides a seamless blend of automated moderation, community building, and fun chat interactions. 

> **🔒 Access Notice:** This bot is **private** and is not available for public invite. It is exclusively deployed and maintained for friendly channels and communities that Jacob is personally connected with. 

---

## 📑 Core Systems Overview

The bot is designed using a modular "Cog" system, meaning its features are separated into dedicated components that handle specific tasks.

### 1. The "Regulars" System (AdminCog)
To prevent malicious links while still allowing trusted community members to share content, the bot utilizes a "Regulars" system. 
* **Auto-Adding:** If a normal user sends a standard chat message (without a link), the bot automatically silently adds them to that channel's list of Regulars.
* **Protection:** If a brand-new user jumps into chat and immediately drops a link, they will bypass the auto-add feature and be caught by the Malicious Link filter.

### 2. Malicious Link Protection (MalLinkCog)
The bot actively scans messages for URLs to protect chat from spam and malicious links.
* **Twitch Links Allowed:** Links to `twitch.tv` or Twitch clips are automatically ignored and permitted.
* **Unauthorized Links:** If a user posts a non-Twitch link, the bot deletes the message and times the user out for 10 minutes (600 seconds). 
* **Alerts:** A detailed audit log (including the original message and username) is sent directly to a configured Discord webhook, pinging the moderator role so human staff can review for a potential ban.
* **Exemptions:** Broadcasters, Moderators, VIPs, Admins, and **Regulars** are immune to this filter.

### 3. Automated Blacklist (BlacklistCog)
A strict, zero-tolerance regex filter for severe profanity and slurs.
* **Action:** Messages containing blacklisted terms are instantly deleted.
* **Alerts:** Similar to the link filter, an audit log is sent to a Discord webhook for moderator review.
* **Exemptions:** Broadcasters, Moderators, VIPs, and Admins bypass this filter.

---

## 🛠️ Command Reference

Here is the complete list of commands available in the bot. 

### Moderation & Admin Commands
*These commands are restricted to the Broadcaster and Moderators.*

| Command | Usage | Description |
| :--- | :--- | :--- |
| `!addregular` | `!addregular @username` | Manually whitelists a user, allowing them to bypass the link filter. |
| `!removeregular`| `!removeregular @username`| Removes a user from the regulars whitelist. |

### General Community Commands
*These commands are available to everyone.*

| Command | Description | Notes |
| :--- | :--- | :--- |
| `!hello` | Greets the user. | |
| `!lurk` | Announces that the user is stepping away but continuing to support the stream. | |
| `!discord` | Drops the channel's configured Discord invite link. | If used by a Mod/Broadcaster, the bot will also **Pin** the message as a chat announcement. |
| `!youtube` | Drops the channel's configured YouTube link. | |
| `!tiktok` | Drops the channel's configured Tiktok link. | |
| `!hockeybot` | Provides a link to Jzcob's Discord Hockey bot. | **Channel Specific:** This command only works when executed in the `jzcob` Twitch channel. |

### Fun Commands
*These commands are available to everyone for chat engagement.*

| Command | Usage | Description |
| :--- | :--- | :--- |
| `!8ball` | `!8ball <question>` | Asks the magic 8-ball a question and receives a randomized positive, neutral, or negative response. |
| `!bald` | `!bald` | Playfully declares that the user is bald. |
| `!diddy` | `!diddy @username` | Tags a specific user with a joke message. |

---

## ⚙️ Technical Configuration (For Channel Owners)

Because the bot handles multiple channels simultaneously, it relies on a local `config.json` file managed by the developer. If a channel owner needs to update their links or webhooks, they simply need to provide the new information to Jake.

**Configurable Channel Elements Include:**
* Discord Invite Link
* YouTube Channel Link
* Discord Webhook URL (for general audit logs)
* Discord Webhook URL (for Mod/Timeout alerts)
* Discord Mod Role ID (for automated pinging)
