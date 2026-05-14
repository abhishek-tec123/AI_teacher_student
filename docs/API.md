# API Reference

Complete endpoint reference for the Student Learning API. All paths are prefixed with `/api/v1` unless otherwise noted.

For interactive docs with request/response schemas, run the server and visit: http://localhost:8000/docs

---

## Authentication

Most endpoints require a Bearer token:

```
Authorization: Bearer <access_token>
```

### Auth Endpoints

| Method | Path | Description |
|--------|------|-------------|
| POST | `/auth/login` | Authenticate and receive access/refresh tokens |
| POST | `/auth/refresh` | Refresh access token using refresh token |
| GET | `/auth/me` | Get current user info |
| POST | `/auth/change-password` | Change own password |
| POST | `/auth/create-student-with-auth` | Create a new student account with auth |
| POST | `/auth/create-admin` | Create a new admin account |
| POST | `/auth/admin/admin-reset-student-password/{student_id}` | Admin resets student password |

---

## Student

Student-facing endpoints for chat, bookmarks, sessions, documents, and conversation history.

### Profile & Subjects

| Method | Path | Description |
|--------|------|-------------|
| GET | `/student/{student_id}/subjects` | Get student's enrolled subjects |
| POST | `/student/create-student` | Create a new student profile |
| GET | `/student/student-list` | List all students |
| GET | `/student/{student_id}` | Get student profile |
| PUT | `/student/{student_id}` | Update student profile |
| DELETE | `/student/{student_id}` | Delete student |

### Chat & Feedback

| Method | Path | Description |
|--------|------|-------------|
| POST | `/student/agent-query` | Send a message to the AI tutor agent |
| GET | `/student/{student_id}/history/{subject}` | Get chat history for a subject |
| POST | `/student/feedback` | Submit feedback on a response |

### Bookmarks

| Method | Path | Description |
|--------|------|-------------|
| GET | `/student/{student_id}/recent-activity` | Get student's recent activity |
| POST | `/student/{student_id}/bookmarks` | Create a bookmark |
| GET | `/student/{student_id}/bookmarks` | Get student's bookmarks |
| PUT | `/student/bookmarks/{bookmark_id}` | Update a bookmark |
| DELETE | `/student/bookmarks/{bookmark_id}` | Delete a bookmark |

### Chat Sessions

| Method | Path | Description |
|--------|------|-------------|
| POST | `/student/chat-sessions` | Create a chat session |
| GET | `/student/{student_id}/chat-sessions` | List student's chat sessions |
| GET | `/student/{student_id}/chat-sessions/{chat_session_id}` | Get a chat session |
| PUT | `/student/{student_id}/chat-sessions/{chat_session_id}` | Update a chat session |
| DELETE | `/student/{student_id}/chat-sessions/{chat_session_id}` | Delete a chat session |
| GET | `/student/{student_id}/active-chat-session/{subject}` | Get active session for subject |
| POST | `/student/{student_id}/active-chat-session/{subject}` | Set active session for subject |
| DELETE | `/student/{student_id}/active-chat-session/{subject}` | Clear active session for subject |
| GET | `/student/{student_id}/chat-sessions/{chat_session_id}/history` | Get session-specific history |

### Documents

| Method | Path | Description |
|--------|------|-------------|
| GET | `/student/{student_id}/agents/{agent_id}/documents` | List agent documents |
| GET | `/student/{student_id}/agents/{agent_id}/documents/{document_id}` | Get document metadata |
| GET | `/student/{student_id}/agents/{agent_id}/documents/{document_id}/preview` | Preview document content |
| GET | `/student/{student_id}/shared-documents/{document_id}` | Get shared document metadata |
| GET | `/student/{student_id}/shared-documents/{document_id}/preview` | Preview shared document |
| POST | `/student/documents/agent-documents` | Get agent document IDs |
| GET | `/student/{student_id}/documents/storage-info` | Get storage usage info |

### Conversation History

| Method | Path | Description |
|--------|------|-------------|
| GET | `/student/conversation-history/{student_id}` | Full conversation history |
| GET | `/student/conversation-history/{student_id}/agent/{agent_id}` | History filtered by agent |
| GET | `/student/conversation-history/{student_id}/session/{session_id}` | History filtered by session |
| GET | `/student/conversation-summary/{student_id}` | Summarized conversation history |

---

## Admin

Admin endpoints for dashboard, global prompts, shared knowledge, and system management.

### Management

| Method | Path | Description |
|--------|------|-------------|
| GET | `/admin/list-admins` | List all admins |
| GET | `/admin/dashboard-counts` | Get dashboard statistics |
| GET | `/admin/global-rag-knowledge` | Legacy: list global RAG knowledge |
| GET | `/admin/global-prompts` | Legacy: list global prompts |

### Global Prompts

