"""hindsight-agent pages — manage knowledge pages for an agent.

All commands resolve agent_id → bank via the global config,
so the caller never needs to know Hindsight internals.
"""

from __future__ import annotations

import json

import click

from ..api import HindsightAPI
from ..config import get_agent


@click.group()
def pages() -> None:
    """Manage knowledge pages for an agent."""


@pages.command("list")
@click.argument("agent_id")
def list_pages(agent_id: str) -> None:
    """List all knowledge pages for an agent."""
    cfg = get_agent(agent_id)
    api = HindsightAPI(cfg.api_url)
    items = api.list_pages(cfg.bank_id)
    click.echo(json.dumps({"items": items}, indent=2))


@pages.command("get")
@click.argument("agent_id")
@click.argument("page_id")
def get_page(agent_id: str, page_id: str) -> None:
    """Get a specific knowledge page."""
    cfg = get_agent(agent_id)
    api = HindsightAPI(cfg.api_url)
    page = api.get_page(cfg.bank_id, page_id)
    click.echo(json.dumps(page, indent=2))


@pages.command("create")
@click.argument("agent_id")
@click.argument("name")
@click.argument("source_query")
@click.option("--id", "page_id", default=None, help="Custom page ID (auto-generated if omitted)")
def create_page(agent_id: str, name: str, source_query: str, page_id: str | None) -> None:
    """Create a new knowledge page.

    NAME is the page title.
    SOURCE_QUERY is the question the system re-asks on every consolidation
    to rebuild the page content from observations.
    """
    cfg = get_agent(agent_id)
    api = HindsightAPI(cfg.api_url)
    result = api.create_page(
        cfg.bank_id,
        name=name,
        source_query=source_query,
        page_id=page_id,
    )
    click.echo(json.dumps(result, indent=2))


@pages.command("update")
@click.argument("agent_id")
@click.argument("page_id")
@click.option("--name", default=None, help="New page name")
@click.option("--source-query", default=None, help="New source query")
def update_page(
    agent_id: str, page_id: str, name: str | None, source_query: str | None
) -> None:
    """Update a knowledge page's name or source query."""
    if name is None and source_query is None:
        raise click.ClickException("At least one of --name or --source-query must be provided.")
    cfg = get_agent(agent_id)
    api = HindsightAPI(cfg.api_url)
    result = api.update_page(cfg.bank_id, page_id, name=name, source_query=source_query)
    click.echo(json.dumps(result, indent=2))


@pages.command("delete")
@click.argument("agent_id")
@click.argument("page_id")
def delete_page(agent_id: str, page_id: str) -> None:
    """Delete a knowledge page."""
    cfg = get_agent(agent_id)
    api = HindsightAPI(cfg.api_url)
    api.delete_page(cfg.bank_id, page_id)
    click.echo(json.dumps({"success": True}))
