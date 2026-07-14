# ==========================================================
# Copyright (c) 2026 ArtistBots
# All Rights Reserved.
#
# Project      : Elevenyts Music Bot
# Powered By   : Artist
# Type         : Premium AFK Module for Pyrogram 2.x
#
# Bot          : @ArtistApibot
# Channel      : https://t.me/artistbots
# GitHub       : https://github.com/elevenyts
#
# Unauthorized copying, modification, or redistribution
# of this source code without permission is prohibited.
# ==========================================================
import asyncio
import time
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from pyrogram import errors, filters
from pyrogram.enums import MessageEntityType
from pyrogram.types import Message

from Elevenyts import app, db, logger

AFK_COLLECTION = "afk"
NOTIFICATION_COLLECTION = "afk_notifications"


async def _get_collection(name: str):
    try:
        return db.db[name]
    except Exception as exc:
        logger.exception("Failed to access Mongo collection %s: %s", name, exc)
        return None


async def _normalize_afk_document(doc: Optional[Dict[str, Any]]) -> Optional[Dict[str, Any]]:
    if not doc:
        return None
    doc = dict(doc)
    doc.setdefault("reason", "No reason provided")
    doc.setdefault("time", int(time.time()))
    doc.setdefault("media_type", "text")
    doc.setdefault("media_file_id", "")
    doc.setdefault("caption", "")
    doc.setdefault("is_global", False)
    doc.setdefault("chat_id", None)
    doc.setdefault("user_id", None)
    doc.setdefault("username", None)
    return doc


async def _save_afk_entry(user_id: int, chat_id: int, reason: str, is_global: bool, media_payload: Dict[str, Any], username: Optional[str] = None) -> bool:
    try:
        collection = await _get_collection(AFK_COLLECTION)
        if not collection:
            return False
        payload = {
            "user_id": user_id,
            "chat_id": chat_id if not is_global else None,
            "is_global": is_global,
            "reason": reason or "No reason provided",
            "time": int(time.time()),
            "media_type": media_payload.get("media_type", "text"),
            "media_file_id": media_payload.get("media_file_id", ""),
            "caption": media_payload.get("caption", ""),
            "username": username or "",
        }
        await collection.update_one(
            {"user_id": user_id, "is_global": is_global, "chat_id": None if is_global else chat_id},
            {"$set": payload},
            upsert=True,
        )
        return True
    except Exception as exc:
        logger.exception("Failed to save AFK entry: %s", exc)
        return False


async def _remove_afk_entry(user_id: int, chat_id: int, is_global: bool) -> bool:
    try:
        collection = await _get_collection(AFK_COLLECTION)
        if not collection:
            return False
        query = {"user_id": user_id}
        if is_global:
            query["is_global"] = True
        else:
            query["chat_id"] = chat_id
        await collection.delete_one(query)
        return True
    except Exception as exc:
        logger.exception("Failed to remove AFK entry: %s", exc)
        return False


async def _get_afk_entry(user_id: int, chat_id: int) -> Optional[Dict[str, Any]]:
    try:
        collection = await _get_collection(AFK_COLLECTION)
        if not collection:
            return None
        local_doc = await collection.find_one({"user_id": user_id, "is_global": False, "chat_id": chat_id})
        if local_doc:
            return await _normalize_afk_document(local_doc)
        global_doc = await collection.find_one({"user_id": user_id, "is_global": True})
        return await _normalize_afk_document(global_doc)
    except Exception as exc:
        logger.exception("Failed to fetch AFK entry: %s", exc)
        return None


async def _list_afk_entries(chat_id: int) -> List[Dict[str, Any]]:
    try:
        collection = await _get_collection(AFK_COLLECTION)
        if not collection:
            return []
        docs = []
        async for doc in collection.find({"$or": [{"is_global": True}, {"chat_id": chat_id}]}).sort("time", 1):
            docs.append(await _normalize_afk_document(doc))
        return [doc for doc in docs if doc]
    except Exception as exc:
        logger.exception("Failed to list AFK entries: %s", exc)
        return []


