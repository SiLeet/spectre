#!/usr/bin/env python3
"""E0a (T115, rust-port-plan §E0a): freeze the frame corpus outside every repo.

Collects every image the Python suite uses as a fixture, stores each one
losslessly as <sha16>.png under $SPECTRE_PARITY_DIR/frames/ (read-only after
the copy) and writes the two committed manifests:

  parity/frames.json            sha16 -> origin path(s), file size, w, h, mode
  parity/spectre-filelist.json  every file under .spectre (path, size, sha16 of the bytes)

sha16 of a frame = sha256(f"{mode}|{w}x{h}|" + RGB bytes)[:16]: the key depends
only on the pixels (as convert('RGB') sees them), never on PNG encoding.

Which images count as fixtures (union, each entry says how it was found):
  dynamic   PIL.Image.open on a repo file during a full suite run (`collect`)
  manifest  scripts/tests/frame_manifest.json (test_frame_regression)
  static    a '....png' string literal in scripts/tests/*.py that resolves to a file

Reads .spectre only. Writes go to $SPECTRE_PARITY_DIR and to parity/ of the
repo this script lives in. Needs no device.

  python scripts/tests/parity/freeze_corpus.py collect --repo C:/Users/Sigi/spectre --refs refs.json
  python scripts/tests/parity/freeze_corpus.py freeze  --repo C:/Users/Sigi/spectre --refs refs.json
"""
from __future__ import annotations

import argparse
import hashlib
import io
import json
import os
import re
import stat
import subprocess
import sys
import time
import unittest
import zlib
from pathlib import Path

HERE = Path(__file__).resolve().parent
OWN_REPO = HERE.parents[2]
OUT = OWN_REPO / 'parity'
PARITY_DIR = Path(os.environ.get('SPECTRE_PARITY_DIR', 'C:/Users/Sigi/spectre-parity'))
PNG_LIT = re.compile(r'''['"]([^'"\n]*?\.png)['"]''')
MISSING = re.compile(r'frame missing: (.+)$')


def frame_key(img) -> str:
    """sha16 over mode + size + RGB bytes (the corpus key, also used by the goldens)."""
    w, h = img.size
    rgb = img if img.mode == 'RGB' else img.convert('RGB')
    return hashlib.sha256(f'{img.mode}|{w}x{h}|'.encode() + rgb.tobytes()).hexdigest()[:16]


def rgb_crc32(img) -> int:
    """zlib.crc32 of the convert('RGB') bytes: lets the Rust loader prove pixel parity without sha2."""
    return zlib.crc32((img if img.mode == 'RGB' else img.convert('RGB')).tobytes())


def alpha_min(img) -> int | None:
    """Lowest alpha (None without an alpha channel). < 255: Pillow ops on the RGBA image differ from RGB."""
    if img.mode in ('RGBA', 'LA', 'PA') or (img.mode == 'P' and 'transparency' in img.info):
        return img.convert('RGBA').getchannel('A').getextrema()[0]
    return None


def file_sha16(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, 'rb') as f:
        for chunk in iter(lambda: f.read(1 << 20), b''):
            h.update(chunk)
    return h.hexdigest()[:16]


def rel(repo: Path, p: Path) -> str | None:
    try:
        return Path(os.path.abspath(p)).relative_to(repo).as_posix()
    except ValueError:
        return None


def generated(relpath: str) -> bool:
    """Files the suite writes itself: not fixtures."""
    return relpath.startswith('scripts/tests/.artifacts/')


# ---------------------------------------------------------------- .spectre write guard

WRITE_EVENTS = {'os.mkdir', 'os.rename', 'os.replace', 'os.remove', 'os.rmdir', 'os.chmod',
                'os.truncate', 'os.utime', 'os.link', 'os.symlink', 'shutil.rmtree', 'shutil.move'}


def guard_spectre(repo: Path, blocked: list, test_id) -> None:
    """Audit hook: any write under <repo>/.spectre raises PermissionError and is logged.

    The live lane owns .spectre; the suite must only read frames there."""
    root = os.path.normcase(os.path.abspath(repo / '.spectre'))

    def inside(p) -> bool:
        if isinstance(p, bytes):
            p = os.fsdecode(p)
        if not isinstance(p, (str, os.PathLike)):
            return False
        a = os.path.normcase(os.path.abspath(p))
        return a == root or a.startswith(root + os.sep)

    def hook(event, args):
        if event == 'open':
            path, mode, flags = (tuple(args) + (None, None))[:3]
            writes = (isinstance(mode, str) and any(c in mode for c in 'wax+')) or (
                isinstance(flags, int) and flags & (os.O_WRONLY | os.O_RDWR | os.O_CREAT
                                                    | os.O_APPEND | os.O_TRUNC))
            paths = [path] if writes else []
        elif event in WRITE_EVENTS:
            paths = list(args[:2]) if event in ('os.rename', 'os.replace', 'os.link',
                                                'os.symlink', 'shutil.move') else list(args[:1])
        else:
            return
        for p in paths:
            if inside(p):
                blocked.append({'test': test_id(), 'event': event, 'path': os.fsdecode(p)})
                raise PermissionError(f'parity export: write to .spectre blocked ({event} {p})')
    sys.addaudithook(hook)


