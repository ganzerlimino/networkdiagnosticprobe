"""Pygame framebuffer UI for NDP."""

from __future__ import annotations

import logging
import os
import queue
import threading
import time
from pathlib import Path
from typing import TYPE_CHECKING

from ndp import __version__
from ndp.core.config import NdpConfig
from ndp.core.engine import ProbeEngine
from ndp.core.ping_state import PingSuiteState
from ndp.core.state import ProbeState
from ndp.ui.backlight import enable_backlight
from ndp.ui.buttons import ButtonAction
from ndp.ui.input import create_ui_input
from ndp.ui.discovery_session import DiscoveryUISession
from ndp.ui.framebuffer import RawFramebuffer
from ndp.ui.layout import content_text_x, content_width, content_x_offset, draw_button_hints
from ndp.ui.screens import (
    ScreenId,
    lines_for_screen,
    next_screen,
    screen_ids_for_mode,
    screen_title,
    shutdown_lines,
    shutdown_palette,
    shutdown_phase_message,
    tft_text,
)
from ndp.ui.splash import draw_splash
from ndp.ping.service import read_adhoc_host, run_ping_suite

if TYPE_CHECKING:
    import pygame

logger = logging.getLogger(__name__)

COLOR_BG = (12, 18, 32)
COLOR_HEADER = (24, 36, 64)
COLOR_TEXT = (235, 240, 255)
COLOR_MUTED = (140, 155, 180)
COLOR_ACCENT = (80, 200, 120)


def _apply_tft_palette(config: NdpConfig) -> None:
    global COLOR_BG, COLOR_HEADER, COLOR_TEXT, COLOR_MUTED, COLOR_ACCENT
    from ndp.locale.loader import tft_palette

    palette = tft_palette(config.ui_theme)
    COLOR_BG = palette["bg"]
    COLOR_HEADER = palette["header"]
    COLOR_TEXT = palette["text"]
    COLOR_MUTED = palette["muted"]
    COLOR_ACCENT = palette["accent"]


def _configure_pygame_env(config: NdpConfig, use_dummy: bool) -> None:
    driver = "dummy" if use_dummy else config.ui_sdl_driver
    os.environ["SDL_VIDEODRIVER"] = driver
    os.environ["SDL_FBDEV"] = config.ui_framebuffer
    os.environ["SDL_MOUSE"] = "0"
    os.environ["PYGAME_HIDE_SUPPORT_PROMPT"] = "1"


def _prefer_raw_backend(config: NdpConfig) -> bool:
    if config.ui_backend == "raw":
        return True
    if config.ui_backend == "sdl":
        return False
    if os.environ.get("SDL_VIDEODRIVER") == "dummy":
        return True
    return Path(config.ui_framebuffer).exists()


def _load_font(size: int) -> pygame.font.Font:
    import pygame

    for name in ("dejavusans", "dejavusansmono", "liberationsans", "freesans"):
        path = pygame.font.match_font(name)
        if path:
            return pygame.font.Font(path, size)
    return pygame.font.Font(None, size)


def _init_display(config: NdpConfig) -> tuple[pygame.Surface, RawFramebuffer | None]:
    """Return pygame surface and optional raw framebuffer for blitting."""
    import pygame

    errors: list[str] = []

    if not _prefer_raw_backend(config):
        _configure_pygame_env(config, use_dummy=False)
        try:
            if pygame.get_init():
                pygame.quit()
            pygame.init()
            pygame.font.init()
            screen = pygame.display.set_mode(
                (config.ui_width, config.ui_height),
                pygame.FULLSCREEN,
            )
            pygame.mouse.set_visible(False)
            logger.info("UI using SDL driver %s", os.environ.get("SDL_VIDEODRIVER"))
            return screen, None
        except pygame.error as exc:
            errors.append(f"sdl:{exc}")
            pygame.quit()

    _configure_pygame_env(config, use_dummy=True)
    if pygame.get_init():
        pygame.quit()
    pygame.init()
    pygame.font.init()
    surface = pygame.Surface((config.ui_width, config.ui_height))
    raw_fb = RawFramebuffer(
        config.ui_framebuffer,
        config.ui_width,
        config.ui_height,
    )
    logger.info(
        "UI using offscreen pygame + raw framebuffer %s (%sx%s, stride=%s)",
        config.ui_framebuffer,
        raw_fb.width,
        raw_fb.height,
        raw_fb.line_length,
    )
    if errors:
        logger.warning("SDL display unavailable (%s); raw fallback active", "; ".join(errors))
    return surface, raw_fb


