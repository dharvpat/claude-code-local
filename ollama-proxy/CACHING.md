# Context Caching System

The Ollama proxy now includes an advanced context caching system that enables:
- **Extended conversations** far beyond model token limits
- **Persistent memory** across sessions
- **Intelligent context retrieval** when referencing past discussions
- **Automatic summarization** when context grows too large

## Features

### 1. Session-Based Caching
Every conversation is tracked as a session with a unique ID. Sessions persist to disk and survive proxy restarts.

### 2. Automatic Archival
When active context reaches the token limit (default: 8,000 tokens):
- Old messages are archived to disk
- A summary is generated using Ollama
- The summary replaces the full context in active memory
- Full details remain accessible on disk

### 3. Smart Context Retrieval
When you reference past conversations:
- "Remember that bug we fixed earlier?"
- "What did we change in server.py before?"

The system automatically:
- Detects the reference
- Searches archived contexts
- Loads relevant sections
- Injects them into the current request

### 4. Persistent Storage
- Sessions saved to `cache/sessions/`
- Archives saved to `cache/archives/`
- SQLite database for metadata and indexing
- Survives proxy restarts

## Configuration

Edit `.env` to configure caching:

```bash
# Enable/disable caching
CACHE_ENABLED=true

# Cache storage location
CACHE_DIR=./cache

# Trigger archival at this many tokens
MAX_ACTIVE_TOKENS=8000

# Maximum total tracked tokens (active + archived)
MAX_TOTAL_TOKENS=100000

# Summary compression ratio (0.2 = 20% of original)
SUMMARY_RATIO=0.2

# Auto-create sessions if no ID provided
AUTO_SESSION=true

# Enable smart context retrieval
SMART_RETRIEVAL=true

# Relevance threshold for retrieval (0.0-1.0)
RETRIEVAL_THRESHOLD=0.6

# Clean up sessions older than this many days
CACHE_CLEANUP_DAYS=30
```

## How It Works

### Normal Request (No Caching)
```
Claude Code → Request → Ollama → Response → Claude Code
```

### With Caching Enabled
```
Claude Code
    ↓
Request + Session ID
    ↓
Session Manager (load cached context)
    ↓
Context Manager (check if archival needed)
    ↓
Context Retrieval (load relevant archives if referenced)
    ↓
Merged Context → Ollama → Response
    ↓
Update Session Cache
    ↓
Trigger Summarization (if needed)
    ↓
Archive Old Context
    ↓
Response → Claude Code
```

## Usage

### Session Management

The proxy automatically creates and manages sessions. Each request can include a session ID header:

```bash
# Claude Code automatically manages this, but you can test manually:
curl -X POST http://localhost:8000/v1/messages \
  -H "Content-Type: application/json" \
  -H "X-Session-ID: my-session-123" \
  -d '{"messages": [{"role": "user", "content": "Hello"}]}'
```

### API Endpoints

#### List Sessions
```bash
GET /v1/sessions?limit=100
```

Returns all cached sessions.

#### Get Session Details
```bash
GET /v1/sessions/{session_id}
```

Returns session info including:
- Message count
- Token usage
- Archive count
- Context health status

#### Delete Session
```bash
DELETE /v1/sessions/{session_id}
```

Deletes session and all its archives.

#### Cache Statistics
```bash
GET /v1/cache/stats
```

Returns:
- Total sessions
- Total messages
- Token statistics
- Cache size on disk
- Configuration settings

## Cache CLI Tool

Manage the cache from the command line:

### List Sessions
```bash
python cache_cli.py list
```

### Show Session Details
```bash
python cache_cli.py show <session-id>
python cache_cli.py show <session-id> --messages  # Include message list
```

### Delete Session
```bash
python cache_cli.py delete <session-id>
python cache_cli.py delete <session-id> --force  # Skip confirmation
```

### View Archive
```bash
python cache_cli.py archive <archive-id>
python cache_cli.py archive <archive-id> --full  # Show full messages
```

### Cache Statistics
```bash
python cache_cli.py stats
```

### Clean Up Old Sessions
```bash
python cache_cli.py cleanup --days 30
python cache_cli.py cleanup --days 30 --force  # Skip confirmation
```

### Export Session
```bash
python cache_cli.py export <session-id>
python cache_cli.py export <session-id> --output backup.json
python cache_cli.py export <session-id> --include-archives
```

## Example Workflow

### 1. Long Coding Session

```
Request 1-10: Building a feature (2,000 tokens total)
→ All messages in active cache

Request 11-50: Extensive debugging (8,000 tokens total)
→ Still in active cache

Request 51: Context exceeds limit
→ Summarization triggered!
→ Messages 1-40 archived (6,000 tokens)
→ Summary generated (1,200 tokens)
→ Active cache now: Summary + Messages 41-51 (3,200 tokens)

Request 52-100: Continue working
→ Work proceeds with summarized context

Request 101: "Remember that bug in session initialization we fixed earlier?"
→ System detects reference to past context
→ Searches archives for "bug" + "session" + "initialization"
→ Finds relevant archive
→ Loads summary of that archive
→ Injects into request
→ Response includes context from archived discussion!
```

### 2. Multiple Sessions

```
Session A: Working on frontend
Session B: Working on backend
Session C: Writing tests

Each session maintains its own:
- Message history
- Archives
- Context window
```

