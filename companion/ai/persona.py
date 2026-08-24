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

"""Persona / character card bridge.

Bidirectional mapping between :class:`CompanionProfile` and the
``characters_router`` character card — the per-catgirl dict stored under
``characters.json`` ``猫娘.<档案名>``. System fields (``system_prompt`` /
``voice_id`` / avatar) live under the card's ``_reserved`` section and are
read/written through the ``utils.config_manager`` reserved-schema helpers,
so the card shape stays identical to what characters_router produces.
"""

from __future__ import annotations

from typing import Any

from companion.models.profile import AvatarKind, CompanionProfile, VoiceConfig

# Card keys the mapping handles explicitly; every other (user-defined)
# card field round-trips through ``profile.metadata["card_fields"]``.
_NICKNAME_KEY = "昵称"
_HANDLED_CARD_KEYS = frozenset({_NICKNAME_KEY, "档案名", "_reserved", "_field_order"})

# `_reserved.avatar.model_type` values understood by the frontend loaders.
_AVATAR_KIND_TO_MODEL_TYPE = {
  AvatarKind.LIVE2D: "live2d",
  AvatarKind.VRM: "vrm",
  AvatarKind.MMD: "mmd",
}
_MODEL_TYPE_TO_AVATAR_KIND = {v: k for k, v in _AVATAR_KIND_TO_MODEL_TYPE.items()}


class CharacterCardError(ValueError):
  """Raised when a profile cannot be turned into a valid character card."""


class CompanionPersonaBridge:
  def __init__(self, profile: CompanionProfile) -> None:
    self.profile = profile

  def to_character_payload(self) -> dict:
    """Flat public payload (API responses / UI), not the stored card shape."""
    return {
      "name": self.profile.name,
      "display_name": self.profile.display_name or self.profile.name,
      "system_prompt": self.profile.system_prompt,
      "locale": self.profile.locale,
      "tags": list(self.profile.tags),
    }

  def to_character_card(self) -> dict:
    """Render the profile as a characters.json card body (without the key)."""
    from utils.config_manager import set_reserved

    profile = self.profile
    card: dict[str, Any] = {}
    extra_fields = profile.metadata.get("card_fields")
    if isinstance(extra_fields, dict):
      card.update(
        {k: v for k, v in extra_fields.items() if k not in _HANDLED_CARD_KEYS}
      )
    if profile.display_name:
      card[_NICKNAME_KEY] = profile.display_name
    if profile.system_prompt:
      set_reserved(card, "system_prompt", profile.system_prompt)
    if profile.voice.voice_id:
      set_reserved(card, "voice_id", profile.voice.voice_id)
    model_type = _AVATAR_KIND_TO_MODEL_TYPE.get(profile.avatar_kind)
    if model_type:
      set_reserved(card, "avatar", "model_type", model_type)
    if profile.avatar_kind == AvatarKind.LIVE2D and profile.avatar_resource_id:
      set_reserved(card, "avatar", "live2d", "model_path", profile.avatar_resource_id)
    return card

  @classmethod
  def from_character_card(
    cls,
    name: str,
    card: dict,
    profile_id: str | None = None,
    locale: str = "zh-CN",
  ) -> "CompanionPersonaBridge":
    """Build a bridge (and profile) from a stored character card."""
    from utils.config_manager import get_reserved

    system_prompt = get_reserved(
      card, "system_prompt", default="", legacy_keys=("system_prompt",)
    )
    voice_id = get_reserved(card, "voice_id", default="", legacy_keys=("voice_id",))
    if not isinstance(voice_id, str):
      # Structured voice-source objects ({source, provider, ref}) are owned
      # by the voice registry; the companion profile only mirrors flat ids.
      voice_id = ""
    model_type = get_reserved(
      card, "avatar", "model_type", default="", legacy_keys=("model_type",)
    )
    avatar_kind = _MODEL_TYPE_TO_AVATAR_KIND.get(str(model_type or ""), AvatarKind.LIVE2D)
    avatar_resource_id = ""
    if avatar_kind == AvatarKind.LIVE2D:
      avatar_resource_id = str(
        get_reserved(
          card, "avatar", "live2d", "model_path", default="", legacy_keys=("live2d",)
        )
        or ""
      )
    card_fields = {k: v for k, v in card.items() if k not in _HANDLED_CARD_KEYS}
    profile = CompanionProfile(
      id=profile_id or f"card-{name}",
      name=name,
      display_name=str(card.get(_NICKNAME_KEY) or ""),
      locale=locale,
      system_prompt=str(system_prompt or ""),
      avatar_kind=avatar_kind,
      avatar_resource_id=avatar_resource_id,
      voice=VoiceConfig(voice_id=voice_id),
      memory_character_name=name,
      metadata={"card_fields": card_fields} if card_fields else {},
    )
    return cls(profile)


async def register_character_card(
  profile: CompanionProfile, config_manager=None
) -> str:
  """Write the profile into characters.json as a new catgirl card.

  Mirrors ``characters_router.add_catgirl`` semantics: the profile name is
  validated with the shared character-name rules and conflicts are resolved
  Windows-style (``name(1)``). Returns the final card key — callers must use
  it (not ``profile.name``) as the memory character name.
  """
  from utils.character_name import PROFILE_NAME_MAX_UNITS, validate_character_name

  result = validate_character_name(profile.name, max_units=PROFILE_NAME_MAX_UNITS)
  if result.code is not None:
    raise CharacterCardError(f"invalid companion name: {result.code}")
  key = result.normalized

  if config_manager is None:
    from utils.config_manager import get_config_manager

    config_manager = get_config_manager()

  characters = await config_manager.aload_characters()
  catgirls = characters.setdefault("猫娘", {})
  if key in catgirls:
    base_name = key
    counter = 1
    while f"{base_name}({counter})" in catgirls:
      counter += 1
    key = f"{base_name}({counter})"

  catgirls[key] = CompanionPersonaBridge(profile).to_character_card()
  await config_manager.asave_characters(characters)
  return key
