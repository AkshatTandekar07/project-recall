#!/usr/bin/env python3
"""
recall.py — ProjectRecall CLI
Save YouTube Shorts and retrieve knowledge from them using local AI.

Usage:
  python recall.py save <youtube_url>
  python recall.py ask "your question in quotes"
  python recall.py list
  python recall.py filter --tag <tag>
  python recall.py filter --date <YYYY-MM>
  python recall.py delete <video_id>
"""

import sys
import argparse
import json
from pathlib import Path

# Force UTF-8 encoding for standard output on Windows to support emojis and rich spinners
if sys.platform == "win32":
    sys.stdout.reconfigure(encoding="utf-8")

from rich.console import Console
from rich.table import Table
from rich.panel import Panel
from rich.progress import Progress, SpinnerColumn, TextColumn
from rich.text import Text
from rich import box

console = Console()


# ===========================================================================
# COMMAND: save
# ===========================================================================
def cmd_save(args):
    """Full ingestion + AI pipeline for a single YouTube URL."""
    from src.ingestion import extract_video_id, fetch_metadata, download_thumbnail, fetch_transcript
    from src.ai_processor import verify_api_key, summarize_transcript, chunk_text, get_embedding, verify_with_web
    from src.storage import get_client, get_collection, check_duplicate, save_content
    from src.config import MAX_SHORT_DURATION

    url = args.url

    console.print()
    console.rule("[bold cyan]ProjectRecall — Saving Video[/]")
    console.print()

    # ── Step 1: Parse URL ──────────────────────────────────────────────────
    with console.status("[cyan]Parsing URL...[/]"):
        video_id = extract_video_id(url)

    if not video_id:
        console.print(f"[bold red]X Error:[/] Could not extract a video ID from:\n  [dim]{url}[/]")
        console.print("\n[yellow]Supported formats:[/]")
        console.print("  • youtube.com/shorts/<id>")
        console.print("  • m.youtube.com/shorts/<id>")
        console.print("  • youtu.be/<id>")
        console.print("  • youtube.com/watch?v=<id>")
        sys.exit(1)

    console.print(f"[green]OK[/] Video ID: [bold]{video_id}[/]")

    # ── Step 2: API Key check ──────────────────────────────────────────────
    with console.status("[cyan]Checking Gemini API key...[/]"):
        healthy = verify_api_key()

    if not healthy:
        console.print("[bold red]X Gemini API key is missing.[/]")
        console.print("\n[yellow]Please set up your .env file:[/]")
        console.print("  1. Create a file named [bold].env[/] in this folder")
        console.print("  2. Add your key like this: [bold]GEMINI_API_KEY=your_key_here[/]")
        console.print("  3. Get a free key at [blue underline]https://aistudio.google.com/[/]")
        sys.exit(1)

    console.print("[green]OK[/] Gemini API key found")

    # ── Step 3: Duplicate check ────────────────────────────────────────────
    client = get_client()
    collection = get_collection(client)

    existing = check_duplicate(collection, video_id)
    if existing:
        console.print(
            f"\n[yellow]X Already saved:[/] [bold]{existing.get('title', video_id)}[/]"
        )
        console.print(f"[dim]Saved at: {existing.get('saved_at', 'unknown')}[/]")
        console.print("[dim]Skipping — use `delete` first if you want to re-save.[/]")
        sys.exit(0)

    # ── Step 4: Fetch metadata via yt-dlp ─────────────────────────────────
    with console.status("[cyan]Fetching video metadata (yt-dlp)...[/]"):
        meta = fetch_metadata(video_id)

    title = meta["title"]
    duration = meta["duration"]
    channel = meta["channel"]
    safe_title = title.encode("ascii", "ignore").decode("ascii")
    safe_channel = channel.encode("ascii", "ignore").decode("ascii")
    console.print(f"[green]OK[/] Fetched metadata: [bold]{safe_title}[/]")
    console.print(f"[dim]   Channel: {safe_channel} | Duration: {duration}s[/]")

    # ── Step 5: Duration guard ─────────────────────────────────────────────
    if duration > MAX_SHORT_DURATION:
        console.print(
            f"\n[yellow]X Warning:[/] This video is {duration}s "
            f"(>{MAX_SHORT_DURATION}s). It may not be a YouTube Short."
        )
        try:
            answer = console.input("[yellow]Continue saving anyway? [y/N]: [/]").strip().lower()
        except (EOFError, KeyboardInterrupt):
            answer = "n"

        if answer != "y":
            console.print("[dim]Cancelled.[/]")
            sys.exit(0)

    # ── Step 6: Download thumbnail ─────────────────────────────────────────
    with console.status("[cyan]Downloading thumbnail...[/]"):
        thumb_path = download_thumbnail(video_id, meta["thumbnail_url"])

    if thumb_path:
        console.print(f"[green]OK[/] Thumbnail saved [dim]({thumb_path})[/]")
    else:
        console.print("[dim]  Thumbnail not available — continuing...[/]")
        thumb_path = ""

    # ── Step 7: Fetch transcript ───────────────────────────────────────────
    with console.status("[cyan]Fetching transcript...[/]"):
        transcript = fetch_transcript(video_id)

    if not transcript:
        console.print("\n[bold red]X No transcript available.[/]")
        console.print(
            "[dim]This video may have captions disabled or be in an "
            "unsupported language. Cannot process without a transcript.[/]"
        )
        sys.exit(1)

    word_count = len(transcript.split())
    console.print(f"[green]OK[/] Transcript fetched ({word_count} words)")

    # ── Step 8: Summarize + tag ────────────────────────────────────────────
    with console.status("[cyan]Summarizing with Gemini...[/]"):
        content_summary = summarize_transcript(transcript, title)

    console.print(f"[green]OK[/] Summary generated")
    console.print(f"[dim]   Tags: {', '.join(content_summary.tags)}[/]")

    # ── Step 9: Web verification ───────────────────────────────────────────
    with console.status("[cyan]Verifying claims on the web...[/]"):
        web_urls = verify_with_web(content_summary.summary)

    if web_urls:
        console.print(f"[green]OK[/] Web verification: {len(web_urls)} source(s) found")
    else:
        console.print("[dim]  Web verification unavailable — continuing...[/]")

    # ── Step 10: Chunk + embed ─────────────────────────────────────────────
    chunks = chunk_text(transcript)
    console.print(f"[green]OK[/] Split into {len(chunks)} chunks")

    embeddings = []
    with Progress(
        SpinnerColumn(),
        TextColumn("[cyan]Generating embeddings... {task.completed}/{task.total}[/]"),
        console=console,
    ) as progress:
        task_id = progress.add_task("embed", total=len(chunks))
        for chunk in chunks:
            embeddings.append(get_embedding(chunk))
            progress.advance(task_id)

    console.print(f"[green]OK[/] Vector embeddings generated ({len(embeddings)} vectors)")

    # ── Step 11: Save to ChromaDB ──────────────────────────────────────────
    with console.status("[cyan]Saving to local database...[/]"):
        saved_at = save_content(
            collection=collection,
            video_id=video_id,
            source_url=url,
            title=title,
            duration_seconds=duration,
            summary=content_summary.summary,
            tags=content_summary.tags,
            thumbnail_local_path=thumb_path,
            web_verification_urls=web_urls,
            chunks=chunks,
            embeddings=embeddings,
        )

    # ── Final summary panel ────────────────────────────────────────────────
    console.print()
    console.print(Panel(
        f"[bold green]✓ Saved successfully![/]\n\n"
        f"[bold]Title:[/]    {title}\n"
        f"[bold]Video ID:[/] {video_id}\n"
        f"[bold]Tags:[/]     {', '.join(content_summary.tags)}\n"
        f"[bold]Chunks:[/]   {len(chunks)}\n"
        f"[bold]Saved:[/]    {saved_at[:19].replace('T', ' ')}\n\n"
        f"[dim]{content_summary.summary}[/]",
        title="[bold]ProjectRecall[/]",
        border_style="green",
        padding=(1, 2),
    ))
    console.print()


