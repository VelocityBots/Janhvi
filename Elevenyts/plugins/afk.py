# ==========================================================
# Copyright (c) 2026 Juno X Music
# All Rights Reserved.
# ==========================================================

import time
import re
from typing import Dict, List, Tuple
from collections import defaultdict

from pyrogram import filters, types

from Elevenyts import app

AFK_USERS: Dict[int, Dict[str, object]] = {}
AFK_MENTIONS: Dict[int, List[Dict[str, object]]] = defaultdict(list)
AFK_HEADER = "❖ ⎯꯭̽🦚⤹‌⋆‌‌‌‌𝅃͢𝐓𝛋֟͡‌‌‌𝐬 ≛ ͓͢‌‌𝛃 ͓𝛊֟͜͡ ͓𝛅 ͓𝝸̵̵𝐥 ͓𝛌 ͓𝐥 ⤹💙ˎ˗"

# How many seconds to wait before sending another AFK auto-reply to the same sender
DEFAULT_REPLY_COOLDOWN = 300  # 5 minutes


def _parse_duration_token(token: str) -> int:
    """Parse a simple duration token like '30s', '10m', '2h', '1d' into seconds.
    Returns seconds or 0 if unparsable.
    """
    match = re.match(r"^(\d+)([smhd])$", token.lower())
    if not match:
        return 0
    value, unit = match.groups()
    value = int(value)
    if unit == "s":
        return value
    if unit == "m":
        return value * 60
    if unit == "h":
        return value * 3600
    if unit == "d":
        return value * 86400
    return 0


def _format_duration(seconds: int) -> str:
    """Format seconds into a human-readable duration string."""
    seconds = max(seconds, 0)
    if seconds < 60:
        return f"{seconds} seconds"

    minutes = seconds // 60
    if minutes < 60:
        return f"{minutes} minute{'s' if minutes != 1 else ''}"

    hours = minutes // 60
    minutes = minutes % 60
    if minutes > 0:
        return f"{hours} hour{'s' if hours != 1 else ''} {minutes} minute{'s' if minutes != 1 else ''}"
    return f"{hours} hour{'s' if hours != 1 else ''}"


def _build_afk_message(name: str = "", reason: str = "", seconds: int = 0, dnd: bool = False) -> str:
    """Build an AFK notification message."""
    mode = "DND" if dnd else "AFK"
    text = f"{AFK_HEADER} is now {mode}!" if not name else f"{AFK_HEADER} {name} is now {mode}!"
    if reason:
        text += f"\n● Reason: {reason}"
    text += f"\n● Away for: {_format_duration(seconds)}"
    return text


def _build_back_message(seconds: int = 0, mentions: int = 0) -> str:
    """Build a welcome back message with activity stats."""
    text = f"❖ Welcome back {AFK_HEADER}!\n● Away for: {_format_duration(seconds)}"
    if mentions > 0:
        text += f"\n● You were mentioned {mentions} time{'s' if mentions != 1 else ''}"
    return text


def _get_user_identifier(user: types.User) -> Tuple[int, str, str]:
    """Extract user identification info."""
    return user.id, user.username or "", user.first_name or "User"


def _track_mention(user_id: int, mention_data: Dict[str, object]):
    """Track a mention for an AFK user."""
    AFK_MENTIONS[user_id].append(mention_data)
    # Keep only last 50 mentions
    if len(AFK_MENTIONS[user_id]) > 50:
        AFK_MENTIONS[user_id] = AFK_MENTIONS[user_id][-50:]


@app.on_message(filters.command(["afk", "away"]))
async def afk_set(_, message: types.Message):
    """Set user as AFK with optional reason."""
    if not message.from_user:
        return

    user_id = message.from_user.id
    tokens = message.command[1:]
    duration_seconds = 0
    reason = ""
    if tokens:
        # If first token is a duration like '30m' or '2h', parse it
        first = tokens[0]
        dur = _parse_duration_token(first)
        if dur > 0:
            duration_seconds = dur
            tokens = tokens[1:]

    if tokens:
        reason = " ".join(tokens).strip()

    AFK_USERS[user_id] = {
        "reason": reason,
        "time": time.time(),
        "until": time.time() + duration_seconds if duration_seconds > 0 else None,
        "username": message.from_user.username,
        "name": message.from_user.first_name or "User",
        "dnd": False,  # DND mode off by default
        "last_activity": time.time(),
        "mention_count": 0,
        "last_notified": {},  # per-sender cooldown tracking
        "reply_cooldown": DEFAULT_REPLY_COOLDOWN,
    }

    extra = f" (for {_format_duration(duration_seconds)})" if duration_seconds > 0 else ""
    await message.reply_text(_build_afk_message(reason=reason + extra if reason else reason, seconds=0, dnd=False))


