"""Guided Up/Down discovery wizard."""

from __future__ import annotations

import logging
import time
from collections.abc import Callable
from dataclasses import dataclass, field
from enum import Enum

from ndp.discovery.arp import flush_arp_cache, scan_hosts
from ndp.discovery.diff import ScanDiff, confirm_reappearance, diff_snapshots
from ndp.discovery.host import DiscoveredHost, ScanSnapshot

logger = logging.getLogger(__name__)


class WizardPhase(str, Enum):
    IDLE = "idle"
    SCANNING_BASELINE = "scanning_baseline"
    WAIT_UNPLUG = "wait_unplug"
    PREPARE_SECOND_SCAN = "prepare_second_scan"
    SCANNING_AFTER = "scanning_after"
    SHOW_DIFF = "show_diff"
    VERIFY_REPLUG = "verify_replug"
    SCANNING_VERIFY = "scanning_verify"
    DONE = "done"


@dataclass
class DiscoveryConfig:
    disconnect_wait_seconds: float = 8.0
    flush_arp_before_second_scan: bool = True
    verify_replug: bool = True
    countdown_step_seconds: float = 1.0


@dataclass
class UpDownResult:
    baseline: ScanSnapshot
    after: ScanSnapshot
    diff: ScanDiff
    verify: ScanSnapshot | None = None
    confirmed_hosts: list[DiscoveredHost] = field(default_factory=list)
    phase: WizardPhase = WizardPhase.DONE

    def to_dict(self) -> dict[str, object]:
        return {
            "phase": self.phase.value,
            "baseline": self.baseline.to_dict(),
            "after": self.after.to_dict(),
            "diff": self.diff.to_dict(),
            "verify": self.verify.to_dict() if self.verify else None,
            "confirmed_hosts": [host.to_dict() for host in self.confirmed_hosts],
        }


class WizardCancelled(Exception):
    """Raised when the user aborts the discovery wizard."""


PromptFn = Callable[[str], str]
OutputFn = Callable[[str], None]
SleepFn = Callable[[float], None]


CancelFn = Callable[[], bool]


class UpDownWizard:
    def __init__(
        self,
        interface: str,
        config: DiscoveryConfig | None = None,
        prompt: PromptFn | None = None,
        output: OutputFn | None = None,
        sleep: SleepFn | None = None,
        skip_verify: bool = False,
        cancel_check: CancelFn | None = None,
    ) -> None:
        self.interface = interface
        self.config = config or DiscoveryConfig()
        self.prompt = prompt or input
        self.output = output or print
        self.sleep = sleep or time.sleep
        self.skip_verify = skip_verify
        self.cancel_check = cancel_check
        self.phase = WizardPhase.IDLE

    def _check_cancel(self) -> None:
        if self.cancel_check and self.cancel_check():
            raise WizardCancelled()

    def run(self) -> UpDownResult:
        self.phase = WizardPhase.SCANNING_BASELINE
        self._say("Passo 1/5 — Scansione baseline...")
        self._check_cancel()
        baseline = scan_hosts(self.interface)
        self._say(f"  Trovati {baseline.host_count} dispositivi ({baseline.source}).")

        self.phase = WizardPhase.WAIT_UNPLUG
        self._say("Passo 2/5 — Stacca il device, poi ○")
        self._wait_for_user()

        self.phase = WizardPhase.PREPARE_SECOND_SCAN
        self._say("Passo 3/5 — Pulizia ARP...")
        if self.config.flush_arp_before_second_scan:
            self._check_cancel()
            flushed = flush_arp_cache(self.interface)
            if flushed:
                self._say("  Cache ARP svuotata.")
            else:
                self._say("  Cache ARP non svuotata (arp-scan userà comunque probe attivi).")
        self._countdown(self.config.disconnect_wait_seconds)

        self.phase = WizardPhase.SCANNING_AFTER
        self._say("Passo 4/5 — Seconda scansione...")
        self._check_cancel()
        after = scan_hosts(self.interface)
        self._say(f"  Trovati {after.host_count} dispositivi ({after.source}).")

        diff = diff_snapshots(baseline, after)
        self.phase = WizardPhase.SHOW_DIFF
        verify_snapshot: ScanSnapshot | None = None
        confirmed_hosts: list[DiscoveredHost] = []

        if self.config.verify_replug and not self.skip_verify:
            self.phase = WizardPhase.VERIFY_REPLUG
            self._say("Passo 5/5 — Ricollega, ○ o ▶ skip")
            answer = self._wait_for_user(allow_skip=True)
            if answer != "s":
                self.phase = WizardPhase.SCANNING_VERIFY
                self._say("Verifica in corso...")
                self._check_cancel()
                verify_snapshot = scan_hosts(self.interface)
                confirmed_hosts = confirm_reappearance(diff.offline_hosts, verify_snapshot)
        else:
            self._say("\nPasso 5/5 — Verifica ricollegamento saltata.")

        self.phase = WizardPhase.DONE
        return UpDownResult(
            baseline=baseline,
            after=after,
            diff=diff,
            verify=verify_snapshot,
            confirmed_hosts=confirmed_hosts,
            phase=self.phase,
        )

    def _say(self, message: str) -> None:
        self.output(message)

    def _wait_for_user(self, allow_skip: bool = False) -> str:
        while True:
            self._check_cancel()
            answer = self.prompt("> ").strip().lower()
            if answer == "" or not allow_skip:
                return answer
            if answer in {"s", "skip", "n", "no"}:
                return "s"
            self._say("○ continua" + (" | ▶ skip" if allow_skip else ""))

    def _countdown(self, total_seconds: float) -> None:
        remaining = max(1, int(total_seconds))
        for second in range(remaining, 0, -1):
            self._check_cancel()
            self._say(f"Attesa {second}s...")
            self.sleep(self.config.countdown_step_seconds)