async def _store_notification_cache(sender_id: int, afk_user_id: int, chat_id: int, message_id: int) -> None:
    try:
        collection = await _get_collection(NOTIFICATION_COLLECTION)
        if not collection:
            return
        payload = {
            "sender_id": sender_id,
            "afk_user_id": afk_user_id,
            "chat_id": chat_id,
            "message_id": message_id,
            "expires_at": int(time.time()) + 300,
        }
        await collection.replace_one(
            {"sender_id": sender_id, "afk_user_id": afk_user_id, "chat_id": chat_id, "message_id": message_id},
            payload,
            upsert=True,
        )
    except Exception as exc:
        logger.exception("Failed to cache AFK notification: %s", exc)


async def _is_duplicate_notification(sender_id: int, afk_user_id: int, chat_id: int, message_id: int) -> bool:
    try:
        collection = await _get_collection(NOTIFICATION_COLLECTION)
        if not collection:
            return False
        doc = await collection.find_one({
            "sender_id": sender_id,
            "afk_user_id": afk_user_id,
            "chat_id": chat_id,
            "message_id": message_id,
            "expires_at": {"$gt": int(time.time())},
        })
        return bool(doc)
    except Exception as exc:
        logger.exception("Failed to detect duplicate AFK notification: %s", exc)
        return False


