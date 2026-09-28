"""Natural-language job entry -> job form draft (the operator must check and confirm).

Deterministic rule-based parser (works offline, English + some Turkish words):

    >>> job, notes = parse_job_text('200 pieces of 30 mm belt, cut each, width 20mm')
    >>> job.quantity, job.pitch_mm, job.cut_mode.name, job.belt_width_mm
    (200, 30.0, 'EVERY', 20.0)

It never starts a job. Unrecognised parts are returned in ``notes``.
"""

import copy
import re
from typing import List, Optional, Tuple

from belt_marking_control.core.job import CutMode, Job, LaserDone

NUM = r'(\d+(?:[.,]\d+)?)'


def _f(s: str) -> float:
    return float(s.replace(',', '.'))


def parse_job_text(text: str, base: Optional[Job] = None) -> Tuple[Job, List[str]]:
    job = copy.deepcopy(base) if base is not None else Job()
    t = ' ' + text.lower().replace('×', 'x') + ' '
    found = []

    m = re.search(r'\b(?:job|order|iş|sipariş)\s*(?:id|no|#)?\s*[:=]?\s*([a-z0-9][\w\-/]*)', t)
    if m:
        job.job_id = m.group(1).upper()
        found.append('job id')
    m = re.search(NUM + r'\s*(?:pcs|pieces?|labels?|marks?|units?|adet|etiket|parça)\b', t)
    if m:
        job.quantity = int(_f(m.group(1)))
        found.append('quantity')
    m = re.search(r'(?:of|x)\s*' + NUM + r'\s*mm\b', t) or \
        re.search(r'(?:pitch|every|spacing|length|long|aralık|boy)\D{0,12}' + NUM + r'\s*mm', t) \
        or re.search(NUM + r'\s*mm\s*(?:long|pitch|labels?|pieces?|belt)', t)
    if m is None:   # fallback: the first length that is not a width
        m = re.search(r'(?<!width )(?<!wide )' + NUM + r'\s*mm\b(?!\s*(?:wide|width))', t)
        if m and re.search(r'(?:width|wide|genişlik)\D{0,8}$', t[:m.start()]):
            m = None
    if m:
        job.pitch_mm = _f(m.group(1))
        found.append('pitch')
    m = re.search(r'(?:width|wide|genişlik)\D{0,8}' + NUM + r'\s*mm', t) or \
        re.search(NUM + r'\s*mm\s*(?:wide|width)', t)
    if m:
        job.belt_width_mm = _f(m.group(1))
        found.append('belt width')
    m = re.search(r'mark(?:ing)?\s*length\D{0,8}' + NUM, t)
    if m:
        job.mark_length_mm = _f(m.group(1))
        found.append('mark length')
    m = re.search(r'(?:laser|marking|lazer)\s*(?:time)?\D{0,8}' + NUM +
                  r'\s*(?:s|sec|seconds?|sn)\b', t)
    if m:
        job.laser_time_s = _f(m.group(1))
        job.laser_done_mode = LaserDone.TIMED
        found.append('laser time')
    if re.search(r'done signal|busy signal', t):
        job.laser_done_mode = LaserDone.SIGNAL
        found.append('done signal')
    m = re.search(r'(?:speed|hız)\D{0,8}' + NUM + r'\s*mm/?s', t)
    if m:
        job.feed_speed_mm_s = _f(m.group(1))
        found.append('speed')

    m = re.search(r'(?:cut\s*every|sets?\s*of|every)\s*(\d+)\s*(?:marks?|labels?|pieces?|pcs)?',
                  t)
    if re.search(r"(no cut|don'?t cut|without cut|continuous|kesme|kesmeden|sürekli)", t):
        job.cut_mode = CutMode.NONE
        found.append('cut: none')
    elif re.search(r'cut (?:at|only at) (?:the )?end|end of (?:the )?batch|parti sonu', t):
        job.cut_mode = CutMode.END
        found.append('cut: end')
    elif m and int(m.group(1)) > 1 and 'mm' not in t[m.end():m.end() + 4]:
        job.cut_mode = CutMode.EVERY_N
        job.cut_every_n = int(m.group(1))
        found.append(f'cut every {job.cut_every_n}')
    elif re.search(r'cut (?:each|every|all)|each (?:one|piece)|her (?:parça|biri)|kes\b', t):
        job.cut_mode = CutMode.EVERY
        found.append('cut: every piece')
    notes = ['recognised: ' + ', '.join(found) if found else 'nothing recognised']
    if job.mark_length_mm > job.pitch_mm:
        job.mark_length_mm = round(job.pitch_mm * 0.7, 1)
        job.lead_mm = round(job.pitch_mm * 0.15, 1)
        notes.append('mark length/lead adapted to the pitch - check')
    notes.append('draft only: check every field and confirm before START')
    return job, notes