@app.on_message(filters.command(["dnd", "donotdisturb"]))
async def dnd_set(_, message: types.Message):
    """Set user as DND (Do Not Disturb) - stricter AFK that doesn't auto-clear."""
    if not message.from_user:
        return

    user_id = message.from_user.id
    tokens = message.command[1:]
    duration_seconds = 0
    reason = ""
    if tokens:
        first = tokens[0]
        dur = _parse_duration_token(first)
        if dur > 0:
            duration_seconds = dur
            tokens = tokens[1:]

    if tokens:
        reason = " ".join(tokens).strip()

    AFK_USERS[user_id] = {
        "reason": reason,
        "time": time.time(),
        "until": time.time() + duration_seconds if duration_seconds > 0 else None,
        "username": message.from_user.username,
        "name": message.from_user.first_name or "User",
        "dnd": True,  # DND mode enabled
        "last_activity": time.time(),
        "mention_count": 0,
        "last_notified": {},
        "reply_cooldown": DEFAULT_REPLY_COOLDOWN,
    }

    extra = f" (for {_format_duration(duration_seconds)})" if duration_seconds > 0 else ""
    await message.reply_text(_build_afk_message(reason=reason + extra if reason else reason, seconds=0, dnd=True))


@app.on_message(filters.command(["afkoff", "back", "dndoff"]))
async def afk_clear(_, message: types.Message):
    """Remove AFK/DND status and show statistics."""
    if not message.from_user:
        return

    user_id = message.from_user.id
    state = AFK_USERS.get(user_id)
    
    if not state:
        await message.reply_text("❌ You are not AFK!")
        return
    
    elapsed = int(time.time() - state.get("time", time.time()))
    mention_count = len(AFK_MENTIONS.get(user_id, []))
    
    # Build welcome back message
    text = _build_back_message(seconds=elapsed, mentions=mention_count)
    
    # Add mention details if any
    if AFK_MENTIONS.get(user_id):
        text += "\n\n**📌 Mentions:**"
        for mention_data in AFK_MENTIONS[user_id][-10:]:  # Show last 10
            text += f"\n• {mention_data.get('sender', 'Unknown')} in {mention_data.get('chat', 'Unknown')}"
    
    # Clean up
    AFK_USERS.pop(user_id, None)
    AFK_MENTIONS.pop(user_id, None)
    
    await message.reply_text(text)


@app.on_message(filters.command(["afklist", "whoisafk"]))
async def afk_list(_, message: types.Message):
    """Show list of all AFK users."""
    if not AFK_USERS:
        await message.reply_text("❌ No users are AFK right now!")
        return
    
    text = "**📋 AFK Users:**\n"
    for user_id, state in AFK_USERS.items():
        name = state.get("name", "Unknown")
        reason = state.get("reason", "No reason")
        elapsed = int(time.time() - state.get("time", time.time()))
        dnd = "🔴 DND" if state.get("dnd") else "💛 AFK"
        mentions = len(AFK_MENTIONS.get(user_id, []))
        mention_str = f" ({mentions} mentions)" if mentions > 0 else ""
        until = state.get("until")
        until_str = ""
        if until:
            remaining = int(until - time.time())
            if remaining > 0:
                until_str = f" • Expires in: {_format_duration(remaining)}"
            else:
                until_str = " • (expired)"
        text += f"\n• {name} {dnd}{mention_str}\n  ⏱ Away: {_format_duration(elapsed)}{until_str}\n  📝 {reason}"
    
    await message.reply_text(text)


