#!/usr/bin/env python3
"""
Cache Management CLI
Command-line tool for managing the context cache
"""

import sys
import argparse
import json
from pathlib import Path
from dotenv import load_dotenv
import os

# Load environment
load_dotenv()

from cache_store import CacheStore
from session_manager import SessionManager

CACHE_DIR = os.getenv("CACHE_DIR", "./cache")


def list_sessions(args):
    """List all sessions"""
    cache_store = CacheStore(CACHE_DIR)
    sessions = cache_store.list_sessions(limit=args.limit)

    if not sessions:
        print("No sessions found")
        return

    print(f"\n{'Session ID':<25} {'Created':<20} {'Messages':<10} {'Tokens':<10} {'Archives':<10}")
    print("=" * 85)

    for session in sessions:
        print(f"{session['session_id']:<25} "
              f"{session['created_at'][:19]:<20} "
              f"{session.get('total_messages', 0):<10} "
              f"{session.get('total_tokens', 0):<10} "
              f"{session.get('archive_count', 0):<10}")

    print(f"\nTotal: {len(sessions)} sessions")


def show_session(args):
    """Show details for a specific session"""
    cache_store = CacheStore(CACHE_DIR)

    # Get stats
    stats = cache_store.get_session_stats(args.session_id)

    if not stats:
        print(f"Session not found: {args.session_id}")
        return

    # Load full session
    session_data = cache_store.load_session(args.session_id)

    print(f"\nSession: {args.session_id}")
    print("=" * 60)
    print(f"Created: {stats['created_at']}")
    print(f"Last Accessed: {stats['last_accessed']}")
    print(f"Total Messages: {stats['total_messages']}")
    print(f"Active Tokens: {stats['active_tokens']}")
    print(f"Total Tokens: {stats['total_tokens']}")
    print(f"Archives: {stats['archive_count']}")

    if session_data:
        print(f"\nMetadata:")
        metadata = session_data.get('metadata', {})
        for key, value in metadata.items():
            print(f"  {key}: {value}")

        if args.messages:
            print(f"\nMessages ({len(session_data.get('messages', []))}):")
            for i, msg in enumerate(session_data.get('messages', []), 1):
                role = msg.get('role', 'unknown')
                content = msg.get('content', '')
                if isinstance(content, str):
                    content_preview = content[:100] + "..." if len(content) > 100 else content
                else:
                    content_preview = str(content)[:100] + "..."
                print(f"  {i}. [{role}] {content_preview}")

    # List archives
    archives = cache_store.get_session_archives(args.session_id)

    if archives:
        print(f"\nArchives ({len(archives)}):")
        for archive in archives:
            print(f"  - {archive['archive_id']}")
            print(f"    Created: {archive['created_at']}")
            print(f"    Original Tokens: {archive['original_tokens']}")
            print(f"    Summary Tokens: {archive['summary_tokens']}")
            print(f"    Compression: {archive['summary_tokens'] / archive['original_tokens'] * 100:.1f}%")


def delete_session(args):
    """Delete a session"""
    cache_store = CacheStore(CACHE_DIR)

    if not args.force:
        response = input(f"Delete session {args.session_id}? (y/n): ")
        if response.lower() != 'y':
            print("Cancelled")
            return

    success = cache_store.delete_session(args.session_id)

    if success:
        print(f"Session deleted: {args.session_id}")
    else:
        print(f"Error deleting session: {args.session_id}")


def show_archive(args):
    """Show archive details"""
    cache_store = CacheStore(CACHE_DIR)
    archive = cache_store.load_archive(args.archive_id)

    if not archive:
        print(f"Archive not found: {args.archive_id}")
        return

    print(f"\nArchive: {args.archive_id}")
    print("=" * 60)
    print(f"Session: {archive['session_id']}")
    print(f"Created: {archive['created_at']}")
    print(f"Messages: {len(archive['messages'])}")
    print(f"Original Tokens: {archive['original_tokens']}")
    print(f"Summary Tokens: {archive['summary_tokens']}")
    print(f"Compression: {archive['summary_tokens'] / archive['original_tokens'] * 100:.1f}%")

    print(f"\nSummary:")
    print("-" * 60)
    print(archive['summary'])

    if args.full:
        print(f"\nFull Messages ({len(archive['messages'])}):")
        print("-" * 60)
        for i, msg in enumerate(archive['messages'], 1):
            role = msg.get('role', 'unknown')
            content = msg.get('content', '')
            print(f"\n{i}. [{role}]")
            if isinstance(content, str):
                print(content)
            else:
                print(json.dumps(content, indent=2))