def _format_age(timestamp: int) -> str:
    try:
        age = max(1, int(time.time()) - int(timestamp))
    except Exception:
        age = 1
    seconds = age % 60
    minutes = (age // 60) % 60
    hours = (age // 3600) % 24
    days = age // 86400
    parts = []
    if days:
        parts.append(f"{days}d")
    if hours:
        parts.append(f"{hours}h")
    if minutes:
        parts.append(f"{minutes}m")
    if seconds or not parts:
        parts.append(f"{seconds}s")
    return " ".join(parts)


def _format_since(timestamp: int) -> str:
    try:
        dt = datetime.fromtimestamp(int(timestamp), tz=timezone.utc)
        return dt.strftime("%d %b %Y %H:%M:%S UTC")
    except Exception:
        return "Unknown"


def _build_afk_card(user_name: str, reason: str, away_label: str, since_timestamp: int, welcome: bool = False) -> str:
    divider = "━━━━━━━━━━━━━━━━━━━━━━"
    if not welcome:
        return (
            f"{divider}\n"
            f"💤 <b>AFK MODE</b>\n\n"
            f"👤 <b>User:</b> {user_name}\n"
            f"⏱ <b>Away:</b> {away_label}\n"
            f"📅 <b>Since:</b> {_format_since(int(since_timestamp))}\n"
            f"📝 <b>Reason:</b> {reason}\n"
            f"{divider}"
        )
    return (
        f"{divider}\n"
        f"✨ <b>Welcome Back</b>\n\n"
        f"👤 <b>User:</b> {user_name}\n"
        f"⏱ <b>AFK Duration:</b> {away_label}\n"
        f"📝 <b>Reason:</b> {reason}\n"
        f"{divider}"
    )


async def _safe_send(send_func, *args: Any, **kwargs: Any) -> Optional[Message]:
    attempt = 0
    while True:
        try:
            return await send_func(*args, **kwargs)
        except errors.FloodWait as e:
            attempt += 1
            if attempt >= 5:
                logger.warning("FloodWait exceeded retries for AFK send: %s", e)
                return None
            logger.warning("FloodWait in AFK module, sleeping for %ss", e.value + 1)
            await asyncio.sleep(e.value + 1)
        except Exception as exc:
            logger.exception("Telegram send failed in AFK module: %s", exc)
            return None


async def _send_text_message(chat_id: int, text: str, reply_to: int, parse_mode: str = "html") -> Optional[Message]:
    return await _safe_send(
        app.send_message,
        chat_id=chat_id,
        text=text,
        parse_mode=parse_mode,
        disable_web_page_preview=True,
        reply_to_message_id=reply_to,
    )


def _extract_media_data(message: Message) -> Dict[str, Any]:
    if message.photo:
        return {"media_type": "photo", "media_file_id": message.photo.file_id, "caption": message.caption or ""}
    if message.video:
        return {"media_type": "video", "media_file_id": message.video.file_id, "caption": message.caption or ""}
    if message.animation:
        return {"media_type": "animation", "media_file_id": message.animation.file_id, "caption": message.caption or ""}
    if message.audio:
        return {"media_type": "audio", "media_file_id": message.audio.file_id, "caption": message.caption or ""}
    if message.voice:
        return {"media_type": "voice", "media_file_id": message.voice.file_id, "caption": message.caption or ""}
    if message.document and not (getattr(message.document, "mime_type", "") == "image/webp") and not getattr(message, "sticker", None):
        return {"media_type": "document", "media_file_id": message.document.file_id, "caption": message.caption or ""}
    if message.text or message.caption:
        return {"media_type": "text", "media_file_id": "", "caption": message.text or message.caption or ""}
    return {"media_type": "text", "media_file_id": "", "caption": ""}


async def _send_afk_media(chat_id: int, reply_to: int, media_payload: Dict[str, Any], caption_override: Optional[str] = None) -> Optional[Message]:
    media_type = media_payload.get("media_type", "text")
    media_file_id = media_payload.get("media_file_id", "")
    caption = caption_override if caption_override is not None else media_payload.get("caption", "")

    if media_type == "photo":
        return await _safe_send(
            app.send_photo,
            chat_id=chat_id,
            photo=media_file_id,
            caption=caption,
            reply_to_message_id=reply_to,
        )
    if media_type == "video":
        return await _safe_send(
            app.send_video,
            chat_id=chat_id,
            video=media_file_id,
            caption=caption,
            reply_to_message_id=reply_to,
        )
    if media_type == "animation":
        return await _safe_send(
            app.send_animation,
            chat_id=chat_id,
            animation=media_file_id,
            caption=caption,
            reply_to_message_id=reply_to,
        )
    if media_type == "audio":
        return await _safe_send(
            app.send_audio,
            chat_id=chat_id,
            audio=media_file_id,
            caption=caption,
            reply_to_message_id=reply_to,
        )
    if media_type == "voice":
        return await _safe_send(
            app.send_voice,
            chat_id=chat_id,
            voice=media_file_id,
            caption=caption,
            reply_to_message_id=reply_to,
        )
    if media_type == "document":
        return await _safe_send(
            app.send_document,
            chat_id=chat_id,
            document=media_file_id,
            caption=caption,
            reply_to_message_id=reply_to,
        )
    return await _send_text_message(chat_id, caption or "", reply_to)


async def _send_welcome_back(chat_id: int, reply_to: int, user: Any, reason: str, duration: str) -> None:
    try:
        display_name = user.first_name if user and getattr(user, "first_name", None) else "User"
        card = _build_afk_card(display_name, reason, duration, welcome=True)
        await _send_text_message(chat_id, card, reply_to)
    except Exception as exc:
        logger.exception("Failed to send welcome back card: %s", exc)


async def _resolve_mention_targets(message: Message) -> List[int]:
    targets: List[int] = []
    if not message or not message.from_user:
        return targets

    try:
        if message.reply_to_message and message.reply_to_message.from_user:
            targets.append(message.reply_to_message.from_user.id)
    except Exception:
        pass

    try:
        if message.entities:
            for entity in message.entities:
                if entity.type == MessageEntityType.TEXT_MENTION and entity.user:
                    targets.append(entity.user.id)
                if entity.type == MessageEntityType.MENTION:
                    username = message.text[entity.offset + 1:entity.offset + entity.length] if message.text else ""
                    if username:
                        user_doc = await _find_user_by_username(username)
                        if user_doc:
                            targets.append(user_doc)
    except Exception:
        pass

    try:
        if message.caption_entities:
            for entity in message.caption_entities:
                if entity.type == MessageEntityType.TEXT_MENTION and entity.user:
                    targets.append(entity.user.id)
                if entity.type == MessageEntityType.MENTION:
                    username = message.caption[entity.offset + 1:entity.offset + entity.length] if message.caption else ""
                    if username:
                        user_doc = await _find_user_by_username(username)
                        if user_doc:
                            targets.append(user_doc)
    except Exception:
        pass
    return list(dict.fromkeys(targets))


async def _find_user_by_username(username: str) -> Optional[int]:
    try:
        collection = await _get_collection(AFK_COLLECTION)
        if not collection:
            return None
        doc = await collection.find_one({"username": username})
        if doc:
            return int(doc.get("user_id", 0))
    except Exception:
        pass
    return None


async def _handle_afk_notification(message: Message) -> None:
    if not message or not message.from_user or message.from_user.is_self:
        return

    try:
        targets = await _resolve_mention_targets(message)
        if not targets:
            return
        for target_id in targets:
            afk_entry = await _get_afk_entry(target_id, message.chat.id)
            if not afk_entry:
                continue
            if target_id == message.from_user.id:
                continue
            if await _is_duplicate_notification(message.from_user.id, target_id, message.chat.id, message.id):
                continue

            await _store_notification_cache(message.from_user.id, target_id, message.chat.id, message.id)
            media_payload = {
                "media_type": afk_entry.get("media_type", "text"),
                "media_file_id": afk_entry.get("media_file_id", ""),
                "caption": afk_entry.get("caption", ""),
            }
            reason = afk_entry.get("reason") or "No reason provided"
            since_timestamp = int(afk_entry.get("time", int(time.time())))
            since_label = _format_age(since_timestamp)
            user_name = message.reply_to_message.from_user.first_name if message.reply_to_message and message.reply_to_message.from_user else (message.from_user.first_name if message.from_user else "User")
            card_text = (
                f"{_build_afk_card(user_name, reason, since_label, since_timestamp, welcome=False)}\n"
                f"<i>Triggered by:</i> {message.from_user.first_name}"
            )
            if media_payload.get("media_type", "text") == "text":
                await _send_text_message(message.chat.id, card_text, message.id)
            else:
                await _send_afk_media(message.chat.id, message.id, media_payload, caption_override=card_text)
    except Exception as exc:
        logger.exception("AFK notification failed: %s", exc)


async def _handle_afk_command(message: Message, is_global: bool, remove: bool = False) -> None:
    if not message.from_user:
        return

    try:
        if remove:
            existing = await _get_afk_entry(message.from_user.id, message.chat.id)
            removed = await _remove_afk_entry(message.from_user.id, message.chat.id, is_global)
            if removed:
                start_time = int(existing.get("time", int(time.time())) if existing else int(time.time()))
                duration = _format_age(int(time.time()) - start_time)
                await _send_text_message(message.chat.id, f"<b>✅ AFK removed.</b>\n\n⏱ <b>Duration:</b> {duration}", message.id)
            else:
                await _send_text_message(message.chat.id, "<b>⚠️ You were not marked AFK.</b>", message.id)
            return

        reason = "No reason provided"
        text = message.text or message.caption or ""
        command = message.command[0].lower() if message.command else "afk"
        if len(message.command) > 1:
            reason = " ".join(message.command[1:])
        elif message.reply_to_message:
            reason = message.reply_to_message.text or message.reply_to_message.caption or "No reason provided"
        elif text:
            reason = text

        media_payload = _extract_media_data(message)
        if message.reply_to_message:
            reply_media = _extract_media_data(message.reply_to_message)
            if reply_media.get("media_type") != "text" or message.reply_to_message.text:
                media_payload = reply_media
            elif media_payload.get("media_type") == "text":
                media_payload = {"media_type": "text", "media_file_id": "", "caption": ""}

        saved = await _save_afk_entry(message.from_user.id, message.chat.id, reason, is_global, media_payload, username=message.from_user.username)
        if saved:
            user_name = message.from_user.first_name or message.from_user.username or "User"
            card = _build_afk_card(user_name, reason, "Now", int(time.time()), welcome=False)
            await _send_text_message(message.chat.id, card, message.id)
        else:
            await _send_text_message(message.chat.id, "<b>⚠️ AFK mode could not be activated.</b>", message.id)
    except Exception as exc:
        logger.exception("AFK command failed: %s", exc)
        await _send_text_message(message.chat.id, "<b>⚠️ Something went wrong while handling AFK.</b>", message.id)


async def _handle_afk_list(message: Message) -> None:
    try:
        entries = await _list_afk_entries(message.chat.id)
        if not entries:
            await _send_text_message(message.chat.id, "<b>📭 No AFK users right now.</b>", message.id)
            return
        lines = ["<b>🛌 AFK List</b>", ""]
        for entry in entries[:20]:
            user_id = entry.get("user_id", 0)
            user_name = f"User #{user_id}" if not user_id else f"User #{user_id}"
            scope = "Global" if entry.get("is_global") else "Local"
            duration = _format_age(int(entry.get("time", int(time.time()))))
            lines.append(f"• {user_name} | {scope} | {duration} | {entry.get('reason', 'No reason provided')}")
        await _send_text_message(message.chat.id, "\n".join(lines), message.id)
    except Exception as exc:
        logger.exception("AFK list failed: %s", exc)


async def _handle_regular_message(message: Message) -> None:
    if not message.from_user or message.from_user.is_self:
        return
    if message.command:
        return
    try:
        afk_entry = await _get_afk_entry(message.from_user.id, message.chat.id)
        if not afk_entry:
            await _handle_afk_notification(message)
            return
        await _remove_afk_entry(message.from_user.id, message.chat.id, bool(afk_entry.get("is_global", False)))
        duration_label = _format_age(int(afk_entry.get("time", int(time.time()))))
        await _send_welcome_back(message.chat.id, message.id, message.from_user, afk_entry.get("reason", "No reason provided"), duration_label)
        if afk_entry.get("media_type", "text") != "text":
            await _send_afk_media(message.chat.id, message.id, {
                "media_type": afk_entry.get("media_type", "text"),
                "media_file_id": afk_entry.get("media_file_id", ""),
                "caption": afk_entry.get("caption", ""),
            })
    except Exception as exc:
        logger.exception("Welcome back handling failed: %s", exc)


@app.on_message(filters.command(["afk"], prefixes="/.!"))
async def afk_handler(client, message: Message):
    await _handle_afk_command(message, is_global=False, remove=False)


@app.on_message(filters.command(["gafk"], prefixes="/.!"))
async def gafk_handler(client, message: Message):
    await _handle_afk_command(message, is_global=True, remove=False)


@app.on_message(filters.command(["unafk"], prefixes="/.!"))
async def unafk_handler(client, message: Message):
    await _handle_afk_command(message, is_global=False, remove=True)


@app.on_message(filters.command(["ungafk"], prefixes="/.!"))
async def ungafk_handler(client, message: Message):
    await _handle_afk_command(message, is_global=True, remove=True)


@app.on_message(filters.command(["afklist"], prefixes="/.!"))
async def afklist_handler(client, message: Message):
    await _handle_afk_list(message)


@app.on_message(filters.text | filters.photo | filters.video | filters.animation | filters.audio | filters.voice | filters.document)
async def afk_listener(client, message: Message):
    if message.command:
        return
    await _handle_regular_message(message)


__all__ = ["afk_handler", "gafk_handler", "unafk_handler", "ungafk_handler", "afklist_handler", "afk_listener"]