@app.on_message(filters.command(["afkstats"]))
async def afk_stats(_, message: types.Message):
    """Show personal AFK statistics."""
    if not message.from_user:
        return
    
    user_id = message.from_user.id
    state = AFK_USERS.get(user_id)
    
    if not state:
        await message.reply_text("❌ You are not AFK!")
        return
    
    elapsed = int(time.time() - state.get("time", time.time()))
    mention_count = len(AFK_MENTIONS.get(user_id, []))
    mode = "🔴 DND Mode" if state.get("dnd") else "💛 AFK Mode"
    until = state.get("until")
    until_str = ""
    if until:
        remaining = int(until - time.time())
        if remaining > 0:
            until_str = f"\n• Expires in: {_format_duration(remaining)}"
        else:
            until_str = "\n• Expires in: (expired)"

    text = f"""**📊 Your AFK Statistics:**

• Mode: {mode}
• Reason: {state.get('reason', 'None')}
• Away for: {_format_duration(elapsed)}{until_str}
• Mentions: {mention_count}
"""
    
    await message.reply_text(text)


@app.on_message(filters.text & ~filters.command & ~filters.service, group=25)
async def afk_reply(_, message: types.Message):
    """Handle AFK interactions and notifications."""
    if not message.from_user:
        return

    user_id = message.from_user.id
    
    # If sender is AFK and not in DND mode, auto-disable AFK
    if user_id in AFK_USERS:
        state = AFK_USERS[user_id]
        if not state.get("dnd"):  # Only auto-clear if not in DND mode
            elapsed = int(time.time() - state.get("time", time.time()))
            AFK_USERS.pop(user_id, None)
            AFK_MENTIONS.pop(user_id, None)
            await message.reply_text(_build_back_message(seconds=elapsed, mentions=0))
        return

    # Check if replying to an AFK user
    if message.reply_to_message and message.reply_to_message.from_user:
        target_id = message.reply_to_message.from_user.id
        state = AFK_USERS.get(target_id)
        if state and target_id != user_id:
            # Expire timed AFK
            now = time.time()
            until = state.get("until")
            if until and now > until:
                AFK_USERS.pop(target_id, None)
                AFK_MENTIONS.pop(target_id, None)
                return

            reason = state.get("reason") or ""
            name = state.get("name") or message.reply_to_message.from_user.first_name or "User"
            elapsed = int(now - state.get("time", now))
            dnd = state.get("dnd", False)

            # Per-sender cooldown to avoid spamming the same person
            sender_id = message.from_user.id
            last_notified = state.get("last_notified", {})
            last = last_notified.get(sender_id, 0)
            cooldown = state.get("reply_cooldown", DEFAULT_REPLY_COOLDOWN)

            # Track mention data regardless
            _track_mention(target_id, {
                "sender": message.from_user.first_name or "Unknown",
                "chat": message.chat.title or "Private",
                "time": now,
            })

            if now - last < cooldown:
                # Update last activity but do not reply again
                state["last_activity"] = now
                return

            # Send reply and update tracking
            state.setdefault("last_notified", {})[sender_id] = now
            state["mention_count"] = state.get("mention_count", 0) + 1
            await message.reply_text(_build_afk_message(name=name, reason=reason, seconds=elapsed, dnd=dnd))
            return

    # Check for mentions
    if message.entities:
        for entity in message.entities:
            if entity.type == "mention":
                mention = message.text[entity.offset : entity.offset + entity.length]
                username = mention.lstrip("@")
                for target_id, state in AFK_USERS.items():
                    if target_id != user_id and str(state.get("username") or "").lower() == username.lower():
                        now = time.time()
                        # Expire timed AFK
                        until = state.get("until")
                        if until and now > until:
                            AFK_USERS.pop(target_id, None)
                            AFK_MENTIONS.pop(target_id, None)
                            continue

                        reason = state.get("reason") or ""
                        name = state.get("name") or username
                        elapsed = int(now - state.get("time", now))
                        dnd = state.get("dnd", False)

                        sender_id = message.from_user.id
                        last_notified = state.get("last_notified", {})
                        last = last_notified.get(sender_id, 0)
                        cooldown = state.get("reply_cooldown", DEFAULT_REPLY_COOLDOWN)

                        # Track mention data regardless
                        _track_mention(target_id, {
                            "sender": message.from_user.first_name or "Unknown",
                            "chat": message.chat.title or "Private",
                            "time": now,
                        })

                        if now - last < cooldown:
                            state["last_activity"] = now
                            continue

                        state.setdefault("last_notified", {})[sender_id] = now
                        state["mention_count"] = state.get("mention_count", 0) + 1
                        await message.reply_text(_build_afk_message(name=name, reason=reason, seconds=elapsed, dnd=dnd))
                        return
