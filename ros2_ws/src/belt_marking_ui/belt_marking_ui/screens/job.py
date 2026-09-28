"""Job setup and recipe screens. Validation uses the controller's own rules/limits."""

import datetime

from belt_marking_control.core.job import (CutMode, Job, job_to_msg, LaserDone, Station,
                                           validate)
from PyQt5.QtWidgets import (QButtonGroup, QCheckBox, QGridLayout, QHBoxLayout,
                             QInputDialog, QLabel, QListWidget, QMessageBox, QPushButton,
                             QScrollArea, QVBoxLayout, QWidget)

from ..i18n import tr
from ..widgets import big_button, NumField

CUT_KEYS = [(CutMode.NONE, 'cut.none'), (CutMode.EVERY, 'cut.every'),
            (CutMode.EVERY_N, 'cut.every_n'), (CutMode.END, 'cut.end')]
DONE_KEYS = [(LaserDone.CONFIG, 'done.config'), (LaserDone.SIGNAL, 'done.signal'),
             (LaserDone.TIMED, 'done.timed')]


def default_job(cfg) -> Job:
    lz = cfg.laser
    return Job(job_id=datetime.datetime.now().strftime('JOB-%Y%m%d-%H%M'),
               belt_width_mm=25.0, quantity=10, pitch_mm=60.0, mark_length_mm=40.0,
               lead_mm=10.0, cut_mode=CutMode.EVERY, laser_time_s=lz.marking_time_default_s,
               settle_s=cfg.machine.settle_default_s,
               feed_speed_mm_s=cfg.machine.feed_speed_default_mm_s,
               stations=[Station(bool(lz.station_enabled[i]), float(lz.station_offsets_mm[i]),
                                 float(lz.station_delays_s[i]))
                         for i in range(lz.num_stations)])