# ===========================================================================
# COMMAND: ask
# ===========================================================================
def cmd_ask(args):
    """Semantic RAG retrieval — ask a question about saved videos."""
    from src.ai_processor import verify_api_key
    from src.retrieval import ask_question

    question = args.question

    if not verify_api_key():
        console.print(
            "[bold red]X Gemini API key is missing.[/] "
            "Please add GEMINI_API_KEY to your .env file."
        )
        sys.exit(1)

    console.print()
    console.print(Panel(
        f"[bold]{question}[/]",
        title="[cyan]Your Question[/]",
        border_style="cyan",
        padding=(0, 2),
    ))

    with console.status("[cyan]Searching and generating answer...[/]"):
        result = ask_question(question)

    console.print()
    console.print(Panel(
        result["answer"],
        title="[bold]Answer[/]",
        border_style="green",
        padding=(1, 2),
    ))

    if result["sources"]:
        console.print()
        console.print("[bold]📎 Sources used:[/]")
        for src in result["sources"]:
            console.print(f"  • [bold]{src['title']}[/]")
            console.print(f"    [blue underline]{src['url']}[/]")
            if src["tags"]:
                console.print(f"    [dim]Tags: {', '.join(src['tags'])}[/]")
            if src["web_verification_urls"]:
                console.print(f"    [dim]Web refs: {', '.join(src['web_verification_urls'][:2])}[/]")

    console.print()


