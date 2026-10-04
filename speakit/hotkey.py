"""Globale Taste/Kombi. Die Ausloeser-Taste wird geschluckt, Modifier laufen durch."""
import logging
import threading
import time

import keyboard

MOD_GROUPS = {
    "ctrl": ("ctrl", "left ctrl", "right ctrl"),
    "alt": ("alt", "left alt", "right alt"),
    "shift": ("shift", "left shift", "right shift"),
    "windows": ("windows", "left windows", "right windows"),
}
ALIAS = {n: g for g, names in MOD_GROUPS.items() for n in names}


def normalize(name: str) -> str:
    name = (name or "").lower()
    return ALIAS.get(name, name)


def _scans(name):
    return frozenset(keyboard.key_to_scan_codes(name))


ALL_MOD_SCANS = frozenset().union(*(_scans(g) for g in MOD_GROUPS))


class HotkeyManager:
    def __init__(self, on_press, on_release, on_cancel=None):
        self.on_press = on_press
        self.on_release = on_release
        self.on_cancel = on_cancel
        self.cancel_armed = lambda: False
        self.injecting = False
        self.names = []
        self.mod_sets = []
        self.trigger = frozenset()
        self.mod_only = False
        self.down = set()
        self.swallow_up = set()
        self.active = False
        self.capture = None  # callback(names) waehrend Tastenaufnahme
        self._cap_keys = []
        self._hook = None
        self._lock = threading.Lock()

    # ---- Konfiguration ----
    def set_hotkey(self, names):
        names = [normalize(n) for n in names]
        if not names:
            raise ValueError("leere Taste")
        sets = [_scans(n) for n in names]  # wirft ValueError bei unbekannter Taste
        mods = [s for n, s in zip(names, sets) if n in MOD_GROUPS]
        non_mods = [s for n, s in zip(names, sets) if n not in MOD_GROUPS]
        with self._lock:
            self.names = names
            self.mod_only = not non_mods
            if self.mod_only:
                self.mod_sets, self.trigger = mods, frozenset()
            else:
                self.mod_sets, self.trigger = mods, non_mods[-1]
            self.reset_state()

    def reset_state(self):
        self.down.clear()
        self.swallow_up.clear()
        self.active = False

    def start(self):
        self.stop()
        self._hook = keyboard.hook(self._handle, suppress=True)

    def stop(self):
        if self._hook is not None:
            try:
                keyboard.unhook(self._hook)
            except Exception:
                pass
            self._hook = None

    def reinstall(self):
        logging.info("Tastatur-Hook neu installiert")
        self.reset_state()
        self.start()

    def start_capture(self, cb):
        self._cap_keys = []
        self.capture = cb

    # ---- Event-Verarbeitung (muss schnell sein) ----
    def _fire(self, fn):
        if fn:
            threading.Thread(target=fn, daemon=True).start()

    def _handle(self, e):
        try:
            return self._process(e)
        except Exception:
            logging.exception("Hotkey-Handler")
            return True

    def _process(self, e):
        if self.injecting:
            return True
        sc, is_down = e.scan_code, e.event_type == "down"
        if self.capture:
            return self._capture(e, sc, is_down)
        if is_down:
            self.down.add(sc)
        else:
            self.down.discard(sc)

        if is_down and sc == 1 and self.on_cancel and self.cancel_armed():
            self._fire(self.on_cancel)

        if self.mod_only:
            return self._process_mod_only(sc, is_down)

        if is_down:
            if sc in self.swallow_up:  # Auto-Repeat
                return False
            if sc in self.trigger and self._mods_match():
                self.swallow_up.add(sc)
                self.active = True
                self._fire(self.on_press)
                return False
            return True
        # Taste losgelassen
        if sc in self.swallow_up:
            self.swallow_up.discard(sc)
            if self.active:
                self.active = False
                self._fire(self.on_release)
            return False
        if self.active and any(sc in m for m in self.mod_sets):
            self.active = False
            self._fire(self.on_release)
        return True

    def _mods_match(self):
        required = frozenset().union(*self.mod_sets) if self.mod_sets else frozenset()
        if (self.down & ALL_MOD_SCANS) - required:
            return False
        return all(self.down & m for m in self.mod_sets)

    def _process_mod_only(self, sc, is_down):
        if not any(sc in m for m in self.mod_sets):
            return True
        if is_down and not self.active and all(self.down & m for m in self.mod_sets):
            self.active = True
            self._fire(self.on_press)
        elif not is_down and self.active:
            self.active = False
            self._fire(self.on_release)
        return True

    def _capture(self, e, sc, is_down):
        name = normalize(e.name)
        if is_down:
            if name not in self._cap_keys:
                self._cap_keys.append(name)
            return False
        cb, keys = self.capture, self._cap_keys
        self.capture = None
        self._cap_keys = []
        # Modifier zuerst, Ausloeser zuletzt
        keys.sort(key=lambda n: 0 if n in MOD_GROUPS else 1)
        self._fire(lambda: cb(keys))
        return False

    # ---- Simulierte Tasten ----
    def send(self, combo):
        self.injecting = True
        try:
            keyboard.send(combo)
            time.sleep(0.08)
        finally:
            self.injecting = False

    def wait_released(self, timeout=1.5):
        end = time.time() + timeout
        while time.time() < end and (self.active or (self.down & ALL_MOD_SCANS)):
            time.sleep(0.02)


def pretty(names):
    return " + ".join(n.capitalize() if len(n) > 1 else n.upper() for n in names)
