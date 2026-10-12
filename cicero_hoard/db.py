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
    # 3: retryable draft batches; the receipt and slides commit together.
    """
    CREATE TABLE slide_batches (
      deck_id TEXT NOT NULL REFERENCES decks(id) ON DELETE CASCADE,
      batch_key TEXT NOT NULL,
      payload_sha256 TEXT NOT NULL,
      slide_ids TEXT NOT NULL,
      PRIMARY KEY (deck_id, batch_key)
    );
    """,
    # 4: immutable local PPTX template snapshot and semantic slide bindings.
    "ALTER TABLE decks ADD COLUMN template TEXT;",
    # 5: linked data recipes and media metadata, without changing immutable source snapshots.
    """
    CREATE TABLE data_links (
      id TEXT PRIMARY KEY,
      deck_id TEXT NOT NULL REFERENCES decks(id) ON DELETE CASCADE,
      definition TEXT NOT NULL,
      source_id INTEGER REFERENCES sources(id) ON DELETE SET NULL,
      enabled INTEGER NOT NULL DEFAULT 1,
      interval_s REAL NOT NULL DEFAULT 60,
      checked_ts REAL,
      refreshed_ts REAL,
      error TEXT NOT NULL DEFAULT '',
      revision INTEGER NOT NULL DEFAULT 1
    );
    CREATE TABLE data_bindings (
      id TEXT PRIMARY KEY,
      link_id TEXT NOT NULL REFERENCES data_links(id) ON DELETE CASCADE,
      slide_id TEXT NOT NULL REFERENCES slides(id) ON DELETE CASCADE,
      block_id TEXT NOT NULL,
      definition TEXT NOT NULL,
      last_block TEXT NOT NULL,
      error TEXT NOT NULL DEFAULT '',
      UNIQUE(slide_id, block_id)
    );
    CREATE TABLE media_metadata (
      asset_id TEXT PRIMARY KEY REFERENCES assets(id) ON DELETE CASCADE,
      definition TEXT NOT NULL
    );
    """,
    # 6: durable render evidence, polls and collaborative document state.
    """
    CREATE TABLE visual_variants(id TEXT PRIMARY KEY,deck_id TEXT NOT NULL REFERENCES decks(id) ON DELETE CASCADE,
      slide_id TEXT NOT NULL REFERENCES slides(id) ON DELETE CASCADE,revision INTEGER NOT NULL,label TEXT NOT NULL,
      patch TEXT NOT NULL,metrics TEXT NOT NULL DEFAULT '{}',png TEXT,created_ts REAL NOT NULL);
    CREATE TABLE polls(id TEXT PRIMARY KEY,deck_id TEXT NOT NULL REFERENCES decks(id) ON DELETE CASCADE,
      title TEXT NOT NULL,options TEXT NOT NULL,open INTEGER NOT NULL DEFAULT 1,created_ts REAL NOT NULL);
    CREATE TABLE poll_votes(poll_id TEXT NOT NULL REFERENCES polls(id) ON DELETE CASCADE,participant TEXT NOT NULL,
      choice INTEGER NOT NULL,created_ts REAL NOT NULL,PRIMARY KEY(poll_id,participant));
    CREATE TABLE collab_documents(slide_id TEXT PRIMARY KEY REFERENCES slides(id) ON DELETE CASCADE,
      state TEXT NOT NULL,snapshot TEXT NOT NULL,version INTEGER NOT NULL DEFAULT 1);
    CREATE TABLE collab_presence(slide_id TEXT NOT NULL REFERENCES slides(id) ON DELETE CASCADE,actor TEXT NOT NULL,
      label TEXT NOT NULL,color TEXT NOT NULL,updated_ts REAL NOT NULL,PRIMARY KEY(slide_id,actor));
    """,
    # 7: resetting a poll keeps a recoverable local round.
    """
    CREATE TABLE poll_rounds(id TEXT PRIMARY KEY,poll_id TEXT NOT NULL REFERENCES polls(id) ON DELETE CASCADE,
      votes TEXT NOT NULL,created_ts REAL NOT NULL);
    """,
]


# the shared SQLite layer: WAL, busy timeout, re-entrant ``tx()`` / ``transaction()``, foreign keys, ordered migrations
Database = functools.partial(sqlkit.Database, migrations=MIGRATIONS, foreign_keys=True)