| Method | Path | Description |
|--------|------|-------------|
| POST | `/admin/prompts/update-base-prompt` | Update the base prompt template |
| GET | `/admin/prompts/current-base-prompt` | Get current base prompt |
| POST | `/admin/prompts/global-prompt/enable` | Enable global RAG |
| POST | `/admin/prompts/global-prompt/disable` | Disable global RAG |
| GET | `/admin/prompts/global-prompt/status` | Get global RAG status |
| GET | `/admin/prompts/global-prompts/` | List all global prompts |
| POST | `/admin/prompts/global-prompts/` | Create a new global prompt |
| GET | `/admin/prompts/global-prompts/{prompt_id}` | Get a global prompt |
| PUT | `/admin/prompts/global-prompts/{prompt_id}` | Update a global prompt |
| DELETE | `/admin/prompts/global-prompts/{prompt_id}` | Delete a global prompt |
| POST | `/admin/prompts/global-prompts/{prompt_id}/enable` | Enable a prompt |
| POST | `/admin/prompts/global-prompts/{prompt_id}/disable` | Disable a prompt |
| GET | `/admin/prompts/global-prompts/enabled/highest-priority` | Get highest priority enabled prompt |

### Shared Knowledge & System

| Method | Path | Description |
|--------|------|-------------|
| POST | `/admin/system/shared-knowledge/upload` | Upload a shared document |
| GET | `/admin/system/shared-knowledge` | List shared documents |
| DELETE | `/admin/system/shared-knowledge/{document_id}` | Delete a shared document |
| GET | `/admin/system/shared-knowledge/{document_id}` | Get shared document metadata |
| POST | `/admin/system/shared-knowledge/{document_id}/enable` | Enable document for agents |
| POST | `/admin/system/shared-knowledge/{document_id}/disable` | Disable document for agents |
| GET | `/admin/system/shared-knowledge/agent/{agent_id}` | Get agent-enabled documents |
| GET | `/admin/system/shared-knowledge/{document_id}/preview` | Preview shared document |
| GET | `/admin/system/global-rag-knowledge` | List global RAG knowledge |
| POST | `/admin/system/agents/{agent_id}/global-settings` | Update agent global settings |
| GET | `/admin/system/agents/{agent_id}/global-settings` | Get agent global settings |

---

## Vectors

Vector search and curriculum agent management.

| Method | Path | Description |
|--------|------|-------------|
| POST | `/vectors/search` | Semantic search across vectors |
| GET | `/vectors/status` | Vector store health status |
| GET | `/vectors/env_info` | Environment info |
| GET | `/vectors/db_status/{class_}/{subject}` | DB status for class/subject |
| GET | `/vectors/classes` | List available classes |
| GET | `/vectors/subjects` | List available subjects |
| GET | `/vectors/all_collections` | List all vector collections |
| GET | `/vectors/student/{student_id}/subjects` | Get student's vector subjects |
| POST | `/vectors/create_vectors` | Create vector embeddings for documents |
| GET | `/vectors/{subject_agent_id}` | Get vector agent details |
| PUT | `/vectors/{subject_agent_id}` | Update vector agent |
| DELETE | `/vectors/{subject_agent_id}` | Delete vector agent |
| POST | `/vectors/agent_of_class` | Create class-level agent |
| POST | `/vectors/{subject_agent_id}/shared-documents/enable` | Enable shared doc for agent |
| POST | `/vectors/{subject_agent_id}/shared-documents/disable` | Disable shared doc for agent |
| GET | `/vectors/{subject_agent_id}/shared-documents` | Get agent's shared documents |

---

## Performance

Agent performance metrics and monitoring.

| Method | Path | Description |
|--------|------|-------------|
| GET | `/performance/overview` | All agents overview |
| GET | `/performance/health-check` | Performance service health |
| GET | `/performance/metrics/summary` | Metrics summary |
| GET | `/performance/all-agents-performance` | Legacy: all agents performance |
| GET | `/performance/agent-performance/{agent_id}` | Legacy: single agent performance |
| GET | `/performance/agent/{agent_id}` | Get agent performance |
| GET | `/performance/agent/{agent_id}/trends` | Get agent performance trends |
| GET | `/performance/analytics/all-agents-performance` | Detailed all-agents performance |
| GET | `/performance/analytics/agent-performance/{agent_id}` | Detailed single agent performance |

---

## Activity Tracking

| Method | Path | Description |
|--------|------|-------------|
| GET | `/activity/recent` | Recent activities |
| GET | `/activity/stats` | Activity statistics |
| GET | `/activity/activity-types` | Available activity types |

---

## Core

| Method | Path | Description |
|--------|------|-------------|
| GET | `/core/health` | Service health check |

---

## Topics

| Method | Path | Description |
|--------|------|-------------|
| GET | `/topics/extract/{subject_agent_id}` | Extract topics from agent |
| GET | `/topics/extract/{subject_agent_id}/preview` | Preview topic extraction |

---

## TTS

| Method | Path | Description |
|--------|------|-------------|
| POST | `/tts-stream` | Stream text-to-speech audio |

---

## Response Codes

| Code | Meaning |
|------|---------|
| 200 | Success |
| 201 | Created |
| 400 | Bad Request |
| 401 | Unauthorized |
| 403 | Forbidden |
| 404 | Not Found |
| 422 | Validation Error |
| 500 | Internal Server Error |

## Rate Limits

| Role | Requests | Window |
|------|----------|--------|
| Admin | 120 | 60s |
| Teacher | 120 | 60s |
| Default | 300 | 60s |
