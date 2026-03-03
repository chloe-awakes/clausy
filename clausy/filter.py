from __future__ import annotations

import json
import logging
import os
import re
from dataclasses import dataclass
from typing import Any, Dict, Iterable, List, Optional, Sequence, Set, Tuple


_DEFAULT_SCAN_PATH = os.path.expanduser("~/.openclaw")
_PATH_TRAVERSAL_SEGMENT_RE = re.compile(r"(^|[\\/])\.\.([\\/]|$)")
logger = logging.getLogger(__name__)

# Hard patterns (independent of "known secrets")
_PEM_PRIVATE_KEY_RE = re.compile(
    r"-----BEGIN [A-Z ]*PRIVATE KEY-----[\s\S]+?-----END [A-Z ]*PRIVATE KEY-----",
    re.MULTILINE,
)

# Bearer tokens (we redact the token part, keep 'Bearer ')
_BEARER_RE = re.compile(r"(?i)\bBearer\s+([A-Za-z0-9\-\._~\+/]+=*)")

# JWT-ish: three base64url-ish segments separated by dots (heuristic)
_JWT_RE = re.compile(r"\b([A-Za-z0-9_-]{10,})\.([A-Za-z0-9_-]{10,})\.([A-Za-z0-9_-]{10,})\b")

# Provider-ish prefixes (best-effort; NOT used for outbound unless paranoia enabled)
_KNOWN_PREFIX_RE = re.compile(
    r"\b("
    r"sk-[A-Za-z0-9]{10,}"
    r"|sk-ant-[A-Za-z0-9]{10,}"
    r"|AIza[0-9A-Za-z\-_]{20,}"
    r"|ghp_[0-9A-Za-z]{20,}"
    r"|github_pat_[0-9A-Za-z_]{20,}"
    r"|xox[baprs]-[0-9A-Za-z-]{10,}"
    r"|rk_(live|test)_[0-9A-Za-z]{10,}"
    r"|sk_(live|test)_[0-9A-Za-z]{10,}"
    r")\b"
)

# Keys to look for in config files (case-insensitive substring match)
_SENSITIVE_KEY_NAMES = (
    "apikey", "api_key", "api-key",
    "token", "access_token", "refresh_token", "bearer",
    "secret", "client_secret",
    "password", "passphrase",
    "private_key", "privatekey",
)

def _is_text_file(path: str) -> bool:
    # Heuristic: treat common config/text formats as text.
    lower = path.lower()
    return lower.endswith((".json", ".yaml", ".yml", ".toml", ".ini", ".conf", ".env", ".txt"))

def _safe_read_text(path: str, max_bytes: int) -> Optional[str]:
    try:
        with open(path, "rb") as f:
            data = f.read(max_bytes + 1)
        if len(data) > max_bytes:
            return None
        return data.decode("utf-8", errors="replace")
    except Exception:
        return None

def _walk(obj: Any) -> Iterable[Tuple[Optional[str], Any]]:
    # Yields (key, value) for dicts/lists; key is None for list entries.
    if isinstance(obj, dict):
        for k, v in obj.items():
            yield k, v
            yield from _walk(v)
    elif isinstance(obj, list):
        for v in obj:
            yield None, v
            yield from _walk(v)

def _looks_sensitive_key(name: str) -> bool:
    n = (name or "").lower()
    return any(s in n for s in _SENSITIVE_KEY_NAMES)

def _collect_from_json_text(txt: str) -> Set[str]:
    secrets: Set[str] = set()
    try:
        obj = json.loads(txt)
    except Exception:
        return secrets

    for k, v in _walk(obj):
        if isinstance(k, str) and _looks_sensitive_key(k):
            if isinstance(v, str) and v.strip():
                secrets.add(v.strip())
    return secrets