# ---------------------------------------------------------------- collect

class _Result(unittest.TextTestResult):
    current = ['?']

    def __init__(self, *a, **k):
        super().__init__(*a, **k)
        self.missing: list[tuple[str, str]] = []

    def startTest(self, test):
        _Result.current[0] = test.id()
        super().startTest(test)

    def addSkip(self, test, reason):
        super().addSkip(test, reason)
        m = MISSING.search(str(reason))
        if m:
            self.missing.append((test.id(), m.group(1).strip()))


def collect(repo: Path, refs_out: Path, pattern: str = 'test*.py') -> int:
    """Run the suite of `repo` (in-process, cwd = repo) and log every Image.open."""
    sys.path.insert(0, str(repo / 'scripts'))
    sys.path.insert(0, str(repo / 'scripts' / 'tests'))
    from PIL import Image
    opened: dict[str, int] = {}
    outside = 0
    real_open = Image.open

    def hooked(fp, *a, **k):
        nonlocal outside
        if isinstance(fp, (str, os.PathLike)):
            r = rel(repo, Path(fp))
            if r is None:
                outside += 1
            elif not generated(r):
                opened[r] = opened.get(r, 0) + 1
        return real_open(fp, *a, **k)
    Image.open = hooked
    os.chdir(repo)
    import tempfile
    import afk_claim_vision as v               # per-run shot dir would be .spectre/shots-<pid>
    v.TMP = Path(tempfile.mkdtemp(prefix='parity-shots-'))
    blocked: list = []
    current = ['?']
    guard_spectre(repo, blocked, lambda: current[0])
    t0 = time.time()
    suite = unittest.defaultTestLoader.discover(str(repo / 'scripts' / 'tests'), pattern=pattern)
    _Result.current = current
    runner = unittest.TextTestRunner(resultclass=_Result, verbosity=0, stream=sys.stderr)
    res = runner.run(suite)
    Image.open = real_open
    data = {'repo': repo.as_posix(), 'tests_run': res.testsRun, 'failures': len(res.failures),
            'errors': len(res.errors), 'skipped': len(res.skipped),
            'seconds': round(time.time() - t0, 1), 'opened_outside_repo': outside, 'spectre_writes_blocked': blocked,
            'opened': dict(sorted(opened.items())),
            'frame_missing': sorted({p for _, p in res.missing}),
            'frame_missing_tests': sorted(res.missing)}
    refs_out.write_text(json.dumps(data, indent=1), encoding='utf-8')
    print(f'collect: {res.testsRun} tests, {len(opened)} repo images opened, '
          f'{len(data["frame_missing"])} frames missing -> {refs_out}')
    return 0 if res.wasSuccessful() and not blocked else 1


# ---------------------------------------------------------------- freeze

def static_refs(repo: Path) -> tuple[dict[str, str], list[str]]:
    """'*.png' literals in the tests -> {relpath: test file}; plus unresolved literals."""
    found, unresolved = {}, set()
    for f in sorted((repo / 'scripts' / 'tests').glob('*.py')):
        for lit in PNG_LIT.findall(f.read_text(encoding='utf-8', errors='replace')):
            if '{' in lit or '*' in lit:
                continue                       # f-string / glob: only the dynamic run sees it
            for cand in (repo / lit, repo / '.spectre' / lit, repo / '.spectre' / 'trash' / lit,
                         repo / '.spectre' / 'trash' / lit.removeprefix('.spectre/')):
                r = rel(repo, cand)
                if r and not generated(r) and cand.is_file():
                    if '/trash/' in r and not lit.startswith('.spectre/trash'):   # moved by F16 prune
                        r = '.spectre/' + r.split('/trash/', 1)[1]
                    found.setdefault(r, f.name)
                    break
            else:
                unresolved.add(lit)
    return found, sorted(unresolved)


def filelist(repo: Path) -> list[dict]:
    rows = []
    for p in sorted((repo / '.spectre').rglob('*')):
        try:
            if p.is_file():
                rows.append({'path': rel(repo, p), 'size': p.stat().st_size, 'sha16': file_sha16(p)})
        except OSError:                        # the live lane may delete files meanwhile
            continue
    return rows


def git_head(repo: Path) -> str:
    try:
        return subprocess.run(['git', '-C', str(repo), 'rev-parse', 'HEAD'], capture_output=True,
                              text=True, timeout=30).stdout.strip()
    except (OSError, subprocess.SubprocessError):
        return ''


