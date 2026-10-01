"""Shared UI context: bridge, session (user/role), config, DB, messages."""

import os
import time
from typing import Optional

from belt_marking_control.core.config import ControlConfig, from_dict
from belt_marking_control.core.db import ProductionDb, ROLE_LEVEL
import yaml

from .i18n import tr


def load_control_config(config_path: str) -> ControlConfig:
    if config_path and os.path.exists(config_path):
        with open(config_path) as fh:
            data = yaml.safe_load(fh) or {}
        return from_dict({k: data[k] for k in ('machine', 'laser', 'knife', 'zair')
                          if k in data})
    return ControlConfig()


class Session:
    """Logged-in user, role and auto-logout."""

    def __init__(self, db: ProductionDb, auto_logout_s: float = 600.0):
        self.db = db
        self.user: Optional[str] = None
        self.role: Optional[str] = None
        self.auto_logout_s = auto_logout_s
        self.last_activity = time.monotonic()

    def login(self, pin: str) -> bool:
        u = self.db.check_pin(pin)
        if u is None:
            self.db.audit('', 'login_failed', '')
            return False
        self.user, self.role = u['name'], u['role']
        self.touch()
        self.db.audit(self.user, 'login', self.role)
        return True

    def logout(self):
        if self.user:
            self.db.audit(self.user, 'logout', '')
        self.user, self.role = None, None

    def touch(self):
        self.last_activity = time.monotonic()

    def expired(self) -> bool:
        return self.user is not None and \
            time.monotonic() - self.last_activity > self.auto_logout_s

    def has(self, role: str) -> bool:
        return self.role is not None and ROLE_LEVEL[self.role] >= ROLE_LEVEL[role]


class Context:
    """Shared objects for all screens: ROS bridge, DB, config, session."""

    def __init__(self, bridge, db: ProductionDb, cfg: ControlConfig, use_sim: bool,
                 config_path: str = ''):
        self.bridge = bridge
        self.db = db
        self.cfg = cfg
        self.use_sim = use_sim
        self.config_path = config_path
        self.session = Session(db)
        self.state = None           # last MachineState
        self.io = None              # last IoStatus
        self.window = None          # MainWindow (set by the app)

    def user(self) -> str:
        return self.session.user or ''

    def require(self, role: str) -> bool:
        if self.session.has(role):
            self.session.touch()
            return True
        if self.window is not None:
            self.window.login_dialog(role)
            if self.session.has(role):
                return True
            self.window.message(tr('msg.need_role', role=role))
        return False

    def message(self, text: str, error: bool = False):
        if self.window is not None:
            self.window.message(text, error)