def _collect_from_kv_text(txt: str) -> Set[str]:
    # Parse simple KEY=VALUE lines and also "key: value" YAML-ish lines.
    secrets: Set[str] = set()
    for line in txt.splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue

        m = re.match(r"^([A-Za-z0-9_.-]+)\s*[:=]\s*(.+)$", line)
        if not m:
            continue
        key = m.group(1)
        val = m.group(2).strip().strip("'\"")
        if _looks_sensitive_key(key) and val:
            secrets.add(val)
    return secrets

def _is_safe_scan_path(value: str) -> bool:
    if not value:
        return False
    if any(ord(ch) < 32 or ord(ch) == 127 for ch in value):
        return False
    if _PATH_TRAVERSAL_SEGMENT_RE.search(value):
        return False
    return True


def _sanitize_scan_paths(paths: Sequence[str]) -> Tuple[str, ...]:
    safe: List[str] = []
    for raw in paths:
        p = os.path.expanduser((raw or "").strip())
        if not p:
            continue
        if not _is_safe_scan_path(p):
            continue
        safe.append(p)
    return tuple(safe)


def collect_secrets_from_env() -> Set[str]:
    secrets: Set[str] = set()
    for k, v in os.environ.items():
        if not v or not isinstance(v, str):
            continue
        kl = k.lower()
        if any(x in kl for x in ("key", "token", "secret", "pass")):
            if v.strip():
                secrets.add(v.strip())
    return secrets

def collect_secrets_from_paths(paths: Sequence[str], max_bytes: int = 2_000_000) -> Set[str]:
    secrets: Set[str] = set()
    for p in _sanitize_scan_paths(paths):
        if not os.path.exists(p):
            continue
        if os.path.isfile(p):
            files = [p]
        else:
            files = []
            for root, dirs, filenames in os.walk(p):
                # Skip some noisy dirs
                skip = {"node_modules", ".git", "__pycache__", "profile", "profiles", "user-data-dir", "logs"}
                dirs[:] = [d for d in dirs if d not in skip]
                for fn in filenames:
                    full = os.path.join(root, fn)
                    files.append(full)

        for fpath in files:
            if not _is_text_file(fpath):
                continue
            txt = _safe_read_text(fpath, max_bytes=max_bytes)
            if not txt:
                continue
            lower = fpath.lower()
            if lower.endswith(".json"):
                secrets |= _collect_from_json_text(txt)
            else:
                secrets |= _collect_from_kv_text(txt)
    return secrets

def _mask(s: str) -> str:
    s = s.strip()
    if len(s) <= 8:
        return "[FILTERED]"
    return f"{s[:3]}…{s[-3:]}"

def _escape_for_regex(s: str) -> str:
    return re.escape(s)

class PrefixMatcher:
    """Aho–Corasick-style automaton over a set of known secrets.

    We use it in streaming to compute:
      k = longest suffix of the current text that is also a prefix of any known secret.

    The automaton state after consuming a string represents the longest suffix
    that matches a trie path (i.e., a prefix of some secret). Therefore, the depth
    of the state is exactly k.
    """

    def __init__(self, patterns: Iterable[str]):
        self.goto: List[Dict[str, int]] = []
        self.fail: List[int] = []
        self.depth: List[int] = []
        self.min_pat_len: List[int] = []  # minimum full pattern length that shares this prefix

        self.goto.append({})
        self.fail.append(0)
        self.depth.append(0)
        self.min_pat_len.append(10**9)

        pats = [p for p in patterns if isinstance(p, str) and p]
        for p in pats:
            self._add(p)

        self._build_failures()

    def _add(self, s: str) -> None:
        state = 0
        L = len(s)
        # root shares all prefixes
        if L < self.min_pat_len[state]:
            self.min_pat_len[state] = L
        for ch in s:
            nxt = self.goto[state].get(ch)
            if nxt is None:
                nxt = len(self.goto)
                self.goto[state][ch] = nxt
                self.goto.append({})
                self.fail.append(0)
                self.depth.append(self.depth[state] + 1)
                self.min_pat_len.append(10**9)
            state = nxt
            if L < self.min_pat_len[state]:
                self.min_pat_len[state] = L

    def _build_failures(self) -> None:
        from collections import deque
        q = deque()

        # depth-1 states from root fail to root
        for ch, s in self.goto[0].items():
            self.fail[s] = 0
            q.append(s)

        while q:
            r = q.popleft()
            for ch, s in self.goto[r].items():
                q.append(s)
                f = self.fail[r]
                while f and ch not in self.goto[f]:
                    f = self.fail[f]
                self.fail[s] = self.goto[f].get(ch, 0)
                # depth is already set by construction

    def step(self, state: int, ch: str) -> int:
        while state and ch not in self.goto[state]:
            state = self.fail[state]
        return self.goto[state].get(ch, 0)

    def feed(self, state: int, text: str) -> int:
        for ch in text:
            state = self.step(state, ch)
        return state

    def k(self, state: int) -> int:
        return self.depth[state]

    def min_len(self, state: int) -> int:
        return self.min_pat_len[state]