# ===========================================================================
# COMMAND: list
# ===========================================================================
def cmd_list(args):
    """List all saved YouTube Shorts."""
    from src.storage import get_client, get_collection, list_all_items

    client = get_client()
    collection = get_collection(client)
    items = list_all_items(collection)

    if not items:
        console.print()
        console.print(Panel(
            "No videos saved yet.\n\nGet started:\n"
            "  [bold]python recall.py save https://youtube.com/shorts/<id>[/]",
            title="[yellow]ProjectRecall — Empty[/]",
            border_style="yellow",
        ))
        return

    table = Table(
        title=f"Saved YouTube Shorts — {len(items)} total",
        border_style="cyan",
        box=box.ROUNDED,
        show_lines=True,
    )
    table.add_column("#", style="dim", width=4, justify="right")
    table.add_column("Title", style="bold white", max_width=38)
    table.add_column("Tags", style="green", max_width=28)
    table.add_column("Saved", style="dim", width=12)
    table.add_column("Video ID", style="dim", width=13)
    table.add_column("URL", style="blue", max_width=40, no_wrap=True)

    for i, item in enumerate(items, 1):
        tags = json.loads(item.get("tags", "[]"))
        saved_date = item.get("saved_at", "")[:10]
        table.add_row(
            str(i),
            item.get("title", "Unknown"),
            ", ".join(tags[:3]) + ("…" if len(tags) > 3 else ""),
            saved_date,
            item.get("video_id", ""),
            item.get("source_url", ""),
        )

    console.print()
    console.print(table)
    console.print()


# ===========================================================================
# COMMAND: filter
# ===========================================================================
def cmd_filter(args):
    """Filter saved videos by tag or save date."""
    from src.storage import get_client, get_collection, filter_by_tag, filter_by_date

    if not args.tag and not args.date:
        console.print(
            "[red]Error:[/] Provide --tag or --date.\n\n"
            "Examples:\n"
            "  [bold]python recall.py filter --tag cooking[/]\n"
            "  [bold]python recall.py filter --date 2025-06[/]"
        )
        sys.exit(1)

    client = get_client()
    collection = get_collection(client)

    if args.tag:
        items = filter_by_tag(collection, args.tag)
        filter_label = f"tag = '{args.tag}'"
    else:
        items = filter_by_date(collection, args.date)
        filter_label = f"date = '{args.date}'"

    if not items:
        console.print(f"\n[yellow]No results found for {filter_label}.[/]\n")
        return

    table = Table(
        title=f"Filter: {filter_label} — {len(items)} result(s)",
        border_style="cyan",
        box=box.ROUNDED,
        show_lines=True,
    )
    table.add_column("#", style="dim", width=4, justify="right")
    table.add_column("Title", style="bold white", max_width=38)
    table.add_column("Tags", style="green", max_width=30)
    table.add_column("Saved", style="dim", width=12)
    table.add_column("URL", style="blue", max_width=44, no_wrap=True)

    for i, item in enumerate(items, 1):
        tags = json.loads(item.get("tags", "[]"))
        table.add_row(
            str(i),
            item.get("title", "Unknown"),
            ", ".join(tags),
            item.get("saved_at", "")[:10],
            item.get("source_url", ""),
        )

    console.print()
    console.print(table)
    console.print()


