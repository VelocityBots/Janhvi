# ==========================================================
# Copyright (c) 2026 Juno X Music
# All Rights Reserved.
# ==========================================================

import time
from typing import Dict

from pyrogram import filters, types

from Elevenyts import app

AFK_USERS: Dict[int, Dict[str, object]] = {}


@app.on_message(filters.command(["afk", "away"]))
async def afk_set(_, message: types.Message):
    if not message.from_user:
        return

    reason = " ".join(message.command[1:]).strip() if len(message.command) > 1 else ""
    AFK_USERS[message.from_user.id] = {"reason": reason, "time": time.time()}

    text = "😴 You are now AFK."
    if reason:
        text += f"\nReason: {reason}"

    await message.reply_text(text)


@app.on_message(filters.command(["afkoff", "back"]))
async def afk_clear(_, message: types.Message):
    if not message.from_user:
        return

    AFK_USERS.pop(message.from_user.id, None)
    await message.reply_text("✅ Welcome back! AFK mode is turned off.")


@app.on_message(filters.text & ~filters.command & ~filters.service, group=25)
async def afk_reply(_, message: types.Message):
    if not message.from_user:
        return

    user_id = message.from_user.id
    if user_id in AFK_USERS:
        AFK_USERS.pop(user_id, None)
        await message.reply_text("✅ Welcome back! AFK mode is turned off.")
        return

    if message.reply_to_message and message.reply_to_message.from_user:
        target_id = message.reply_to_message.from_user.id
        state = AFK_USERS.get(target_id)
        if state and target_id != user_id:
            reason = state.get("reason") or ""
            name = message.reply_to_message.from_user.first_name or "User"
            text = f"😴 {name} is currently AFK."
            if reason:
                text += f"\nReason: {reason}"
            await message.reply_text(text)