@dataclass
class FilterConfig:
    mode: str = "smart"  # smart|both|outbound|off
    scan_openclaw: bool = True
    scan_paths: Tuple[str, ...] = (_DEFAULT_SCAN_PATH,)
    max_bytes: int = 2_000_000
    max_tail: int = 32_768
    enable_prefix_patterns: bool = False  # paranoia mode


@dataclass
class ProfanityFilterConfig:
    mode: str = "off"  # off|mask|block
    words: Tuple[str, ...] = ()
    replacement: str = "[CENSORED]"
    block_message: str = "Content blocked by safety filter."


def _env_int_bounded(
    raw: str | None,
    *,
    var_name: str,
    default: int,
    min_value: int,
    max_value: int,
) -> int:
    if raw is None or not str(raw).strip():
        return default
    val = str(raw).strip()
    try:
        parsed = int(val)
    except Exception:
        logger.warning("%s=%r is invalid; using %d", var_name, val, default)
        return default
    if not (min_value <= parsed <= max_value):
        logger.warning(
            "%s=%d is out of range (valid range is %d-%d); using %d",
            var_name,
            parsed,
            min_value,
            max_value,
            default,
        )
        return default
    return parsed


def load_filter_config_from_env() -> FilterConfig:
    mode = os.environ.get("CLAUSY_FILTER_MODE", "smart").strip().lower()
    scan_openclaw = os.environ.get("CLAUSY_FILTER_SCAN_OPENCLAW", "1").strip() not in ("0", "false", "no")
    scan_paths_env = os.environ.get("CLAUSY_FILTER_SCAN_PATHS", "").strip()
    if scan_paths_env:
        scan_paths = _sanitize_scan_paths(scan_paths_env.split(","))
        if not scan_paths:
            scan_paths = (_DEFAULT_SCAN_PATH,)
    else:
        scan_paths = (_DEFAULT_SCAN_PATH,)
    max_bytes = _env_int_bounded(
        os.environ.get("CLAUSY_FILTER_MAX_BYTES"),
        var_name="CLAUSY_FILTER_MAX_BYTES",
        default=2_000_000,
        min_value=1,
        max_value=200_000_000,
    )
    max_tail = _env_int_bounded(
        os.environ.get("CLAUSY_FILTER_MAX_TAIL"),
        var_name="CLAUSY_FILTER_MAX_TAIL",
        default=32_768,
        min_value=1,
        max_value=2_000_000,
    )
    enable_prefix = os.environ.get("CLAUSY_FILTER_PREFIX_PATTERNS", "0").strip() in ("1", "true", "yes")
    return FilterConfig(
        mode=mode,
        scan_openclaw=scan_openclaw,
        scan_paths=scan_paths,
        max_bytes=max_bytes,
        max_tail=max_tail,
        enable_prefix_patterns=enable_prefix,
    )


