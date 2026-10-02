"""SQLite connection (WAL) and ordered schema migrations."""

from __future__ import annotations

import functools

from .hoard_link import sqlkit

MIGRATIONS: list[str] = [
    # 1: decks, sources, slides, revisions, assets, exports, settings
    """
    CREATE TABLE settings (key TEXT PRIMARY KEY, value TEXT NOT NULL);
    CREATE TABLE decks (
      id TEXT PRIMARY KEY,
      title TEXT NOT NULL,
      brief TEXT NOT NULL DEFAULT '',
      audience TEXT NOT NULL DEFAULT '',
      tone TEXT NOT NULL DEFAULT '',
      language TEXT NOT NULL DEFAULT 'es',
      slide_count INTEGER NOT NULL DEFAULT 10,
      theme TEXT NOT NULL DEFAULT 'claro',
      status TEXT NOT NULL DEFAULT 'draft',
      outline TEXT NOT NULL DEFAULT '[]',
      model_used TEXT,
      created_ts REAL NOT NULL,
      updated_ts REAL NOT NULL
    );
    CREATE TABLE sources (
      id INTEGER PRIMARY KEY AUTOINCREMENT,
      deck_id TEXT NOT NULL REFERENCES decks(id) ON DELETE CASCADE,
      title TEXT NOT NULL DEFAULT '',
      kind TEXT NOT NULL DEFAULT 'text',
      chars INTEGER NOT NULL DEFAULT 0,
      text TEXT NOT NULL DEFAULT '',
      sha256 TEXT NOT NULL DEFAULT '',
      truncated INTEGER NOT NULL DEFAULT 0,
      created_ts REAL NOT NULL
    );
    CREATE INDEX sources_deck ON sources(deck_id);
    CREATE TABLE slides (
      id TEXT PRIMARY KEY,
      deck_id TEXT NOT NULL REFERENCES decks(id) ON DELETE CASCADE,
      position INTEGER NOT NULL,
      layout TEXT NOT NULL DEFAULT 'bullets',
      title TEXT NOT NULL DEFAULT '',
      subtitle TEXT,
      blocks TEXT NOT NULL DEFAULT '[]',
      notes TEXT NOT NULL DEFAULT '',
      status TEXT NOT NULL DEFAULT 'draft',
      revision INTEGER NOT NULL DEFAULT 1,
      sources TEXT NOT NULL DEFAULT '[]',
      image_prompt TEXT,
      outline_id TEXT,
      created_ts REAL NOT NULL,
      updated_ts REAL NOT NULL
    );
    CREATE INDEX slides_deck ON slides(deck_id, position);
    CREATE TABLE revisions (
      slide_id TEXT NOT NULL REFERENCES slides(id) ON DELETE CASCADE,
      revision INTEGER NOT NULL,
      created_ts REAL NOT NULL,
      reason TEXT NOT NULL,
      snapshot TEXT NOT NULL,
      PRIMARY KEY (slide_id, revision)
    );
    CREATE TABLE assets (
      id TEXT PRIMARY KEY,
      deck_id TEXT NOT NULL REFERENCES decks(id) ON DELETE CASCADE,
      filename TEXT NOT NULL DEFAULT '',
      mime TEXT NOT NULL,
      ext TEXT NOT NULL,
      width INTEGER NOT NULL,
      height INTEGER NOT NULL,
      bytes INTEGER NOT NULL,
      sha256 TEXT NOT NULL,
      created_ts REAL NOT NULL
    );
    CREATE INDEX assets_deck ON assets(deck_id);
    CREATE TABLE exports (
      id TEXT PRIMARY KEY,
      deck_id TEXT NOT NULL REFERENCES decks(id) ON DELETE CASCADE,
      format TEXT NOT NULL,
      filename TEXT NOT NULL,
      bytes INTEGER NOT NULL,
      sha256 TEXT NOT NULL,
      created_ts REAL NOT NULL
    );
    CREATE INDEX exports_deck ON exports(deck_id, created_ts);
    """,
    # 2: themes made from another app's design system (a deck's `theme` column may name one)
    """
    CREATE TABLE custom_themes (
      id TEXT PRIMARY KEY,
      name TEXT NOT NULL,
      definition TEXT NOT NULL,
      source_ref TEXT NOT NULL DEFAULT '',
      source_revision TEXT NOT NULL DEFAULT '',
      warnings TEXT NOT NULL DEFAULT '[]',
      created_ts REAL NOT NULL
    );
    CREATE INDEX custom_themes_source ON custom_themes(source_ref, source_revision);
    """,
]


# the shared SQLite layer: WAL, busy timeout, re-entrant ``tx()`` / ``transaction()``, foreign keys, ordered migrations
Database = functools.partial(sqlkit.Database, migrations=MIGRATIONS, foreign_keys=True)