def freeze(repo: Path, refs_path: Path) -> int:
    from PIL import Image
    refs = json.loads(refs_path.read_text(encoding='utf-8'))
    how: dict[str, set[str]] = {}
    for r in refs['opened']:
        how.setdefault(r, set()).add('dynamic')
    manifest = json.loads((repo / 'scripts' / 'tests' / 'frame_manifest.json').read_text(encoding='utf-8'))
    for e in manifest:
        how.setdefault(e['relpath'], set()).add('manifest')
    static, unresolved = static_refs(repo)
    for r in static:
        how.setdefault(r, set()).add('static')

    frames_dir = PARITY_DIR / 'frames'
    frames_dir.mkdir(parents=True, exist_ok=True)
    by_key: dict[str, dict] = {}
    gone, unreadable, written = [], [], 0
    for r in sorted(how):
        src = repo / r
        if not src.is_file() and r.startswith('.spectre/'):     # F16 prune moved it (like frame_regression)
            src = repo / '.spectre' / 'trash' / r[len('.spectre/'):]
        if not src.is_file():
            gone.append({'path': r, 'how': sorted(how[r])})
            continue
        try:
            data = src.read_bytes()
            with Image.open(io.BytesIO(data)) as im:
                im.load()
                key = frame_key(im)
                e = by_key.get(key)
                if e is None:
                    e = by_key[key] = {'sha16': key, 'w': im.size[0], 'h': im.size[1], 'mode': im.mode,
                                       'crc32': rgb_crc32(im), 'alpha_min': alpha_min(im),
                                       'rgb_sha16': None if im.mode == 'RGB' else frame_key(im.convert('RGB')),
                                       'src': [], 'how': set()}
            fsha = hashlib.sha256(data).hexdigest()[:16]
            # the corpus file holds the ORIGINAL bytes: pixel-lossless and byte-exact, so file-hash
            # checks (test_frame_regression) and the export overlay see what the tests saw
            dst = frames_dir / f'{key}.png'
            if not dst.exists() or file_sha16(dst) != fsha:
                if any(s['file_sha16'] != fsha for s in e['src']):
                    raise OSError(f'same pixels as {e["src"][0]["path"]} but other bytes')
                tmp = dst.with_suffix('.tmp')
                tmp.write_bytes(data)
                if dst.exists():
                    os.chmod(dst, stat.S_IREAD | stat.S_IWRITE)
                os.replace(tmp, dst)
                os.chmod(dst, stat.S_IREAD)
                written += 1
            e['src'].append({'path': r, 'found_at': rel(repo, src), 'bytes': len(data), 'file_sha16': fsha})
            e['how'] |= how[r]
        except OSError as exc:                     # truncated screencap etc.
            unreadable.append({'path': r, 'error': str(exc)})

    frames = [dict(e, how=sorted(e['how'])) for e in sorted(by_key.values(), key=lambda e: e['sha16'])]
    files = filelist(repo)
    OUT.mkdir(exist_ok=True)
    header = {'v': 1, 'frozen_at': time.strftime('%Y-%m-%dT%H:%M:%S'), 'source_repo': repo.as_posix(),
              'source_head': git_head(repo), 'parity_dir': PARITY_DIR.as_posix(),
              'key': 'sha256(f"{mode}|{w}x{h}|" + RGB bytes)[:16]'}
    (OUT / 'frames.json').write_text(json.dumps({
        **header, 'count': len(frames), 'bytes_in_corpus': sum(
            (frames_dir / f'{e["sha16"]}.png').stat().st_size for e in frames),
        'suite': {k: refs[k] for k in ('tests_run', 'failures', 'errors', 'skipped')},
        'frames_with_transparency': sum(1 for e in frames if (e['alpha_min'] if e['alpha_min'] is not None else 255) < 255),
        'frame_missing': refs['frame_missing'], 'static_unresolved': unresolved,
        'not_on_disk': gone, 'unreadable': unreadable, 'frames': frames}, indent=1),
        encoding='utf-8')
    (OUT / 'spectre-filelist.json').write_text(json.dumps({
        **header, 'count': len(files), 'bytes': sum(f['size'] for f in files), 'files': files},
        indent=1), encoding='utf-8')
    print(f'freeze: {len(frames)} frames ({written} new) from {len(how)} refs; '
          f'{len(refs["frame_missing"])} missing in suite, {len(gone)} gone, '
          f'{len(unreadable)} unreadable; filelist {len(files)} files')
    return 0


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split('\n\n')[0])
    ap.add_argument('cmd', choices=('collect', 'freeze'))
    ap.add_argument('--repo', type=Path, default=OWN_REPO, help='checkout whose .spectre holds the frames')
    ap.add_argument('--refs', type=Path, required=True, help='collect output / freeze input (JSON)')
    ap.add_argument('--pattern', default='test*.py')
    a = ap.parse_args(argv)
    repo = a.repo.resolve()
    refs = a.refs.resolve()
    if a.cmd == 'collect':
        return collect(repo, refs, a.pattern)
    return freeze(repo, refs)


if __name__ == '__main__':
    sys.exit(main())
