"""Target registry loaded from config/targets.yaml (including Matter node/endpoint mapping)."""

from __future__ import annotations

from dataclasses import dataclass, field
from functools import lru_cache
from pathlib import Path
from typing import Dict, Iterable, List, Optional, Sequence, Set, Tuple

import yaml
from pydantic import BaseModel, Field, field_validator

from shared.schemas import Action, ClarificationReason
from shared.settings import get_settings

ALLOWED_ACTIONS: Set[str] = {"ON", "OFF", "STATUS"}
_ALL_WORDS = {"all", "everything", "every light", "all lights"}


def _alias_key(value: str) -> str:
    return " ".join(value.strip().lower().replace("_", " ").replace("-", " ").split())


class TargetConfig(BaseModel):
    id: str
    display_name: str
    node_id: Optional[int] = Field(default=None, ge=1)
    endpoint_id: int = Field(default=1, ge=0)
    aliases: List[str] = Field(default_factory=list)
    supported_actions: List[Action] = Field(default_factory=lambda: ["ON", "OFF", "STATUS"])
    enabled: bool = True

    @field_validator("id")
    @classmethod
    def normalize_id(cls, value: str) -> str:
        cleaned = value.strip().lower().replace(" ", "_").replace("-", "_")
        if not cleaned or cleaned == "all":
            raise ValueError("target id must be non-empty and cannot be 'all'")
        return cleaned

    @field_validator("aliases")
    @classmethod
    def normalize_aliases(cls, values: List[str]) -> List[str]:
        out: List[str] = []
        for raw in values:
            alias = _alias_key(str(raw))
            if alias and alias not in out:
                out.append(alias)
        return out

    @field_validator("supported_actions", mode="before")
    @classmethod
    def validate_actions(cls, values: object) -> List[str]:
        if not isinstance(values, list) or not values:
            raise ValueError("supported_actions must not be empty")
        out: List[str] = []
        for value in values:
            token = "ON" if value is True else "OFF" if value is False else str(value).strip().upper()
            if token not in ALLOWED_ACTIONS:
                raise ValueError(f"unsupported action in registry: {value!r}")
            if token not in out:
                out.append(token)
        return out

    @field_validator("node_id", mode="before")
    @classmethod
    def empty_node_id(cls, value: object) -> object:
        if value is None or value == "" or value == "null":
            return None
        return value


class TargetsFile(BaseModel):
    targets: List[TargetConfig]


@dataclass(frozen=True)
class TargetRecord:
    id: str
    display_name: str
    node_id: Optional[int]
    endpoint_id: int
    aliases: Sequence[str]
    supported_actions: Sequence[str]
    enabled: bool

    def supports(self, action: str) -> bool:
        return action.upper() in self.supported_actions

    @property
    def commissioned(self) -> bool:
        return self.node_id is not None


@dataclass
class TargetRegistry:
    """Lookup helpers for AI target resolution, Safety validation, and Matter node mapping."""

    records: Dict[str, TargetRecord] = field(default_factory=dict)
    _alias_index: Dict[str, str] = field(default_factory=dict, repr=False)
    _endpoint_index: Dict[Tuple[int, int], str] = field(default_factory=dict, repr=False)

    @classmethod
    def from_records(cls, records: Iterable[TargetRecord]) -> "TargetRegistry":
        registry = cls()
        for record in records:
            if record.id in registry.records:
                raise ValueError(f"duplicate target id: {record.id}")
            if record.id == "all":
                raise ValueError("'all' is not a V1 target")
            if record.commissioned:
                endpoint_key = (int(record.node_id), record.endpoint_id)  # type: ignore[arg-type]
                if endpoint_key in registry._endpoint_index:
                    other = registry._endpoint_index[endpoint_key]
                    raise ValueError(
                        f"Matter node/endpoint {endpoint_key} shared by '{other}' and '{record.id}'"
                    )
                registry._endpoint_index[endpoint_key] = record.id
            registry.records[record.id] = record

            for name in {record.id, record.display_name, *record.aliases}:
                key = _alias_key(name)
                if not key:
                    continue
                owner = registry._alias_index.get(key)
                if owner and owner != record.id:
                    raise ValueError(f"alias '{name}' collides between '{owner}' and '{record.id}'")
                registry._alias_index[key] = record.id
        if not registry.records:
            raise ValueError("target registry is empty")
        return registry

    @classmethod
    def load(cls, path: Optional[Path] = None) -> "TargetRegistry":
        targets_path = path or get_settings().resolved_targets_path()
        raw = yaml.safe_load(targets_path.read_text(encoding="utf-8")) or {}
        parsed = TargetsFile.model_validate(raw)
        return cls.from_records(
            TargetRecord(
                id=item.id,
                display_name=item.display_name,
                node_id=item.node_id,
                endpoint_id=item.endpoint_id,
                aliases=tuple(item.aliases),
                supported_actions=tuple(item.supported_actions),
                enabled=item.enabled,
            )
            for item in parsed.targets
        )

    def get(self, target_id: str) -> Optional[TargetRecord]:
        return self.records.get(target_id.strip().lower().replace(" ", "_").replace("-", "_"))

    def by_node_endpoint(self, node_id: int, endpoint_id: int = 1) -> Optional[TargetRecord]:
        tid = self._endpoint_index.get((node_id, endpoint_id))
        return self.records.get(tid) if tid else None

    def ids(self) -> List[str]:
        return sorted(self.records.keys())

    def commissioned_ids(self) -> List[str]:
        return [tid for tid in self.ids() if self.records[tid].commissioned]

    def display_names(self) -> List[str]:
        return [self.records[i].display_name for i in self.ids()]

    def find_mentions(self, text: str) -> List[str]:
        """Unique target ids mentioned in free text (longest alias first)."""
        consumed = f" {_alias_key(text)} "
        hits: List[str] = []
        for alias, target_id in sorted(self._alias_index.items(), key=lambda x: len(x[0]), reverse=True):
            token = f" {alias} "
            if token in consumed:
                if target_id not in hits:
                    hits.append(target_id)
                consumed = consumed.replace(token, " ")
        return hits

    def resolve(
        self, phrase: str, *, from_free_text: bool = False
    ) -> Tuple[Optional[str], Optional[ClarificationReason], List[str]]:
        """Return (target_id, None, []) on success or (None, reason, candidates)."""
        cleaned = (phrase or "").strip()
        if not cleaned:
            return None, ClarificationReason.UNKNOWN_TARGET, []
        if _alias_key(cleaned) in _ALL_WORDS:
            return None, ClarificationReason.MULTIPLE_TARGETS, self.ids()

        if not from_free_text:
            direct = self.get(cleaned) or (
                self.records.get(tid) if (tid := self._alias_index.get(_alias_key(cleaned))) else None
            )
            if direct is not None:
                return direct.id, None, []

        mentions = self.find_mentions(cleaned)
        if len(mentions) == 1:
            return mentions[0], None, []
        if len(mentions) > 1:
            reason = (
                ClarificationReason.MULTIPLE_TARGETS
                if from_free_text
                else ClarificationReason.AMBIGUOUS_TARGET
            )
            return None, reason, mentions
        return None, ClarificationReason.UNKNOWN_TARGET, []

    def zone_id_map(self) -> Dict[str, int]:
        return {
            rec.id: int(rec.node_id)
            for rec in self.records.values()
            if rec.node_id is not None
        }


@lru_cache(maxsize=4)
def get_target_registry(path: Optional[str] = None) -> TargetRegistry:
    return TargetRegistry.load(Path(path) if path else None)


def clear_target_registry_cache() -> None:
    get_target_registry.cache_clear()
