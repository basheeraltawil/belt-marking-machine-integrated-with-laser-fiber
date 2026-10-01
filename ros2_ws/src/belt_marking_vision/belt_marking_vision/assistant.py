"""Offline operator assistant: answers questions from the project documentation.

READ-ONLY by design: it has no ROS publishers/clients and cannot command the machine. It
only returns text and the source sections.

* Retrieval: BM25 over the Markdown sections of docs/ (no internet, no GPU).
* Alarm codes ("E-401", "w702", "alarm 201") are answered exactly from the alarm catalogue.
* Optional generation: if ``BELT_ASSISTANT_LLM_URL`` points to a local Ollama server
  (e.g. http://localhost:11434, model from ``BELT_ASSISTANT_MODEL``), the retrieved
  sections are summarised by the local model; otherwise the sections are returned as is.

    ros2 run belt_marking_vision assistant "what does E-401 mean and how do I fix it?"
"""

from dataclasses import dataclass
import glob
import json
import math
import os
import re
import sys
from typing import List, Optional
import urllib.request

from belt_marking_control.core.alarms import CATALOG

_WORD = re.compile(r'[a-zA-Z0-9äöüçğışÄÖÜÇĞİŞ]+')
_ALARM = re.compile(r'\b([EW])?[- ]?(\d{3})\b', re.IGNORECASE)
STOP = set('the a an and or of to in on for is are be it this that with how what why do i '
           'my me can does from by at as when which'.split())


@dataclass
class Section:
    source: str
    title: str
    text: str


def _tokens(text: str) -> List[str]:
    return [w.lower() for w in _WORD.findall(text) if w.lower() not in STOP]


def default_docs_dir() -> str:
    here = os.path.dirname(os.path.abspath(__file__))
    for cand in (os.environ.get('BELT_DOCS_DIR', ''),
                 os.path.join(here, '..', '..', '..', '..', 'docs'),
                 os.path.join(here, '..', '..', '..', '..', '..', 'docs'),
                 os.path.join(here, '..', 'share', 'belt_marking_vision', 'docs')):
        if cand and os.path.isdir(cand):
            return os.path.abspath(cand)
    try:
        from ament_index_python.packages import get_package_share_directory
        return os.path.join(get_package_share_directory('belt_marking_vision'), 'docs')
    except Exception:  # noqa: BLE001
        return 'docs'


class DocsAssistant:
    """Offline question answering over docs/ (BM25 + alarm catalogue)."""

    def __init__(self, docs_dir: Optional[str] = None, k1: float = 1.4, b: float = 0.75):
        self.sections = self._load(docs_dir or default_docs_dir())
        self.k1, self.b = k1, b
        self.docs = [_tokens(s.title + ' ' + s.text) for s in self.sections]
        self.avgdl = sum(map(len, self.docs)) / max(1, len(self.docs))
        df = {}
        for d in self.docs:
            for w in set(d):
                df[w] = df.get(w, 0) + 1
        n = len(self.docs)
        self.idf = {w: math.log(1 + (n - c + 0.5) / (c + 0.5)) for w, c in df.items()}

    @staticmethod
    def _load(docs_dir: str) -> List[Section]:
        out = []
        for path in sorted(glob.glob(os.path.join(docs_dir, '*.md'))):
            title, buf = os.path.basename(path), []
            for line in open(path, encoding='utf-8'):
                if line.startswith('#'):
                    if buf:
                        out.append(Section(os.path.basename(path), title, ''.join(buf)))
                    title, buf = line.strip('# \n'), []
                else:
                    buf.append(line)
            if buf:
                out.append(Section(os.path.basename(path), title, ''.join(buf)))
        return out

    def search(self, query: str, k: int = 3) -> List[Section]:
        q = _tokens(query)
        scores = []
        for i, d in enumerate(self.docs):
            tf = {}
            for w in d:
                tf[w] = tf.get(w, 0) + 1
            s = 0.0
            for w in q:
                if w in tf:
                    f = tf[w]
                    s += self.idf.get(w, 0) * f * (self.k1 + 1) / (
                        f + self.k1 * (1 - self.b + self.b * len(d) / self.avgdl))
            scores.append((s, i))
        scores.sort(reverse=True)
        return [self.sections[i] for s, i in scores[:k] if s > 0]

    def alarm_answer(self, question: str) -> Optional[str]:
        for prefix, code in _ALARM.findall(question):
            a = CATALOG.get(int(code))
            if a is not None and (prefix or 'alarm' in question.lower() or 'code' in
                                  question.lower() or len(question) < 12):
                return (f'{a.code_text} {a.text}\nSeverity: {a.severity.name}, machine '
                        f'reaction: {a.reaction.name}.\nWhat to do: {a.remedy}')
        return None

    def answer(self, question: str) -> dict:
        alarm = self.alarm_answer(question)
        hits = self.search(question, 3)
        context = '\n\n'.join(f'[{h.source} / {h.title}]\n{h.text.strip()[:1200]}' for h in hits)
        text = alarm or ''
        llm = self._llm(question, (alarm or '') + '\n\n' + context)
        if llm:
            text = llm
        elif not alarm:
            text = context or 'No matching section found in the documentation.'
        return {'answer': text, 'sources': [f'{h.source} / {h.title}' for h in hits],
                'generated': bool(llm)}

    @staticmethod
    def _llm(question: str, context: str) -> Optional[str]:
        url = os.environ.get('BELT_ASSISTANT_LLM_URL')
        if not url:
            return None
        prompt = ('You are a maintenance assistant for a belt marking machine. Answer ONLY '
                  'from the context. You cannot operate the machine; give instructions for '
                  'the operator. If unsure, say so.\n\nContext:\n' + context +
                  '\n\nQuestion: ' + question + '\nAnswer:')
        body = json.dumps({'model': os.environ.get('BELT_ASSISTANT_MODEL', 'llama3.2'),
                           'prompt': prompt, 'stream': False}).encode()
        try:
            req = urllib.request.Request(url.rstrip('/') + '/api/generate', body,
                                         {'Content-Type': 'application/json'})
            with urllib.request.urlopen(req, timeout=60) as resp:  # noqa: S310 - local URL
                return json.loads(resp.read())['response'].strip()
        except Exception:  # noqa: BLE001 - fall back to retrieval only
            return None


def main(argv=None):
    argv = sys.argv[1:] if argv is None else argv
    question = ' '.join(a for a in argv if not a.startswith('--ros-args'))
    if not question:
        print('usage: assistant "question"')
        return 1
    res = DocsAssistant().answer(question)
    print(res['answer'])
    print('\nsources: ' + '; '.join(res['sources']))
    return 0


if __name__ == '__main__':
    sys.exit(main())
