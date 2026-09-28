"""Minimal translation table (English + Turkish). Missing keys fall back to English/key.

Add a language by adding a column; the UI rebuilds its texts on ``set_language``.
"""

_LANG = 'en'

T = {
    # navigation
    'nav.production': ('Production', 'Üretim'),
    'nav.job': ('Job setup', 'İş ayarı'),
    'nav.recipes': ('Recipes', 'Reçeteler'),
    'nav.manual': ('Manual', 'Manuel'),
    'nav.calibration': ('Calibration', 'Kalibrasyon'),
    'nav.alarms': ('Alarms', 'Alarmlar'),
    'nav.logs': ('Logs / OEE', 'Kayıtlar / OEE'),
    'nav.settings': ('Settings', 'Ayarlar'),
    # production
    'btn.start': ('START', 'BAŞLAT'),
    'btn.hold': ('HOLD', 'BEKLET'),
    'btn.resume': ('RESUME', 'DEVAM'),
    'btn.stop': ('STOP', 'DURDUR'),
    'btn.reset': ('RESET', 'SIFIRLA'),
    'btn.clear': ('CLEAR', 'TEMİZLE'),
    'btn.ack': ('ACK', 'ONAYLA'),
    'btn.ack_all': ('Acknowledge all', 'Tümünü onayla'),
    'btn.login': ('Login', 'Giriş'),
    'btn.logout': ('Logout', 'Çıkış'),
    'btn.save': ('Save', 'Kaydet'),
    'btn.load': ('Load', 'Yükle'),
    'btn.delete': ('Delete', 'Sil'),
    'btn.duplicate': ('Duplicate', 'Kopyala'),
    'btn.export': ('Export CSV to USB', "CSV'yi USB'ye aktar"),
    'btn.cancel': ('Cancel', 'İptal'),
    'btn.ok': ('OK', 'Tamam'),
    'lbl.state': ('State', 'Durum'),
    'lbl.mode': ('Mode', 'Mod'),
    'lbl.job': ('Job', 'İş'),
    'lbl.recipe': ('Recipe', 'Reçete'),
    'lbl.marks': ('Marks', 'Markalama'),
    'lbl.remaining': ('Remaining', 'Kalan'),
    'lbl.pieces': ('Pieces cut', 'Kesilen parça'),
    'lbl.rejects': ('Rejects', 'Ret'),
    'lbl.phase': ('Phase', 'Aşama'),
    'lbl.belt_pos': ('Belt position', 'Bant konumu'),
    'lbl.user': ('User', 'Kullanıcı'),
    'lbl.no_user': ('not logged in', 'giriş yok'),
    # job fields
    'job.job_id': ('Job / order ID', 'İş / sipariş no'),
    'job.belt_width_mm': ('Belt width [mm]', 'Bant genişliği [mm]'),
    'job.quantity': ('Number of marks', 'Markalama adedi'),
    'job.pitch_mm': ('Mark pitch [mm]', 'Etiket aralığı [mm]'),
    'job.mark_length_mm': ('Mark length [mm]', 'Marka uzunluğu [mm]'),
    'job.lead_mm': ('Lead (edge→mark) [mm]', 'Kenar→marka [mm]'),
    'job.cut_mode': ('Cut mode', 'Kesim modu'),
    'job.cut_every_n': ('Cut every N', "Her N'de kes"),
    'job.laser_time_s': ('Laser time [s]', 'Lazer süresi [s]'),
    'job.laser_done_mode': ('Laser done by', 'Lazer bitişi'),
    'job.settle_s': ('Settle [s]', 'Bekleme [s]'),
    'job.post_mark_delay_s': ('Post-mark delay [s]', 'Marka sonrası [s]'),
    'job.feed_speed_mm_s': ('Feed speed [mm/s]', 'Besleme hızı [mm/s]'),
    'job.initial_trim_cut': ('Trim cut at start', 'Başta kırpma kesimi'),
    'job.mark_text': ('Expected text (QA)', 'Beklenen metin (QA)'),
    'job.piece_length': ('Piece length', 'Parça uzunluğu'),
    'job.stations': ('Laser stations', 'Lazer istasyonları'),
    'cut.none': ('Continuous', 'Sürekli'),
    'cut.every': ('Every piece', 'Her parça'),
    'cut.every_n': ('Every N', 'Her N'),
    'cut.end': ('End of batch', 'Parti sonu'),
    'done.config': ('Machine default', 'Makine varsayılanı'),
    'done.signal': ('Done signal', 'Bitti sinyali'),
    'done.timed': ('Time', 'Süre'),
    'msg.confirm_start': ('Start job {job} with {n} marks?',
                          '{job} işi {n} markalama ile başlasın mı?'),
    'msg.invalid': ('Please correct:', 'Lütfen düzeltin:'),
    'msg.need_role': ('Requires role: {role}', 'Gerekli yetki: {role}'),
    'msg.need_manual': ('Switch to MANUAL mode first', 'Önce MANUEL moda geçin'),
    'msg.exported': ('Exported {n} files to {path}', '{n} dosya {path} konumuna aktarıldı'),
    'msg.resume_laser': ('The laser did not finish. Retry the mark or count it as reject?',
                         'Lazer bitmedi. Tekrar markalansın mı yoksa ret sayılsın mı?'),
    'btn.retry': ('RETRY', 'TEKRAR'),
    'btn.reject': ('REJECT', 'RET'),
    'manual.jog': ('Jog belt (hold)', 'Bant ilerlet (basılı tut)'),
    'manual.feed': ('Feed distance', 'Besleme mesafesi'),
    'manual.cut': ('Cut now', 'Şimdi kes'),
    'manual.laser': ('Trigger laser once', 'Lazeri bir kez tetikle'),
    'manual.zair': ('Z-Air', 'Z-Hava'),
    'manual.home': ('Zero position', 'Konumu sıfırla'),
    'mode.AUTO': ('AUTO', 'OTOMATİK'),
    'mode.MANUAL': ('MANUAL', 'MANUEL'),
    'mode.MAINTENANCE': ('MAINTENANCE', 'BAKIM'),
    'mode.SIMULATION': ('SIMULATION', 'SİMÜLASYON'),
}

LANGUAGES = {'en': 0, 'tr': 1}


def set_language(lang: str) -> None:
    global _LANG
    if lang in LANGUAGES:
        _LANG = lang


def language() -> str:
    return _LANG


def tr(key: str, **fmt) -> str:
    entry = T.get(key)
    if entry is None:
        text = key
    else:
        idx = LANGUAGES[_LANG]
        text = entry[idx] if idx < len(entry) and entry[idx] else entry[0]
    return text.format(**fmt) if fmt else text