def load_profanity_filter_config_from_env() -> ProfanityFilterConfig:
    mode = os.environ.get("CLAUSY_BADWORD_FILTER_MODE", "off").strip().lower()
    words_env = os.environ.get("CLAUSY_BADWORD_WORDS", "")
    words = tuple(w.strip().lower() for w in words_env.split(",") if w.strip())
    replacement = os.environ.get("CLAUSY_BADWORD_REPLACEMENT", "[CENSORED]").strip() or "[CENSORED]"
    block_message = os.environ.get("CLAUSY_BADWORD_BLOCK_MESSAGE", "Content blocked by safety filter.").strip() or "Content blocked by safety filter."
    return ProfanityFilterConfig(mode=mode, words=words, replacement=replacement, block_message=block_message)


class ProfanityFilter:
    def __init__(self, cfg: Optional[ProfanityFilterConfig] = None):
        self.cfg = cfg or load_profanity_filter_config_from_env()
        self._compiled = self._compile()

    def _compile(self) -> Optional[re.Pattern]:
        if self.cfg.mode not in ("mask", "block") or not self.cfg.words:
            return None
        words = sorted({w for w in self.cfg.words if w}, key=len, reverse=True)
        if not words:
            return None
        escaped = "|".join(re.escape(w) for w in words)
        return re.compile(rf"\b(?:{escaped})\b", re.IGNORECASE)

    def filter_text(self, text: str) -> str:
        if self.cfg.mode == "off" or not text or self._compiled is None:
            return text
        if self.cfg.mode == "block":
            if self._compiled.search(text):
                return self.cfg.block_message
            return text
        return self._compiled.sub(self.cfg.replacement, text)