def cache_stats(args):
    """Show cache statistics"""
    cache_store = CacheStore(CACHE_DIR)
    stats = cache_store.get_cache_stats()

    print("\nCache Statistics")
    print("=" * 60)
    print(f"Cache Directory: {CACHE_DIR}")
    print(f"Total Sessions: {stats['total_sessions']}")
    print(f"Total Messages: {stats['total_messages']}")
    print(f"Total Tokens: {stats['total_tokens']:,}")
    print(f"Total Archives: {stats['total_archives']}")
    print(f"Archived Tokens: {stats['archived_tokens']:,}")
    print(f"Cache Size: {stats['cache_size_mb']} MB")

    if stats['total_tokens'] > 0:
        archive_ratio = stats['archived_tokens'] / stats['total_tokens'] * 100
        print(f"Archive Ratio: {archive_ratio:.1f}%")


def cleanup(args):
    """Clean up old sessions"""
    cache_store = CacheStore(CACHE_DIR)

    if not args.force:
        response = input(f"Delete sessions older than {args.days} days? (y/n): ")
        if response.lower() != 'y':
            print("Cancelled")
            return

    deleted = cache_store.cleanup_old_sessions(days=args.days)
    print(f"Deleted {deleted} old sessions")


def export_session(args):
    """Export session to JSON file"""
    cache_store = CacheStore(CACHE_DIR)
    session_data = cache_store.load_session(args.session_id)

    if not session_data:
        print(f"Session not found: {args.session_id}")
        return

    # Include archives if requested
    if args.include_archives:
        archives = cache_store.get_session_archives(args.session_id)
        session_data['archives'] = []

        for archive_meta in archives:
            archive_data = cache_store.load_archive(archive_meta['archive_id'])
            if archive_data:
                session_data['archives'].append(archive_data)

    output_file = args.output or f"{args.session_id}.json"

    with open(output_file, 'w') as f:
        json.dump(session_data, f, indent=2)

    print(f"Exported to: {output_file}")


def main():
    parser = argparse.ArgumentParser(description="Cache Management CLI")
    subparsers = parser.add_subparsers(dest='command', help='Commands')

    # List sessions
    list_parser = subparsers.add_parser('list', help='List all sessions')
    list_parser.add_argument('--limit', type=int, default=100, help='Maximum number of sessions')
    list_parser.set_defaults(func=list_sessions)

    # Show session
    show_parser = subparsers.add_parser('show', help='Show session details')
    show_parser.add_argument('session_id', help='Session ID')
    show_parser.add_argument('--messages', action='store_true', help='Show messages')
    show_parser.set_defaults(func=show_session)

    # Delete session
    delete_parser = subparsers.add_parser('delete', help='Delete a session')
    delete_parser.add_argument('session_id', help='Session ID')
    delete_parser.add_argument('--force', action='store_true', help='Skip confirmation')
    delete_parser.set_defaults(func=delete_session)

    # Show archive
    archive_parser = subparsers.add_parser('archive', help='Show archive details')
    archive_parser.add_argument('archive_id', help='Archive ID')
    archive_parser.add_argument('--full', action='store_true', help='Show full messages')
    archive_parser.set_defaults(func=show_archive)

    # Stats
    stats_parser = subparsers.add_parser('stats', help='Show cache statistics')
    stats_parser.set_defaults(func=cache_stats)

    # Cleanup
    cleanup_parser = subparsers.add_parser('cleanup', help='Clean up old sessions')
    cleanup_parser.add_argument('--days', type=int, default=30, help='Delete sessions older than N days')
    cleanup_parser.add_argument('--force', action='store_true', help='Skip confirmation')
    cleanup_parser.set_defaults(func=cleanup)

    # Export
    export_parser = subparsers.add_parser('export', help='Export session to JSON')
    export_parser.add_argument('session_id', help='Session ID')
    export_parser.add_argument('--output', help='Output file path')
    export_parser.add_argument('--include-archives', action='store_true', help='Include archives')
    export_parser.set_defaults(func=export_session)

    args = parser.parse_args()

    if not args.command:
        parser.print_help()
        return

    args.func(args)


if __name__ == "__main__":
    main()