def _blit_frame(
    screen: pygame.Surface,
    raw_fb: RawFramebuffer | None,
) -> None:
    if raw_fb is not None:
        raw_fb.blit_surface(screen)
    else:
        import pygame

        pygame.display.flip()


class ProbeUI:
    def __init__(self, config: NdpConfig) -> None:
        self.config = config
        self.engine = ProbeEngine(config)
        self._lock = threading.Lock()
        self._stop = threading.Event()
        self._force_refresh = threading.Event()
        self._screen = ScreenId.HOME
        self._state = ProbeState(interface=config.interface)
        self._redraw_now = threading.Event()
        self._button_queue: queue.SimpleQueue[ButtonAction] = queue.SimpleQueue()
        self._interactive = config.ui_input != "none"
        self._display_screens = screen_ids_for_mode(self._interactive)
        self._discovery = (
            DiscoveryUISession(config, on_activity=self._request_redraw)
            if self._interactive
            else None
        )
        self._input_device = create_ui_input(config) if self._interactive else None
        self._web_thread: threading.Thread | None = None
        self._ping_thread: threading.Thread | None = None
        self._last_cycle_at = time.monotonic()
        self._state.ping.adhoc_host = read_adhoc_host(Path(config.ping_adhoc_path))
        _apply_tft_palette(config)

    @property
    def display_only(self) -> bool:
        return not self._interactive

    def get_state(self) -> ProbeState:
        with self._lock:
            return self._state

    def update_ping_state(self, suite: PingSuiteState) -> None:
        with self._lock:
            self._state.ping = suite
        self._request_redraw()

    def refresh_adhoc_host(self) -> None:
        with self._lock:
            self._state.ping.adhoc_host = read_adhoc_host(Path(self.config.ping_adhoc_path))
        self._request_redraw()

    def apply_mndp_device(self, device: dict[str, object]) -> None:
        with self._lock:
            self.engine.apply_mndp_device(device)
            self._state.neighbor = self.engine.state.neighbor
        self._request_redraw()

    def _request_redraw(self) -> None:
        self._redraw_now.set()

    def _enqueue_button(self, action: ButtonAction) -> None:
        self._button_queue.put(action)

    def _drain_button_queue(self) -> None:
        while True:
            try:
                action = self._button_queue.get_nowait()
            except queue.Empty:
                break
            self._on_button(action)

    def _input_loop(self) -> None:
        if self._input_device is None:
            return
        poll_interval = 1.0 / max(50, self.config.ui_button_poll_hz)
        while not self._stop.is_set():
            self._input_device.poll(self._enqueue_button)
            time.sleep(poll_interval)

    def _engine_loop(self) -> None:
        while not self._stop.is_set():
            if self._force_refresh.is_set():
                self._force_refresh.clear()
            with self._lock:
                self._state = self.engine.refresh()
                self._state.ping.adhoc_host = read_adhoc_host(
                    Path(self.config.ping_adhoc_path)
                )
            time.sleep(self.engine.poll_interval())

    def _maybe_auto_cycle(self, now: float) -> None:
        interval = self.config.ui_auto_cycle_seconds
        if interval <= 0 or not self.display_only:
            return
        if now - self._last_cycle_at < interval:
            return
        self._last_cycle_at = now
        previous = self._screen
        self._screen = next_screen(
            self._screen,
            1,
            screens=self._display_screens,
        )
        if self._screen != previous:
            logger.debug("UI auto-cycle -> %s", self._screen.name)

    def _on_button(self, action: ButtonAction) -> None:
        if not self._interactive or self._discovery is None:
            return

        if self._screen == ScreenId.DISCOVER:
            if action == ButtonAction.SELECT:
                self._discovery.on_select()
                self._redraw_now.set()
                return
            if action == ButtonAction.NEXT and self._discovery.on_next_skip():
                self._redraw_now.set()
                return
            if action == ButtonAction.PREVIOUS:
                if self._discovery.running:
                    self._discovery.cancel()
                else:
                    self._screen = next_screen(self._screen, -1, screens=self._display_screens)
                    logger.info("UI screen -> %s", self._screen.name)
                self._redraw_now.set()
                return
            if action == ButtonAction.NEXT:
                if not self._discovery.is_idle():
                    self._redraw_now.set()
                    return
                self._screen = next_screen(self._screen, 1, screens=self._display_screens)
                logger.info("UI screen -> %s", self._screen.name)
                self._redraw_now.set()
                return

        if self._screen == ScreenId.PING and action == ButtonAction.SELECT:
            self._start_ping_suite()
            self._redraw_now.set()
            return

        previous = self._screen
        if action == ButtonAction.PREVIOUS:
            self._screen = next_screen(self._screen, -1, screens=self._display_screens)
        elif action == ButtonAction.NEXT:
            self._screen = next_screen(self._screen, 1, screens=self._display_screens)
        elif action == ButtonAction.SELECT:
            self._force_refresh.set()

        if self._screen != previous:
            logger.info("UI screen -> %s", self._screen.name)

        self._redraw_now.set()

    def _start_ping_suite(self) -> None:
        if self._ping_thread is not None and self._ping_thread.is_alive():
            return

        with self._lock:
            self._state.ping.running = True
            self._state.ping.message = tft_text(self.config, "tft.ping_running")
            gateway = self._state.ip.gateway
            self._state.ping.adhoc_host = read_adhoc_host(Path(self.config.ping_adhoc_path))

        def _worker() -> None:
            suite = run_ping_suite(
                self.config,
                gateway=gateway,
                adhoc_path=Path(self.config.ping_adhoc_path),
            )
            self.update_ping_state(suite)

        self._ping_thread = threading.Thread(target=_worker, daemon=True, name="ndp-ping")
        self._ping_thread.start()

    def _run_startup(
        self,
        screen: pygame.Surface,
        raw_fb: RawFramebuffer | None,
        title_font: pygame.font.Font,
        body_font: pygame.font.Font,
        hint_font: pygame.font.Font,
    ) -> None:
        if not self.config.ui_splash_enabled and not self.config.ui_warmup_on_start:
            return

        warmup_done = threading.Event()
        warmup_error: list[str] = []

        def _warmup() -> None:
            try:
                if self.config.ui_warmup_on_start:
                    with self._lock:
                        self._state = self.engine.refresh()
                    for sid in self._display_screens:
                        for line in lines_for_screen(
                            sid,
                            self._state,
                            interactive=self._interactive,
                            web_port=self.config.web_port,
                        ):
                            body_font.render(line, True, COLOR_TEXT)
                warmup_done.set()
            except Exception as exc:  # pragma: no cover
                warmup_error.append(str(exc))
                warmup_done.set()

        worker = threading.Thread(target=_warmup, daemon=True, name="ndp-warmup")
        worker.start()

        splash_start = time.monotonic()
        status = tft_text(self.config, "tft.splash_loading")
        while not self._stop.is_set():
            elapsed = time.monotonic() - splash_start
            if warmup_done.is_set():
                status = (
                    tft_text(self.config, "tft.splash_ready")
                    if not warmup_error
                    else tft_text(self.config, "tft.splash_init_error")
                )
            elif elapsed > 0.5:
                status = tft_text(self.config, "tft.splash_collecting")

            if self.config.ui_splash_enabled:
                draw_splash(
                    screen,
                    self.config,
                    title_font=title_font,
                    body_font=body_font,
                    version=__version__,
                    status_line=status,
                )
                _blit_frame(screen, raw_fb)

            ready = warmup_done.is_set() and elapsed >= self.config.ui_splash_min_seconds
            if ready:
                break
            time.sleep(0.05)

        if warmup_error:
            logger.warning("Warmup error: %s", warmup_error[0])

    def run(self) -> int:
        import pygame

        if self.config.web_enabled:
            from ndp.web.server import resolve_config_path, start_web_server

            config_path = self.config.source_path or resolve_config_path()
            self._web_thread = start_web_server(
                self.config,
                config_path,
                self.get_state,
                on_ping_complete=self.update_ping_state,
                on_adhoc_changed=self.refresh_adhoc_host,
                on_mndp_connected=self.apply_mndp_device,
            )

        self._hotspot_stop = threading.Event()
        if self.config.wifi_hotspot_enabled:
            from ndp.network.hotspot import maintain_hotspot, start_hotspot_watchdog

            maintain_hotspot(self.config)
            start_hotspot_watchdog(self.config, self._hotspot_stop)

        if self.config.ui_backlight_enabled:
            enable_backlight(self.config.ui_backlight_gpio)

        screen, raw_fb = _init_display(self.config)

        title_font = _load_font(self.config.ui_font_size + 4)
        body_font = _load_font(self.config.ui_font_size)
        hint_font = _load_font(max(12, self.config.ui_font_size - 2))

        mode = "display-only" if self.display_only else f"input={self.config.ui_input}"
        logger.info("TFT UI started (%s, auto-cycle=%ss)", mode, self.config.ui_auto_cycle_seconds)

        self._run_startup(screen, raw_fb, title_font, body_font, hint_font)

        worker = threading.Thread(target=self._engine_loop, daemon=True, name="ndp-engine")
        worker.start()

        try:
            if self._input_device is not None:
                with self._input_device:
                    input_thread = threading.Thread(
                        target=self._input_loop,
                        daemon=True,
                        name="ndp-input",
                    )
                    input_thread.start()
                    self._main_loop(screen, raw_fb, title_font, body_font, hint_font)
            else:
                self._main_loop(screen, raw_fb, title_font, body_font, hint_font)
        finally:
            self._hotspot_stop.set()
            if raw_fb is not None:
                raw_fb.close()
            pygame.quit()

        return 0

    def _main_loop(
        self,
        screen: pygame.Surface,
        raw_fb: RawFramebuffer | None,
        title_font: pygame.font.Font,
        body_font: pygame.font.Font,
        hint_font: pygame.font.Font,
    ) -> None:
        import pygame

        last_frame = time.monotonic()
        frame_interval = 1.0 / max(1, self.config.ui_fps)

        while not self._stop.is_set():
            for event in pygame.event.get():
                if event.type == pygame.QUIT:
                    self._stop.set()

            if self._interactive:
                self._drain_button_queue()

            now = time.monotonic()
            self._maybe_auto_cycle(now)

            if self._redraw_now.is_set() or (now - last_frame) >= frame_interval:
                self._redraw_now.clear()

                with self._lock:
                    state = self._state
                    current = self._screen

                self._draw(screen, title_font, body_font, hint_font, current, state)
                _blit_frame(screen, raw_fb)
                last_frame = now
            else:
                time.sleep(0.002)

    def stop(self) -> None:
        self._stop.set()

    def _draw(
        self,
        surface: pygame.Surface,
        title_font: pygame.font.Font,
        body_font: pygame.font.Font,
        hint_font: pygame.font.Font,
        screen_id: ScreenId,
        state: ProbeState,
    ) -> None:
        import pygame

        surface.fill(COLOR_BG)
        margin = self.config.ui_content_margin_side
        edge = self.config.ui_hint_edge
        text_gap = self.config.ui_content_text_gap
        text_width = content_width(self.config.ui_width, edge, margin)
        content_x = content_x_offset(edge, margin)
        text_x = content_text_x(edge, margin, text_gap)

        from ndp.system.shutdown import is_shutting_down, shutdown_snapshot

        if is_shutting_down():
            palette = shutdown_palette()
            surface.fill(palette["bg"])
            pygame.draw.rect(surface, palette["header"], pygame.Rect(0, 0, self.config.ui_width, 38))
            stripe_h = 6
            pygame.draw.rect(
                surface,
                palette["stripe"],
                pygame.Rect(0, self.config.ui_height - stripe_h, self.config.ui_width, stripe_h),
            )
            pygame.draw.rect(
                surface,
                palette["accent"],
                pygame.Rect(0, 0, self.config.ui_width, 3),
            )
            title = title_font.render(tft_text(self.config, "tft.shutdown_title"), True, palette["accent"])
            surface.blit(title, (text_x, 8))
            phase = str(shutdown_snapshot().get("phase", "in_progress"))
            message = shutdown_phase_message(phase, self.config)
            y = 44
            line_step = self.config.ui_font_size + self.config.ui_line_spacing
            for index, line in enumerate(shutdown_lines(message, self.config)):
                if index == 0:
                    continue
                if not line:
                    y += line_step // 2
                    continue
                color = palette["accent"] if index >= 3 else palette["text"]
                rendered = body_font.render(line, True, color)
                surface.blit(rendered, (text_x, y))
                y += line_step
            return

        header = pygame.Rect(content_x, 0, text_width, 34)
        pygame.draw.rect(surface, COLOR_HEADER, header)

        title = title_font.render(screen_title(screen_id, self.config), True, COLOR_ACCENT)
        surface.blit(title, (text_x, 6))

        dots = self._screen_dots(screen_id)
        dots_surface = hint_font.render(dots, True, COLOR_MUTED)
        surface.blit(
            dots_surface,
            (content_x + text_width - dots_surface.get_width() - 8, 10),
        )

        if (
            self._interactive
            and screen_id == ScreenId.DISCOVER
            and self._discovery is not None
        ):
            body_lines = self._discovery.display_lines()
        else:
            body_lines = lines_for_screen(
                screen_id,
                state,
                interactive=self._interactive,
                web_port=self.config.web_port,
                config=self.config,
            )

        y = 42
        line_step = self.config.ui_font_size + self.config.ui_line_spacing
        for line in body_lines:
            rendered = body_font.render(line, True, COLOR_TEXT)
            if rendered.get_width() > text_width - text_gap - 20:
                line = line[:28] + "…"
                rendered = body_font.render(line, True, COLOR_TEXT)
            surface.blit(rendered, (text_x, y))
            y += line_step

        if self._interactive:
            draw_button_hints(
                surface,
                hint_font,
                edge=self.config.ui_hint_edge,
                width=self.config.ui_width,
                height=self.config.ui_height,
                color=COLOR_MUTED,
                margin=margin,
                y_offset=self.config.ui_hint_y_offset,
            )
        elif self.config.web_enabled and self.config.wifi_hotspot_enabled:
            from ndp.network.hotspot import hotspot_footer

            footer = hotspot_footer(self.config)
            footer_warn = (255, 180, 60)
            footer_y = self.config.ui_height - 4
            for index, line in enumerate(reversed(footer.lines)):
                is_client_line = index == 0
                color = footer_warn if (footer.warn_no_client and is_client_line) else COLOR_MUTED
                rendered = hint_font.render(line, True, color)
                footer_y -= rendered.get_height()
                surface.blit(rendered, (text_x, footer_y))

    def _screen_dots(self, active: ScreenId) -> str:
        parts = []
        for screen in self._display_screens:
            parts.append("*" if screen == active else "-")
        return " ".join(parts)


def run_ui(config: NdpConfig) -> int:
    import signal

    from ndp.network.hotspot import stop_hotspot
    from ndp.system.shutdown import configure_shutdown_hooks

    configure_shutdown_hooks(stop_hotspot=lambda: stop_hotspot(config))
    ui = ProbeUI(config)

    def _handle_signal(_signum: int, _frame: object) -> None:
        logger.info("UI shutdown requested")
        ui.stop()

    signal.signal(signal.SIGTERM, _handle_signal)
    signal.signal(signal.SIGINT, _handle_signal)
    return ui.run()
