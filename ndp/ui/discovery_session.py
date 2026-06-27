"""UI-driven Up/Down discovery session."""

from __future__ import annotations

import logging
import threading
from collections.abc import Callable
from dataclasses import dataclass, field

from ndp.core.config import NdpConfig
from ndp.discovery.console import compact_diff_lines
from ndp.discovery.wizard import (
    DiscoveryConfig,
    UpDownResult,
    UpDownWizard,
    WizardCancelled,
    WizardPhase,
)

logger = logging.getLogger(__name__)

RedrawFn = Callable[[], None]


@dataclass
class DiscoveryUISession:
    config: NdpConfig
    on_activity: RedrawFn | None = None
    _lines: list[str] = field(default_factory=list)
    _phase: WizardPhase = WizardPhase.IDLE
    _running: bool = False
    _waiting_for_user: bool = False
    _waiting_allow_skip: bool = False
    _countdown: int | None = None
    _result: UpDownResult | None = None
    _error: str | None = None
    _cancel: threading.Event = field(default_factory=threading.Event)
    _prompt_answer: threading.Event = field(default_factory=threading.Event)
    _skip_answer: bool = False
    _thread: threading.Thread | None = None
    _wizard: UpDownWizard | None = None
    _lock: threading.Lock = field(default_factory=threading.Lock)

    @property
    def phase(self) -> WizardPhase:
        return self._phase

    @property
    def running(self) -> bool:
        return self._running

    @property
    def result(self) -> UpDownResult | None:
        return self._result

    def is_idle(self) -> bool:
        if self._running:
            return False
        if self._thread is not None and self._thread.is_alive():
            return False
        return True

    def _notify(self) -> None:
        if self.on_activity is not None:
            self.on_activity()

    def start(self) -> None:
        if not self.is_idle():
            return
        self._cancel.clear()
        self._result = None
        self._error = None
        self._lines.clear()
        self._phase = WizardPhase.SCANNING_BASELINE
        self._running = True
        self._lines.append("Avvio wizard...")
        self._notify()
        self._thread = threading.Thread(target=self._run, daemon=True, name="ndp-discovery")
        self._thread.start()

    def cancel(self) -> None:
        self._cancel.set()
        self._prompt_answer.set()
        self._notify()

    def reset(self) -> None:
        self.cancel()
        if self._thread is not None:
            self._thread.join(timeout=0.5)
        self._thread = None
        self._running = False
        self._result = None
        self._error = None
        self._lines.clear()
        self._phase = WizardPhase.IDLE
        self._countdown = None
        self._cancel.clear()
        self._prompt_answer.clear()
        self._notify()

    def on_select(self) -> bool:
        with self._lock:
            if self._waiting_for_user:
                self._skip_answer = False
                self._prompt_answer.set()
                return True
        if self.is_idle():
            self.start()
            return True
        if self._phase == WizardPhase.DONE:
            self.reset()
            self.start()
            return True
        return True

    def on_next_skip(self) -> bool:
        with self._lock:
            if self._waiting_for_user and self._waiting_allow_skip:
                self._skip_answer = True
                self._prompt_answer.set()
                return True
        return False

    def display_lines(self) -> list[str]:
        with self._lock:
            if self.is_idle() and self._phase != WizardPhase.DONE:
                return [
                    "Up/Down scan",
                    "○ avvia wizard",
                    "",
                    "Stacca 1 device",
                    "per trovarlo in rete",
                ]
            if self._error:
                return ["Errore:", self._error[:28], "", "○ riprova"]
            if self._phase == WizardPhase.DONE and self._result is not None:
                return compact_diff_lines(self._result.diff)[:7]
            lines = list(self._lines[-6:])
            if self._countdown is not None:
                lines.append(f"Attesa {self._countdown}s")
            if self._waiting_for_user:
                hint = "○ continua"
                if self._waiting_allow_skip:
                    hint += "  ▶ skip"
                lines.append(hint)
            elif self._running:
                lines.append("Scansione...")
            return lines[:7]

    def _run(self) -> None:
        discovery = DiscoveryConfig(
            disconnect_wait_seconds=self.config.discovery_disconnect_wait_seconds,
            flush_arp_before_second_scan=self.config.discovery_flush_arp,
            verify_replug=self.config.discovery_verify_replug,
            countdown_step_seconds=1.0,
        )
        wizard = UpDownWizard(
            interface=self.config.interface,
            config=discovery,
            prompt=self._ui_prompt,
            output=self._ui_output,
            sleep=self._ui_sleep,
            cancel_check=self._cancel.is_set,
        )
        self._wizard = wizard
        try:
            result = wizard.run()
            with self._lock:
                self._result = result
                self._phase = WizardPhase.DONE
        except WizardCancelled:
            with self._lock:
                self._error = None
                self._lines.append("Annullato.")
                self._phase = WizardPhase.IDLE
        except Exception as exc:  # pragma: no cover - defensive on device
            logger.exception("Discovery wizard failed")
            with self._lock:
                self._error = str(exc)
                self._phase = WizardPhase.IDLE
        finally:
            self._wizard = None
            self._running = False
            self._waiting_for_user = False
            self._countdown = None
            self._thread = None
            self._notify()

    def _ui_output(self, message: str) -> None:
        line = message.strip()
        if not line:
            return
        with self._lock:
            if self._wizard is not None:
                self._phase = self._wizard.phase
            self._lines.append(line[:32])
            if len(self._lines) > 12:
                self._lines = self._lines[-12:]
        self._notify()

    def _ui_prompt(self, _message: str) -> str:
        with self._lock:
            if self._wizard is not None:
                self._phase = self._wizard.phase
            self._waiting_for_user = True
            self._waiting_allow_skip = self._phase == WizardPhase.VERIFY_REPLUG
            self._prompt_answer.clear()
        self._notify()
        self._prompt_answer.wait()
        with self._lock:
            self._waiting_for_user = False
            self._waiting_allow_skip = False
            if self._skip_answer:
                self._skip_answer = False
                return "s"
        return ""

    def _ui_sleep(self, seconds: float) -> None:
        remaining = max(1, int(seconds))
        for second in range(remaining, 0, -1):
            if self._cancel.is_set():
                raise WizardCancelled()
            with self._lock:
                self._countdown = second
            self._notify()
            self._prompt_answer.wait(timeout=1.0)
            self._prompt_answer.clear()
        with self._lock:
            self._countdown = None
        self._notify()
