# -*- coding: utf-8 -*-
# Copyright 2025-2026 Project N.E.K.O. Team
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

"""Multipart upload persistence for the companion generation wizard.

The wizard (`static/companion/wizard/`) posts corpus files and multimodal
reference material (images / audio / video) to
``POST /api/companion/generate/upload``. This module owns the sync,
filesystem-only part of that endpoint: sanitizing client filenames, writing
the streams under the user docs directory, and merging decodable corpus
text files into the ``corpus_text`` that the analyze stage consumes.

Everything here is blocking by design — the async route offloads with
``asyncio.to_thread`` (same convention as ``start_generation``).
"""

from __future__ import annotations

import re
import unicodedata
import uuid
from dataclasses import dataclass, field
from pathlib import Path
from typing import BinaryIO

from config import (
  COMPANION_CORPUS_FILE_MERGE_MAX_CHARS,
  COMPANION_UPLOAD_MAX_FILE_BYTES,
  COMPANION_UPLOAD_MAX_FILES_PER_FIELD,
)
from utils.config_manager import get_config_manager
from utils.logger_config import get_module_logger

logger = get_module_logger(__name__)

# Corpus files with these suffixes are decoded and merged into corpus_text;
# anything else (pdf, docx, …) is only stored and referenced by path.
_TEXT_CORPUS_SUFFIXES = frozenset(
  {".txt", ".md", ".markdown", ".json", ".jsonl", ".csv", ".tsv", ".log", ".yaml", ".yml"}
)

_COPY_CHUNK_BYTES = 1024 * 1024

_UNSAFE_CHARS_RE = re.compile(r"[^\w.\-]+", re.UNICODE)


class UploadError(ValueError):
  """Raised when an upload violates count/size limits (HTTP 413)."""


def default_upload_root() -> Path:
  """Session uploads live next to the generated packages in the docs dir."""
  root = Path(get_config_manager().docs_dir) / "N.E.K.O" / "companions" / "uploads"
  root.mkdir(parents=True, exist_ok=True)
  return root


def sanitize_filename(name: str | None) -> str:
  """Reduce a client-supplied filename to a safe basename.

  Strips directory components from both separator conventions (browsers may
  send relative paths for directory uploads), normalizes unicode, and
  replaces anything outside ``[\\w.-]`` so the result can never traverse out
  of the session directory.
  """
  base = Path((name or "").replace("\\", "/")).name
  base = unicodedata.normalize("NFKC", base).strip().strip(".")
  base = _UNSAFE_CHARS_RE.sub("_", base)
  return base or "file"


@dataclass
class SavedUploads:
  """Result of persisting one wizard multipart submission."""

  session_dir: str
  corpus_files: list[str] = field(default_factory=list)
  reference_images: list[str] = field(default_factory=list)
  reference_audio: list[str] = field(default_factory=list)
  reference_video: list[str] = field(default_factory=list)
  merged_corpus_text: str = ""

  def counts(self) -> dict[str, int]:
    return {
      "corpus_files": len(self.corpus_files),
      "reference_images": len(self.reference_images),
      "reference_audio": len(self.reference_audio),
      "reference_video": len(self.reference_video),
    }


def _save_stream(stream: BinaryIO, dest: Path) -> None:
  """Chunked copy with a hard size cap; never buffers the file in memory."""
  written = 0
  try:
    with dest.open("wb") as out:
      while True:
        chunk = stream.read(_COPY_CHUNK_BYTES)
        if not chunk:
          break
        written += len(chunk)
        if written > COMPANION_UPLOAD_MAX_FILE_BYTES:
          raise UploadError(
            f"file '{dest.name}' exceeds "
            f"{COMPANION_UPLOAD_MAX_FILE_BYTES // (1024 * 1024)} MB limit"
          )
        out.write(chunk)
  except UploadError:
    dest.unlink(missing_ok=True)
    raise


def _save_category(
  files: list[tuple[str | None, BinaryIO]], category: str, session_dir: Path
) -> list[str]:
  if len(files) > COMPANION_UPLOAD_MAX_FILES_PER_FIELD:
    raise UploadError(
      f"too many files for '{category}' "
      f"(max {COMPANION_UPLOAD_MAX_FILES_PER_FIELD})"
    )
  saved: list[str] = []
  target_dir = session_dir / category
  for index, (filename, stream) in enumerate(files):
    target_dir.mkdir(parents=True, exist_ok=True)
    # Index prefix keeps duplicate client filenames from clobbering each other.
    dest = target_dir / f"{index:02d}_{sanitize_filename(filename)}"
    _save_stream(stream, dest)
    saved.append(str(dest))
  return saved


def _merge_corpus_text(inline_text: str, corpus_paths: list[str]) -> str:
  """Concatenate inline corpus text with decodable uploaded corpus files."""
  parts: list[str] = []
  budget = COMPANION_CORPUS_FILE_MERGE_MAX_CHARS
  inline = (inline_text or "").strip()
  if inline:
    parts.append(inline[:budget])
    budget -= len(parts[0])
  for raw_path in corpus_paths:
    if budget <= 0:
      break
    path = Path(raw_path)
    if path.suffix.lower() not in _TEXT_CORPUS_SUFFIXES:
      continue
    try:
      text = path.read_text(encoding="utf-8", errors="replace").strip()
    except OSError:
      logger.warning("Companion wizard: unreadable corpus upload %s", path, exc_info=True)
      continue
    if text:
      parts.append(text[:budget])
      budget -= len(parts[-1])
  return "\n\n".join(parts)


def save_generation_uploads(
  corpus_files: list[tuple[str | None, BinaryIO]],
  reference_images: list[tuple[str | None, BinaryIO]],
  reference_audio: list[tuple[str | None, BinaryIO]],
  reference_video: list[tuple[str | None, BinaryIO]],
  inline_corpus_text: str = "",
  upload_root: Path | None = None,
) -> SavedUploads:
  """Persist one wizard submission under ``<upload_root>/<session uuid>/``.

  Raises :class:`UploadError` when count/size limits are exceeded; partial
  writes from the failing request are left on disk only within the session
  directory (cheap to inspect, trivially garbage-collectable by path).
  """
  root = upload_root or default_upload_root()
  session_dir = root / uuid.uuid4().hex
  saved = SavedUploads(session_dir=str(session_dir))
  saved.corpus_files = _save_category(corpus_files, "corpus", session_dir)
  saved.reference_images = _save_category(reference_images, "images", session_dir)
  saved.reference_audio = _save_category(reference_audio, "audio", session_dir)
  saved.reference_video = _save_category(reference_video, "video", session_dir)
  saved.merged_corpus_text = _merge_corpus_text(inline_corpus_text, saved.corpus_files)
  return saved
