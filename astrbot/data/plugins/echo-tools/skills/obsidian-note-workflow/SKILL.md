---
name: obsidian-note-workflow
description: Safely search, organize, preview, and create linked notes in the user's Obsidian Vault. Use when the user asks to save a conversation as a note, create or organize a project/resource/course note, connect a new note to existing notes, or explicitly asks to consult diaries or archives before writing.
---

# Manage Obsidian Notes

Use the Obsidian tools only in the Vault owner's private QQ chat.

## Read and search

1. Use `obsidian_search` before reading or creating a note.
2. Use `standard` for projects, resources, and course notes.
3. Use `private_on_demand` only when the user explicitly asks to consult diaries or personal material.
4. Use `archive_on_demand` only when the user explicitly asks to search archives.
5. Pass paths returned by search or list tools into `obsidian_read`. Do not invent existing paths.
6. Read only the fragments needed for the current request.

## Create a linked note

1. Clarify the intended note only when title, destination, or content cannot be inferred safely.
2. Search for relevant existing notes and select only clearly related results.
3. Create only under `1. Projects`, `3. Resources`, or `5. Note`.
4. Call `obsidian_prepare_create` with:
   - a new `.md` relative path;
   - a concise title;
   - the organized Markdown body;
   - existing note paths returned by search as `links`;
   - minimal structured metadata when useful.
5. Show the user the destination, summary, and linked notes from the preview.
6. Stop after previewing. Never call `obsidian_commit_create` in the same user turn.
7. Commit only in a later turn whose current user message explicitly contains `确认创建`, `确认写入`, or `确认保存`.
8. Pass the exact pending `operation_id` to `obsidian_commit_create`.

## Add a backlink to an existing note

1. Read the existing note before proposing a modification.
2. Choose a concise `placement_hint` matching the most relevant existing section.
3. Call `obsidian_prepare_link` with the old note path and newly created note path.
4. Show the exact file, selected insertion section, and new Wikilink.
5. Stop and wait for a later explicit confirmation.
6. Call `obsidian_commit_link` only when the current message explicitly confirms the modification.
7. Cancel obsolete previews with `obsidian_cancel_link`.

If the user requests changes instead of confirming, prepare a new preview and treat the older operation as superseded.
Call `obsidian_cancel_create` before replacing a pending preview or when the user explicitly cancels it.

## Safety boundaries

- Never create, search, or read Obsidian content in a group chat or for another user.
- Never overwrite, delete, move, or rename a note.
- Never modify an old note merely to create a backlink. Add `[[existing note]]` links to the new note; Obsidian supplies backlinks automatically.
- Never access passwords, tokens, keys, recovery codes, hidden directories, attachments, or Obsidian configuration.
- Do not claim a note was created until `obsidian_commit_create` returns success.