class JobScreen(QWidget):

    def __init__(self, ctx):
        super().__init__()
        self.ctx = ctx
        cfg, m = ctx.cfg, ctx.cfg.machine
        self.job = default_job(cfg)
        outer = QVBoxLayout(self)
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        body = QWidget()
        grid = QGridLayout(body)
        scroll.setWidget(body)
        outer.addWidget(scroll, 1)
        self.fields = {}
        row = 0

        def label(key):
            lb = QLabel(tr(key))
            lb.setWordWrap(True)
            return lb

        self.job_id_btn = QPushButton(self.job.job_id)
        self.job_id_btn.clicked.connect(self._edit_job_id)
        grid.addWidget(label('job.job_id'), row, 0)
        grid.addWidget(self.job_id_btn, row, 1, 1, 3)
        row += 1
        specs = [  # key, min, max, decimals
            ('belt_width_mm', m.belt_width_min_mm, m.belt_width_max_mm, 1),
            ('quantity', 1, m.quantity_max, 0),
            ('pitch_mm', m.pitch_min_mm, m.pitch_max_mm, 2),
            ('mark_length_mm', 0.1, cfg.laser.field_length_mm, 2),
            ('lead_mm', 0.0, m.pitch_max_mm, 2),
            ('laser_time_s', 0.05, 600.0, 2),
            ('settle_s', 0.0, 10.0, 2),
            ('post_mark_delay_s', 0.0, 60.0, 2),
            ('feed_speed_mm_s', 0.5, m.feed_speed_max_mm_s, 1),
            ('cut_every_n', 1, m.quantity_max, 0),
        ]
        for i, (key, lo, hi, dec) in enumerate(specs):
            f = NumField(tr('job.' + key), float(getattr(self.job, key)), lo, hi, dec)
            f.changed.connect(lambda v, k=key: self._set(k, v))
            self.fields[key] = f
            grid.addWidget(label('job.' + key), row + i // 2, (i % 2) * 2)
            grid.addWidget(f, row + i // 2, (i % 2) * 2 + 1)
        row += (len(specs) + 1) // 2

        grid.addWidget(label('job.cut_mode'), row, 0)
        self.cut_group = QButtonGroup(self)
        cut_row = QHBoxLayout()
        for mode, key in CUT_KEYS:
            b = QPushButton(tr(key))
            b.setCheckable(True)
            self.cut_group.addButton(b, int(mode))
            cut_row.addWidget(b)
        self.cut_group.buttonClicked[int].connect(lambda i: self._set('cut_mode', CutMode(i)))
        grid.addLayout(cut_row, row, 1, 1, 3)
        row += 1
        grid.addWidget(label('job.laser_done_mode'), row, 0)
        self.done_group = QButtonGroup(self)
        done_row = QHBoxLayout()
        for mode, key in DONE_KEYS:
            b = QPushButton(tr(key))
            b.setCheckable(True)
            self.done_group.addButton(b, int(mode))
            done_row.addWidget(b)
        self.done_group.buttonClicked[int].connect(
            lambda i: self._set('laser_done_mode', LaserDone(i)))
        grid.addLayout(done_row, row, 1, 1, 3)
        row += 1
        self.trim = QCheckBox(tr('job.initial_trim_cut'))
        self.trim.toggled.connect(lambda v: self._set('initial_trim_cut', v))
        grid.addWidget(self.trim, row, 0, 1, 2)
        self.text_btn = QPushButton('')
        self.text_btn.clicked.connect(self._edit_text)
        grid.addWidget(label('job.mark_text'), row, 2)
        grid.addWidget(self.text_btn, row, 3)
        row += 1
        grid.addWidget(label('job.stations'), row, 0)
        self.station_widgets = []
        for i, st in enumerate(self.job.stations):
            en = QCheckBox(f'#{i}')
            en.setChecked(st.enabled)
            off = NumField(f'station {i} offset [mm]', st.offset_mm, 0.0, 5000.0, 1)
            dly = NumField(f'station {i} delay [s]', st.delay_s, 0.0, 60.0, 2)
            en.toggled.connect(self._stations_changed)
            off.changed.connect(self._stations_changed)
            dly.changed.connect(self._stations_changed)
            r = QHBoxLayout()
            r.addWidget(en)
            r.addWidget(QLabel('mm'))
            r.addWidget(off)
            r.addWidget(QLabel('s'))
            r.addWidget(dly)
            grid.addLayout(r, row, 1, 1, 3)
            row += 1
            self.station_widgets.append((en, off, dly))

        bottom = QHBoxLayout()
        self.summary = QLabel('')
        self.summary.setWordWrap(True)
        self.summary.setProperty('role', 'small')
        bottom.addWidget(self.summary, 3)
        describe = big_button('✎ ' + tr('job.describe'))
        describe.clicked.connect(self._describe)
        bottom.addWidget(describe, 1)
        save = big_button(tr('btn.save') + ' ' + tr('nav.recipes'))
        save.clicked.connect(self._save_recipe)
        start = big_button(tr('btn.start'), 'start')
        start.clicked.connect(self.request_start)
        bottom.addWidget(save, 1)
        bottom.addWidget(start, 1)
        outer.addLayout(bottom)
        self.load_job(self.job)

    # ------------------------------------------------------------------ model
    def load_job(self, job: Job):
        self.job = job
        self.job_id_btn.setText(job.job_id)
        for key, f in self.fields.items():
            f.set_value(float(getattr(job, key)))
        self.cut_group.button(int(job.cut_mode)).setChecked(True)
        self.done_group.button(int(job.laser_done_mode)).setChecked(True)
        self.trim.setChecked(job.initial_trim_cut)
        self.text_btn.setText(job.mark_text or '—')
        for i, (en, off, dly) in enumerate(self.station_widgets):
            if i < len(job.stations):
                en.setChecked(job.stations[i].enabled)
                off.set_value(job.stations[i].offset_mm)
                dly.set_value(job.stations[i].delay_s)
        self._update_summary()

    def _set(self, key, value):
        if key in ('quantity', 'cut_every_n'):
            value = int(value)
        setattr(self.job, key, value)
        self._update_summary()

    def _stations_changed(self, *_):
        self.job.stations = [Station(en.isChecked(), off.value(), dly.value())
                             for en, off, dly in self.station_widgets]
        self._update_summary()

    def _edit_job_id(self):
        text, ok = QInputDialog.getText(self, tr('job.job_id'), tr('job.job_id'),
                                        text=self.job.job_id)
        if ok:
            self.job.job_id = text.strip()
            self.job_id_btn.setText(self.job.job_id)
            self._update_summary()

    def _edit_text(self):
        text, ok = QInputDialog.getText(self, tr('job.mark_text'), tr('job.mark_text'),
                                        text=self.job.mark_text)
        if ok:
            self.job.mark_text = text
            self.text_btn.setText(text or '—')

    def errors(self):
        return validate(self.job, self.ctx.cfg)

    def _update_summary(self):
        errs = self.errors()
        piece = self.job.piece_length_mm()
        total_m = self.job.quantity * self.job.pitch_mm / 1000.0
        text = (f'{tr("job.piece_length")}: {piece:.1f} mm   belt: {total_m:.2f} m   ')
        if errs:
            text += '⚠ ' + '; '.join(errs)
            self.summary.setStyleSheet('color: #ff7b72')
        else:
            self.summary.setStyleSheet('')
        self.summary.setText(text)

    # ----------------------------------------------------------------- actions
    def request_start(self):
        if not self.ctx.require('operator'):
            return
        errs = self.errors()
        if errs:
            QMessageBox.warning(self, 'Job', tr('msg.invalid') + '\n• ' + '\n• '.join(errs))
            return
        if QMessageBox.question(self, 'Job', tr('msg.confirm_start', job=self.job.job_id,
                                                n=self.job.quantity)) != QMessageBox.Yes:
            return
        b = self.ctx.bridge
        spec = job_to_msg(self.job, b.job_spec, b.station_msg, target=b.job_spec())
        if b.run_job(spec, self.ctx.user()):
            self.ctx.db.audit(self.ctx.user(), 'ui_start_job', self.job.to_json())
            self.ctx.window.show_screen('production')
        else:
            self.ctx.message('RunJob action server not available', True)

    def _describe(self):
        """Natural-language job entry: fills the form, the operator checks and confirms."""
        text, ok = QInputDialog.getText(self, tr('job.describe'),
                                        'e.g. "200 pieces of 30 mm belt, cut each"')
        if not ok or not text.strip():
            return
        try:
            from belt_marking_vision.nl_job import parse_job_text
        except ImportError:
            self.ctx.message('belt_marking_vision not installed', True)
            return
        job, notes = parse_job_text(text, self.job)
        self.load_job(job)
        self.ctx.message(' · '.join(notes))
        self.ctx.db.audit(self.ctx.user(), 'nl_job_entry', {'text': text, 'notes': notes})

    def _save_recipe(self):
        if not self.ctx.require('technician'):
            return
        name, ok = QInputDialog.getText(self, tr('nav.recipes'), 'name',
                                        text=self.job.recipe or '')
        if not ok or not name.strip():
            return
        self.job.recipe = name.strip()
        b = self.ctx.bridge
        req = b.request('save')
        req.name, req.overwrite, req.user = self.job.recipe, True, self.ctx.user()
        req.spec = job_to_msg(self.job, b.job_spec, b.station_msg, target=b.job_spec())
        b.call('save', req, lambda r: self.ctx.message(r.message if r else 'offline',
                                                       r is None or not r.accepted))


class RecipesScreen(QWidget):

    def __init__(self, ctx):
        super().__init__()
        self.ctx = ctx
        lay = QHBoxLayout(self)
        self.list = QListWidget()
        lay.addWidget(self.list, 2)
        col = QVBoxLayout()
        for key, fn, role in (('btn.load', self._load, ''), ('btn.duplicate', self._dup, ''),
                              ('btn.delete', self._delete, 'stop')):
            b = big_button(tr(key), role)
            b.clicked.connect(fn)
            col.addWidget(b)
        refresh = big_button('⟳')
        refresh.clicked.connect(self.refresh)
        col.addWidget(refresh)
        lay.addLayout(col, 1)

    def showEvent(self, ev):
        self.refresh()
        super().showEvent(ev)

    def refresh(self):
        self.ctx.bridge.call('list', self.ctx.bridge.request('list'), self._fill)

    def _fill(self, res):
        self.list.clear()
        if res is None:
            return
        for name, w in zip(res.names, res.belt_widths_mm):
            self.list.addItem(f'{name}    ({w:g} mm)')

    def _selected(self):
        item = self.list.currentItem()
        return item.text().split('    (')[0] if item else None

    def _load(self):
        name = self._selected()
        if not name:
            return
        req = self.ctx.bridge.request('load')
        req.name = name
        self.ctx.bridge.call('load', req, self._loaded)

    def _loaded(self, res):
        if res is None or not res.found:
            self.ctx.message(res.message if res else 'offline', True)
            return
        from belt_marking_control.core.job import job_from_msg
        job = job_from_msg(res.spec)
        job.job_id = datetime.datetime.now().strftime('JOB-%Y%m%d-%H%M')
        screen = self.ctx.window.screens['job']
        # keep the station widgets consistent with the machine
        while len(job.stations) < len(screen.station_widgets):
            job.stations.append(Station(False, 0.0, 0.0))
        screen.load_job(job)
        self.ctx.window.show_screen('job')
        self.ctx.message(f'recipe {job.recipe} loaded: check belt guides for '
                         f'{job.belt_width_mm:g} mm')

    def _dup(self):
        name = self._selected()
        if not name or not self.ctx.require('technician'):
            return
        new, ok = QInputDialog.getText(self, tr('btn.duplicate'), 'new name', text=name + '-copy')
        if not ok or not new.strip():
            return
        req = self.ctx.bridge.request('load')
        req.name = name

        def got(res):
            if res is None or not res.found:
                return
            save = self.ctx.bridge.request('save')
            save.name, save.spec, save.overwrite, save.user = new.strip(), res.spec, False, \
                self.ctx.user()
            self.ctx.bridge.call('save', save, lambda _r: self.refresh())
        self.ctx.bridge.call('load', req, got)

    def _delete(self):
        name = self._selected()
        if not name or not self.ctx.require('technician'):
            return
        if QMessageBox.question(self, tr('btn.delete'), f'{name}?') != QMessageBox.Yes:
            return
        req = self.ctx.bridge.request('delete')
        req.name, req.user = name, self.ctx.user()
        self.ctx.bridge.call('delete', req, lambda _r: self.refresh())
