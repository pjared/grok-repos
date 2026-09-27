"""Which lineup card is current. No window and no keyboard hook."""

from __future__ import annotations

import threading
from dataclasses import dataclass
from pathlib import Path

from suit_o.lineups.library import LineupCard, list_cards
from suit_o.lineups.trigger import OverlayDecision, decision_from_snapshot
from suit_o.models import Snapshot


@dataclass(frozen=True)
class DeckView:
    """What the overlay should paint on the next tick."""

    visible: bool
    reason: str
    map_key: str
    side: str
    index: int
    total: int
    card: LineupCard | None
    hidden: bool


class LineupDeck:
    """Remember map, side, and weapon across partial payloads, and cycle cards."""

    def __init__(self, root: Path, *, pack_dir: Path | None = None) -> None:
        self.root = root
        self.pack_dir = pack_dir
        self.hidden = False
        self.enabled = True
        self.smokes_only = True
        self._index = 0
        self._map_key = ""
        self._side = ""
        self._weapon: str | None = None
        self._health: int | None = None
        self._round_phase: str | None = None
        self._bucket = ("", "")
        self._lock = threading.Lock()

    def observe(self, snapshot: Snapshot | None) -> DeckView:
        with self._lock:
            decision = self._apply_snapshot(snapshot)
            return self._view_locked(decision)

    def view(self) -> DeckView:
        with self._lock:
            decision = self._decision_locked()
            return self._view_locked(decision)

    def cycle(self, delta: int) -> DeckView:
        """Step to another card. Does not show the overlay by itself."""

        with self._lock:
            decision = self._decision_locked()
            cards = self._cards_locked(decision.grenade)
            if cards:
                self._index = (self._index + delta) % len(cards)
            return self._view_locked(decision)

    def toggle(self) -> DeckView:
        """Hide or show. Showing still waits until a grenade is in hand."""

        with self._lock:
            self.hidden = not self.hidden
            return self._view_locked(self._decision_locked())

    def set_enabled(self, enabled: bool) -> None:
        with self._lock:
            self.enabled = enabled

    def set_smokes_only(self, smokes_only: bool) -> None:
        """Kept so older configs still load. The overlay follows the held grenade."""

        with self._lock:
            self.smokes_only = bool(smokes_only)

    def _apply_snapshot(self, snapshot: Snapshot | None) -> OverlayDecision:
        if snapshot is not None:
            if snapshot.map_present and snapshot.map_token:
                self._map_key = snapshot.map_token
            if snapshot.round_present and snapshot.round_phase is not None:
                self._round_phase = snapshot.round_phase
            own = snapshot.own
            if own is not None:
                if own.team in {"T", "CT"}:
                    self._side = own.team.lower()
                if own.health is not None:
                    self._health = own.health
                if own.weapons_seen:
                    self._weapon = own.active_weapon
        return self._decision_locked()

    def _decision_locked(self) -> OverlayDecision:
        return decision_from_snapshot(
            None,
            user_hidden=self.hidden,
            enabled=self.enabled,
            map_key=self._map_key,
            side=self._side,
            active_weapon=self._weapon,
            health=self._health,
            round_phase=self._round_phase,
        )

    def _cards_locked(self, grenade: str) -> list[LineupCard]:
        if not self._map_key or self._side not in {"t", "ct"}:
            return []
        if grenade not in {"smoke", "flash", "molotov", "he"}:
            return []
        cards = list_cards(self.root, self._map_key, self._side) if grenade == "smoke" else []
        if self.pack_dir is not None:
            from suit_o.lineups.pack import pack_cards

            cards.extend(
                pack_cards(
                    self.pack_dir,
                    self._map_key,
                    self._side,
                    grenade=grenade,
                )
            )
        return cards

    def _view_locked(self, decision: OverlayDecision) -> DeckView:
        bucket = (decision.map_key, decision.side, decision.grenade)
        cards = self._cards_locked(decision.grenade)
        if bucket != self._bucket:
            self._bucket = bucket
            self._index = 0
        if not cards:
            self._index = 0
            card = None
        else:
            self._index %= len(cards)
            card = cards[self._index]
        visible = decision.visible and card is not None
        reason = "no-lineups" if decision.visible and card is None else decision.reason
        return DeckView(
            visible=visible,
            reason=reason,
            map_key=decision.map_key,
            side=decision.side,
            index=self._index,
            total=len(cards),
            card=card if visible else None,
            hidden=self.hidden,
        )