## Storage Structure

```
cache/
├── sessions.db              # SQLite metadata
├── sessions/                # Active sessions
│   ├── sess_abc123.json
│   ├── sess_def456.json
│   └── ...
├── archives/                # Archived contexts
│   ├── sess_abc123_archive_20250123_150000_a1b2c3.json
│   ├── sess_abc123_archive_20250123_160000_d4e5f6.json
│   └── ...
└── index/                   # Content indexes (future use)
    └── content_index.json
```

## Performance Considerations

### Summarization Cost
- Uses local Ollama to generate summaries
- Takes 5-30 seconds depending on content size
- Happens asynchronously (doesn't block response)

### Disk Usage
- Active sessions: ~1-10 KB each
- Archives: ~5-50 KB each
- Database: ~100 KB to 10 MB
- Total: Grows slowly, plan for ~1 GB per 10,000 messages

### Memory Usage
- Active sessions kept in memory
- Archives loaded on-demand
- Typical usage: 10-100 MB for proxy

## Troubleshooting

### Archival Not Triggered
Check:
- `CACHE_ENABLED=true` in `.env`
- `MAX_ACTIVE_TOKENS` is set appropriately
- Session has enough messages

### Context Not Retrieved
Check:
- `SMART_RETRIEVAL=true` in `.env`
- Your query contains clear references
- Archives exist for the session

### Slow Summarization
- Normal for large contexts
- Reduce `MAX_ACTIVE_TOKENS` to trigger earlier
- Use a faster model for summarization

### Cache Growing Too Large
```bash
# Clean old sessions
python cache_cli.py cleanup --days 30

# Delete specific sessions
python cache_cli.py delete <session-id>

# Or manually delete cache directory
rm -rf cache/
```

## Advanced Usage

### Disable Caching
```bash
CACHE_ENABLED=false
```

Proxy works without caching (original behavior).

### Adjust Token Limits
```bash
# Conservative (more frequent archival)
MAX_ACTIVE_TOKENS=4000

# Aggressive (less frequent archival)
MAX_ACTIVE_TOKENS=16000
```

### Adjust Compression
```bash
# More compression (smaller summaries)
SUMMARY_RATIO=0.1  # 10% of original

# Less compression (detailed summaries)
SUMMARY_RATIO=0.4  # 40% of original
```

### Disable Smart Retrieval
```bash
SMART_RETRIEVAL=false
```

Archives still created, but not automatically loaded.

## Monitoring

### Check Active Sessions
```bash
python cache_cli.py list
```

### Monitor Specific Session
```bash
watch -n 5 "python cache_cli.py show sess_abc123"
```

### Cache Health
```bash
python cache_cli.py stats
```

Look for:
- Total tokens (should be under MAX_TOTAL_TOKENS)
- Archive ratio (higher = more compression)
- Cache size (disk usage)

## Best Practices

1. **Use meaningful session IDs** when testing manually
2. **Monitor cache size** periodically
3. **Clean up old sessions** regularly
4. **Backup important sessions** before cleanup
5. **Adjust token limits** based on your use case
6. **Test summarization quality** with your model

## Limitations

- **Summarization quality** depends on Ollama model capabilities
- **Context retrieval** uses simple keyword matching (could be enhanced with embeddings)
- **No automatic session expiry** (must clean up manually)
- **Single-threaded summarization** (one at a time)

## Future Enhancements

Potential improvements:
- [ ] Embedding-based semantic search
- [ ] Automatic session expiry
- [ ] Compression of archives
- [ ] Web UI for cache management
- [ ] Multi-threaded summarization
- [ ] Configurable retention policies
- [ ] Session merging and splitting

## Comparison: With vs. Without Caching

| Feature | Without Caching | With Caching |
|---------|----------------|--------------|
| Context Window | ~8K tokens | Effectively unlimited |
| Session Persistence | No | Yes (disk-based) |
| Restart Behavior | Context lost | Context restored |
| Long Conversations | Not supported | Fully supported |
| Past Reference | Not possible | Automatic retrieval |
| Memory Usage | Low | Medium |
| Disk Usage | None | Growing (manageable) |
| Performance | Fast | Slightly slower (summarization) |

## FAQ

**Q: Does caching slow down responses?**
A: First response in a session is slightly slower (loading cache). Summarization happens asynchronously and doesn't block.

**Q: How much disk space do I need?**
A: Plan for ~1 GB per 10,000 messages. Most users: <100 MB.

**Q: Can I use this with multiple Claude Code instances?**
A: Yes! Each instance gets its own session (if using AUTO_SESSION=true).

**Q: What happens if I delete the cache directory?**
A: All sessions and archives are lost. The proxy creates a new cache on next startup.

**Q: Can I backup the cache?**
A: Yes! Just backup the entire `cache/` directory, or export specific sessions with `cache_cli.py export`.

**Q: How does this compare to Anthropic's prompt caching?**
A: Similar concept, but this is disk-based and persistent. Anthropic's caching is cloud-based and temporary (~5 min TTL).

## Support

For issues or questions:
- Check logs in the proxy output
- Run `cache_cli.py stats` to check cache health
- Enable `DEBUG=true` in `.env` for detailed logs
- Review this documentation

Happy coding with unlimited context! 🚀