class SecretFilter:
    def __init__(self, cfg: Optional[FilterConfig] = None):
        self.cfg = cfg or load_filter_config_from_env()
        self.known: Set[str] = set()
        self._compiled: Optional[re.Pattern] = None
        self._matcher: Optional[PrefixMatcher] = None

    def refresh(self) -> None:
        # Collect "known secrets" from env + optionally OpenClaw config directories
        known = set()
        known |= collect_secrets_from_env()

        if self.cfg.scan_openclaw:
            known |= collect_secrets_from_paths(self.cfg.scan_paths, max_bytes=self.cfg.max_bytes)

        # Remove very short values (too many false positives)
        known = {s for s in known if isinstance(s, str) and len(s.strip()) >= 10}
        self.known = known
        self._compiled = self._compile_known_regex()
        self._matcher = PrefixMatcher(self.known) if self.known else None

    def _compile_known_regex(self) -> Optional[re.Pattern]:
        if not self.known:
            return None
        # Sort by length desc to prefer longer matches first
        parts = sorted((_escape_for_regex(s) for s in self.known), key=len, reverse=True)
        # Use a non-capturing alternation
        return re.compile("|".join(parts))

    def _filter_known(self, text: str) -> str:
        if not text:
            return text
        if not self._compiled:
            return text

        def repl(m: re.Match) -> str:
            return _mask(m.group(0))

        return self._compiled.sub(repl, text)

    def _filter_hard_patterns(self, text: str) -> str:
        if not text:
            return text
        # PEM keys
        text = _PEM_PRIVATE_KEY_RE.sub("[FILTERED_PRIVATE_KEY]", text)

        # Bearer token: keep Bearer, mask token
        def bearer_repl(m: re.Match) -> str:
            tok = m.group(1) or ""
            return "Bearer " + _mask(tok)

        text = _BEARER_RE.sub(bearer_repl, text)

        # JWT-ish
        def jwt_repl(m: re.Match) -> str:
            whole = m.group(0) or ""
            return _mask(whole)

        text = _JWT_RE.sub(jwt_repl, text)

        if self.cfg.enable_prefix_patterns:
            text = _KNOWN_PREFIX_RE.sub(lambda m: _mask(m.group(0) or ""), text)

        return text

    def stream_init(self) -> Tuple[str, int]:
        """Initialize streaming boundary protection state.

        Returns (tail, automaton_state). Only meaningful when known secrets are loaded.
        """
        return "", 0

    def stream_split_safe(self, tail: str, state: int, delta: str) -> Tuple[str, str, int]:
        """Split tail+delta into (safe_to_emit, new_tail, new_state).

        new_tail is the longest suffix that could still be the beginning of a known secret.
        This prevents partial secret leakage across chunk boundaries.

        If the tail grows beyond cfg.max_tail, we fail-closed: emit a marker and reset.
        """
        if not delta:
            return "", tail, state

        raw = (tail or "") + delta

        if self._matcher is None:
            # No known secrets; don't hold back anything
            return raw, "", 0

        # Advance automaton with the new delta; current state represents the current tail.
        new_state = self._matcher.feed(state, delta)
        k = self._matcher.k(new_state)

        if k <= 0:
            return raw, "", 0

        safe = raw[:-k]
        new_tail = raw[-k:]

        # Hard cap tail (fail-closed): mask and reset if we exceed.
        if len(new_tail) > self.cfg.max_tail:
            safe = safe + "[FILTERED_MAX_TAIL_REACHED]"
            return safe, "", 0

        return safe, new_tail, new_state

    def stream_flush_tail(self, tail: str, state: int) -> Tuple[str, str, int]:
        """Flush remaining tail at end of stream safely.

        If the tail still matches a prefix of a known secret and the matched prefix
        is more than half of the shortest possible secret length for this prefix,
        we mask it instead of emitting raw.
        """
        if not tail:
            return "", "", 0

        if self._matcher is None:
            return tail, "", 0

        k = self._matcher.k(state)
        if k > 0:
            min_len = self._matcher.min_len(state)
            # Only mask on flush if we already hold more than half of a candidate secret
            if min_len < 10**9 and k > (min_len / 2.0):
                return "[FILTERED_PARTIAL_SECRET_FLUSH]", "", 0

        return tail, "", 0
    def filter_outbound(self, text: str) -> str:
        # Outbound = to web LLM. In smart mode, only filter known secrets.
        if self.cfg.mode == "off":
            return text
        if self.cfg.mode in ("outbound", "both", "smart"):
            text = self._filter_known(text)
            # do NOT apply hard patterns outbound by default (to avoid breaking sample keys)
            if self.cfg.mode == "both" and self.cfg.enable_prefix_patterns:
                text = self._filter_hard_patterns(text)
        return text

    def filter_inbound(self, text: str) -> str:
        # Inbound = from web LLM to OpenClaw/client. In smart mode, filter known + hard patterns.
        if self.cfg.mode == "off":
            return text
        if self.cfg.mode in ("both", "smart", "outbound"):
            text = self._filter_known(text)
        # Always apply hard patterns inbound (safe default)
        text = self._filter_hard_patterns(text)
        return text

    def filter_tool_calls_inplace(self, tool_calls: Any) -> Any:
        # Filter tool_calls structure:
        # - name should remain
        # - arguments is JSON-encoded string: we filter inside that string and also try to parse and filter values
        if not isinstance(tool_calls, list):
            return tool_calls
        for tc in tool_calls:
            if not isinstance(tc, dict):
                continue
            fn = tc.get("function")
            if not isinstance(fn, dict):
                continue
            args = fn.get("arguments")
            if isinstance(args, str) and args:
                # First: filter known + hard patterns in string form (robust even if JSON is broken)
                filtered = self.filter_inbound(args)
                # Second: if it's valid JSON, filter string values inside and dump back
                try:
                    obj = json.loads(filtered)
                    obj = self._filter_obj_strings(obj)
                    filtered = json.dumps(obj, ensure_ascii=False)
                except Exception:
                    pass
                fn["arguments"] = filtered
        return tool_calls

    def _filter_obj_strings(self, obj: Any) -> Any:
        if isinstance(obj, dict):
            return {k: self._filter_obj_strings(v) for k, v in obj.items()}
        if isinstance(obj, list):
            return [self._filter_obj_strings(v) for v in obj]
        if isinstance(obj, str):
            return self.filter_inbound(obj)
        return obj