# ===========================================================================
# COMMAND: delete
# ===========================================================================
def cmd_delete(args):
    """Delete all data for a saved video by its video ID."""
    from src.storage import get_client, get_collection, delete_video, check_duplicate

    video_id = args.video_id
    client = get_client()
    collection = get_collection(client)

    # Show what we're about to delete
    existing = check_duplicate(collection, video_id)
    if not existing:
        console.print(f"\n[yellow]Video ID [bold]{video_id}[/] not found in database.[/]\n")
        sys.exit(0)

    console.print(f"\n[bold]About to delete:[/] {existing.get('title', video_id)}")
    console.print(f"[dim]Saved at: {existing.get('saved_at', 'unknown')}[/]")

    try:
        answer = console.input(
            f"\n[red]This cannot be undone. Delete? [y/N]: [/]"
        ).strip().lower()
    except (EOFError, KeyboardInterrupt):
        answer = "n"

    if answer != "y":
        console.print("[dim]Cancelled.[/]")
        return

    with console.status("[cyan]Deleting...[/]"):
        deleted_count = delete_video(collection, video_id)

    console.print(
        f"\n[green]✓[/] Deleted [bold]{deleted_count}[/] chunk(s) "
        f"for video [bold]{video_id}[/]\n"
    )


# ===========================================================================
# ARGUMENT PARSER
# ===========================================================================
def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="recall.py",
        description="ProjectRecall — Save and retrieve knowledge from YouTube Shorts using local AI.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""\
Examples:
  python recall.py save https://www.youtube.com/shorts/dQw4w9WgXcQ
  python recall.py save https://youtu.be/dQw4w9WgXcQ

  python recall.py ask "What did the video about Python tips say?"
      -> Always wrap your question in quotes!

  python recall.py list
  python recall.py filter --tag cooking
  python recall.py filter --date 2025-06
  python recall.py delete dQw4w9WgXcQ
""",
    )

    subparsers = parser.add_subparsers(dest="command", required=True)

    # save
    p_save = subparsers.add_parser(
        "save", help="Save a YouTube Short (fetches transcript, summarizes, stores)"
    )
    p_save.add_argument("url", help="Full YouTube Short URL")
    p_save.set_defaults(func=cmd_save)

    # ask
    p_ask = subparsers.add_parser(
        "ask", help='Ask a question about your saved videos. WRAP IN QUOTES: ask "..."'
    )
    p_ask.add_argument(
        "question",
        help='Your question. MUST be in quotes: python recall.py ask "your question here"',
    )
    p_ask.set_defaults(func=cmd_ask)

    # list
    p_list = subparsers.add_parser("list", help="List all saved YouTube Shorts")
    p_list.set_defaults(func=cmd_list)

    # filter
    p_filter = subparsers.add_parser("filter", help="Filter saved videos by tag or date")
    p_filter.add_argument("--tag", metavar="TAG", help="Filter by tag (partial match, case-insensitive)")
    p_filter.add_argument(
        "--date",
        metavar="YYYY-MM",
        help="Filter by save month. Example: --date 2025-06",
    )
    p_filter.set_defaults(func=cmd_filter)

    # delete
    p_delete = subparsers.add_parser("delete", help="Delete a saved video by its 11-character video ID")
    p_delete.add_argument(
        "video_id",
        help="11-character YouTube video ID (from `list` output)",
    )
    p_delete.set_defaults(func=cmd_delete)

    return parser


# ===========================================================================
# ENTRY POINT
# ===========================================================================
def main():
    parser = build_parser()
    args = parser.parse_args()

    try:
        args.func(args)
    except KeyboardInterrupt:
        console.print("\n[dim]Interrupted.[/]")
        sys.exit(0)
    except RuntimeError as exc:
        console.print(f"\n[bold red]✗ Error:[/] {exc}\n")
        sys.exit(1)
    except Exception as exc:
        console.print(f"\n[bold red]X Unexpected error:[/] {exc}")
        console.print("[dim]Run with PYTHONTRACEBACK=1 for full traceback.[/]")
        sys.exit(1)


if __name__ == "__main__":
    main()
