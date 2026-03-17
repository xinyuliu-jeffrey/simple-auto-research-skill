#!/usr/bin/env python3
"""
research_tools.py - Standalone CLI for academic research tasks.

Uses ONLY Python stdlib. No pip dependencies required.

Sub-commands:
    search-papers    Search arXiv, Semantic Scholar, and OpenAlex for papers
    search-repos     Search GitHub for relevant repositories
    run-experiment   Run an experiment command and capture results
    verify-citations Verify citation validity against Semantic Scholar and arXiv
"""

import argparse
import datetime
import json
import os
import re
import subprocess
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET
from typing import Any, Dict, List, Optional


# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

USER_AGENT = "ResearchTools/1.0"
REQUEST_TIMEOUT = 15  # seconds

GITHUB_SEARCH_API = "https://api.github.com/search/repositories"

ARXIV_API = "http://export.arxiv.org/api/query"
SEMANTIC_SCHOLAR_API = "https://api.semanticscholar.org/graph/v1/paper/search"
OPENALEX_API = "https://api.openalex.org/works"


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_request(url: str) -> bytes:
    """Issue a GET request with standard headers and timeout."""
    req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    with urllib.request.urlopen(req, timeout=REQUEST_TIMEOUT) as resp:
        return resp.read()


def _normalize_title(title: str) -> str:
    """Lowercase and strip whitespace for deduplication."""
    return " ".join(title.lower().split())


def _reconstruct_abstract_from_inverted_index(
    inverted_index: Optional[Dict[str, List[int]]],
) -> str:
    """
    OpenAlex stores abstracts as an inverted index:
        {"word": [pos0, pos1, ...], ...}
    Reconstruct the original text by placing each word at its positions.
    """
    if not inverted_index:
        return ""
    # Determine total length
    max_pos = -1
    for positions in inverted_index.values():
        for p in positions:
            if p > max_pos:
                max_pos = p
    if max_pos < 0:
        return ""
    words: List[str] = [""] * (max_pos + 1)
    for word, positions in inverted_index.items():
        for p in positions:
            words[p] = word
    return " ".join(words)


def _paper_info_score(paper: Dict[str, Any]) -> int:
    """Score how much information a paper entry contains (for dedup preference)."""
    score = 0
    if paper.get("abstract"):
        score += 2
    if paper.get("citation_count") is not None and paper["citation_count"] > 0:
        score += 2
    if paper.get("doi"):
        score += 1
    if paper.get("arxiv_id"):
        score += 1
    if paper.get("url"):
        score += 1
    if paper.get("authors"):
        score += 1
    return score


# ---------------------------------------------------------------------------
# API Fetchers
# ---------------------------------------------------------------------------


def search_arxiv(query: str, max_results: int, year_min: Optional[int]) -> List[Dict[str, Any]]:
    """Search arXiv Atom API and return normalized paper dicts."""
    params = urllib.parse.urlencode({
        "search_query": f"all:{query}",
        "start": 0,
        "max_results": max_results,
    })
    url = f"{ARXIV_API}?{params}"

    try:
        data = _make_request(url)
    except (urllib.error.URLError, OSError) as exc:
        print(f"[WARN] arXiv API request failed: {exc}", file=sys.stderr)
        return []

    papers: List[Dict[str, Any]] = []
    try:
        root = ET.fromstring(data)
    except ET.ParseError as exc:
        print(f"[WARN] arXiv XML parse error: {exc}", file=sys.stderr)
        return []

    ns = {"atom": "http://www.w3.org/2005/Atom"}

    for entry in root.findall("atom:entry", ns):
        title_el = entry.find("atom:title", ns)
        title = title_el.text.strip().replace("\n", " ") if title_el is not None and title_el.text else ""

        # Authors
        authors: List[str] = []
        for author_el in entry.findall("atom:author", ns):
            name_el = author_el.find("atom:name", ns)
            if name_el is not None and name_el.text:
                authors.append(name_el.text.strip())

        # Published date -> year
        published_el = entry.find("atom:published", ns)
        year: Optional[int] = None
        if published_el is not None and published_el.text:
            try:
                year = int(published_el.text[:4])
            except (ValueError, IndexError):
                pass

        # Year filter
        if year_min is not None and year is not None and year < year_min:
            continue

        # Abstract
        summary_el = entry.find("atom:summary", ns)
        abstract = ""
        if summary_el is not None and summary_el.text:
            abstract = summary_el.text.strip().replace("\n", " ")

        # arXiv ID from <id> element (e.g. http://arxiv.org/abs/2401.12345v1)
        id_el = entry.find("atom:id", ns)
        arxiv_id = ""
        if id_el is not None and id_el.text:
            # Extract the ID portion after /abs/
            raw_id = id_el.text.strip()
            if "/abs/" in raw_id:
                arxiv_id = raw_id.split("/abs/")[-1]
                # Strip version suffix (e.g. v1)
                if "v" in arxiv_id:
                    arxiv_id = arxiv_id.rsplit("v", 1)[0]

        url_str = f"https://arxiv.org/abs/{arxiv_id}" if arxiv_id else ""

        papers.append({
            "title": title,
            "authors": authors,
            "year": year,
            "abstract": abstract,
            "citation_count": None,
            "arxiv_id": arxiv_id or None,
            "doi": None,
            "url": url_str or None,
            "source": "arxiv",
        })

    return papers


def search_semantic_scholar(
    query: str, max_results: int, year_min: Optional[int]
) -> List[Dict[str, Any]]:
    """Search Semantic Scholar API and return normalized paper dicts."""
    params = urllib.parse.urlencode({
        "query": query,
        "limit": min(max_results, 100),  # API cap
        "fields": "title,authors,year,abstract,citationCount,externalIds,url",
    })
    url = f"{SEMANTIC_SCHOLAR_API}?{params}"

    try:
        data = _make_request(url)
    except (urllib.error.URLError, OSError) as exc:
        print(f"[WARN] Semantic Scholar API request failed: {exc}", file=sys.stderr)
        return []

    try:
        body = json.loads(data)
    except json.JSONDecodeError as exc:
        print(f"[WARN] Semantic Scholar JSON parse error: {exc}", file=sys.stderr)
        return []

    papers: List[Dict[str, Any]] = []
    for item in body.get("data") or []:
        year = item.get("year")
        if year_min is not None and year is not None and year < year_min:
            continue

        authors = []
        for a in item.get("authors") or []:
            name = a.get("name")
            if name:
                authors.append(name)

        ext_ids = item.get("externalIds") or {}
        arxiv_id = ext_ids.get("ArXiv") or None
        doi = ext_ids.get("DOI") or None

        papers.append({
            "title": (item.get("title") or "").strip(),
            "authors": authors,
            "year": year,
            "abstract": (item.get("abstract") or "").strip(),
            "citation_count": item.get("citationCount"),
            "arxiv_id": arxiv_id,
            "doi": doi,
            "url": item.get("url") or None,
            "source": "semantic_scholar",
        })

    return papers


def search_openalex(
    query: str, max_results: int, year_min: Optional[int]
) -> List[Dict[str, Any]]:
    """Search OpenAlex API and return normalized paper dicts."""
    params: Dict[str, Any] = {
        "search": query,
        "per_page": min(max_results, 200),  # API cap
        "sort": "cited_by_count:desc",
    }
    if year_min is not None:
        params["filter"] = f"from_publication_date:{year_min}-01-01"

    url = f"{OPENALEX_API}?{urllib.parse.urlencode(params)}"

    try:
        data = _make_request(url)
    except (urllib.error.URLError, OSError) as exc:
        print(f"[WARN] OpenAlex API request failed: {exc}", file=sys.stderr)
        return []

    try:
        body = json.loads(data)
    except json.JSONDecodeError as exc:
        print(f"[WARN] OpenAlex JSON parse error: {exc}", file=sys.stderr)
        return []

    papers: List[Dict[str, Any]] = []
    for item in body.get("results") or []:
        year = item.get("publication_year")
        if year_min is not None and year is not None and year < year_min:
            continue

        # Authors from authorships
        authors = []
        for authorship in item.get("authorships") or []:
            author_obj = authorship.get("author") or {}
            name = author_obj.get("display_name")
            if name:
                authors.append(name)

        # Reconstruct abstract from inverted index
        abstract = _reconstruct_abstract_from_inverted_index(
            item.get("abstract_inverted_index")
        )

        doi_raw = item.get("doi") or ""
        # OpenAlex doi is a full URL like "https://doi.org/10.1234/..."
        doi = doi_raw.replace("https://doi.org/", "") if doi_raw else None

        papers.append({
            "title": (item.get("title") or "").strip(),
            "authors": authors,
            "year": year,
            "abstract": abstract,
            "citation_count": item.get("cited_by_count"),
            "arxiv_id": None,
            "doi": doi,
            "url": item.get("id") or None,  # OpenAlex entity URL
            "source": "openalex",
        })

    return papers


# ---------------------------------------------------------------------------
# Deduplication
# ---------------------------------------------------------------------------


def deduplicate_papers(papers: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """Deduplicate papers by normalized title, keeping the most informative entry."""
    seen: Dict[str, Dict[str, Any]] = {}
    for paper in papers:
        key = _normalize_title(paper.get("title") or "")
        if not key:
            continue
        if key not in seen or _paper_info_score(paper) > _paper_info_score(seen[key]):
            seen[key] = paper
    return list(seen.values())


# ---------------------------------------------------------------------------
# Sub-command handlers
# ---------------------------------------------------------------------------


def cmd_search_papers(args: argparse.Namespace) -> None:
    """Handler for the search-papers sub-command."""
    query = args.query
    max_results = args.max_results
    year_min = args.year_min
    output = args.output

    print(f"Searching for papers: {query!r}  (max_results={max_results}, year_min={year_min})")

    all_papers: List[Dict[str, Any]] = []

    # --- arXiv ---
    print("  [1/3] Querying arXiv...", end=" ", flush=True)
    arxiv_papers = search_arxiv(query, max_results, year_min)
    print(f"{len(arxiv_papers)} results")
    all_papers.extend(arxiv_papers)

    # --- Semantic Scholar ---
    print("  [2/3] Querying Semantic Scholar...", end=" ", flush=True)
    ss_papers = search_semantic_scholar(query, max_results, year_min)
    print(f"{len(ss_papers)} results")
    all_papers.extend(ss_papers)

    # --- OpenAlex ---
    print("  [3/3] Querying OpenAlex...", end=" ", flush=True)
    oa_papers = search_openalex(query, max_results, year_min)
    print(f"{len(oa_papers)} results")
    all_papers.extend(oa_papers)

    # Deduplicate
    before = len(all_papers)
    results = deduplicate_papers(all_papers)
    after = len(results)
    if before != after:
        print(f"  Deduplicated: {before} -> {after} papers")

    # Write output
    output_json = json.dumps(results, indent=2, ensure_ascii=False)
    if output:
        with open(output, "w", encoding="utf-8") as f:
            f.write(output_json)
            f.write("\n")
        print(f"  Results written to {output}")
    else:
        print(output_json)

    print(f"Done. {len(results)} unique papers found.")


def cmd_search_repos(args: argparse.Namespace) -> None:
    """Handler for the search-repos sub-command.

    Searches the GitHub Search API for repositories matching the query,
    extracts key metadata, and writes JSON output.
    """
    query = args.query
    max_results = args.max_results
    github_token: Optional[str] = args.github_token
    output: Optional[str] = args.output

    # Build the search URL
    search_query = f"{query} language:python"
    params = urllib.parse.urlencode({
        "q": search_query,
        "sort": "stars",
        "order": "desc",
        "per_page": max_results,
    })
    url = f"{GITHUB_SEARCH_API}?{params}"

    headers = {
        "Accept": "application/vnd.github.v3+json",
        "User-Agent": USER_AGENT,
    }
    if github_token:
        headers["Authorization"] = f"token {github_token}"

    print(f"Searching GitHub repos: {query!r}  (max_results={max_results})")

    # Rate-limit retry: if 403, wait 10s, retry up to 2 times
    max_retries = 2
    data: Optional[bytes] = None
    for attempt in range(1 + max_retries):
        req = urllib.request.Request(url, headers=headers)
        try:
            with urllib.request.urlopen(req, timeout=REQUEST_TIMEOUT) as resp:
                data = resp.read()
            break
        except urllib.error.HTTPError as exc:
            if exc.code == 403 and attempt < max_retries:
                print(
                    f"  [WARN] GitHub 403 rate limit, retrying in 10s "
                    f"(attempt {attempt + 1}/{max_retries})...",
                    file=sys.stderr,
                )
                time.sleep(10)
                continue
            print(f"[ERROR] GitHub API request failed: {exc}", file=sys.stderr)
            sys.exit(1)
        except (urllib.error.URLError, OSError) as exc:
            print(f"[ERROR] GitHub API request failed: {exc}", file=sys.stderr)
            sys.exit(1)

    if data is None:
        print("[ERROR] Failed to fetch data from GitHub API.", file=sys.stderr)
        sys.exit(1)

    try:
        body = json.loads(data)
    except json.JSONDecodeError as exc:
        print(f"[ERROR] GitHub JSON parse error: {exc}", file=sys.stderr)
        sys.exit(1)

    items = body.get("items") or []
    print(f"  GitHub returned {len(items)} results")

    # Extract fields and build normalized repo dicts
    repos: List[Dict[str, Any]] = []
    for item in items:
        full_name = item.get("full_name", "")
        parts = full_name.split("/", 1)
        owner = parts[0] if parts else ""
        name = parts[1] if len(parts) > 1 else item.get("name", "")

        repos.append({
            "owner": owner,
            "name": name,
            "url": item.get("html_url", ""),
            "stars": item.get("stargazers_count", 0),
            "pushed_at": item.get("pushed_at", ""),
            "description": item.get("description") or "",
            "language": item.get("language") or "",
            "size_kb": item.get("size", 0),
        })

    # Sort by stars descending (API already sorts, but enforce it)
    repos.sort(key=lambda r: r["stars"], reverse=True)

    # Write output
    output_json = json.dumps(repos, indent=2, ensure_ascii=False)
    if output:
        with open(output, "w", encoding="utf-8") as f:
            f.write(output_json)
            f.write("\n")
        print(f"  Results written to {output}")
    else:
        print(output_json)

    print(f"Done. {len(repos)} repositories found.")


def cmd_run_experiment(args: argparse.Namespace) -> None:
    """Handler for the run-experiment sub-command.

    Runs an experiment command in a specified working directory, captures
    stdout/stderr, parses metrics from stdout, and writes result.json.
    """
    workdir: str = args.workdir
    cmd: str = args.cmd
    gpu: Optional[str] = args.gpu
    timeout: int = args.timeout
    output_dir: str = args.output_dir

    # 1. Create output-dir if it doesn't exist
    os.makedirs(output_dir, exist_ok=True)

    # 2. Build env: copy os.environ, add CUDA_VISIBLE_DEVICES if --gpu specified
    env = os.environ.copy()
    if gpu is not None:
        env["CUDA_VISIBLE_DEVICES"] = gpu

    # 3. Run command
    print(f"Running experiment: {cmd}")
    print(f"  workdir:    {workdir}")
    if gpu is not None:
        print(f"  GPU:        {gpu}")
    print(f"  timeout:    {timeout}s")
    print(f"  output-dir: {output_dir}")

    timed_out = False
    start_time = time.monotonic()
    try:
        proc = subprocess.run(
            cmd,
            shell=True,
            cwd=workdir,
            env=env,
            capture_output=True,
            text=True,
            timeout=timeout,
        )
        returncode = proc.returncode
        stdout = proc.stdout
        stderr = proc.stderr
    except subprocess.TimeoutExpired as exc:
        timed_out = True
        returncode = -1
        stdout = exc.stdout if exc.stdout is not None else ""
        stderr = exc.stderr if exc.stderr is not None else ""
        # TimeoutExpired may return bytes if text mode didn't finish
        if isinstance(stdout, bytes):
            stdout = stdout.decode("utf-8", errors="replace")
        if isinstance(stderr, bytes):
            stderr = stderr.decode("utf-8", errors="replace")

    elapsed_sec = round(time.monotonic() - start_time, 2)

    # 5. Parse metrics from stdout: lines matching "pattern: value"
    metric_pattern = re.compile(
        r"^(\w[\w.]*)\s*:\s*([+-]?\d+\.?\d*(?:[eE][+-]?\d+)?)\s*$"
    )
    metrics: Dict[str, float] = {}
    for line in stdout.splitlines():
        m = metric_pattern.match(line.strip())
        if m:
            metrics[m.group(1)] = float(m.group(2))

    # 6. Write result.json
    result = {
        "command": cmd,
        "workdir": workdir,
        "gpu": gpu,
        "returncode": returncode,
        "elapsed_sec": elapsed_sec,
        "timed_out": timed_out,
        "stdout": stdout,
        "stderr": stderr,
        "metrics": metrics,
        "timestamp": datetime.datetime.now().isoformat(timespec="seconds"),
    }

    result_path = os.path.join(output_dir, "result.json")
    with open(result_path, "w", encoding="utf-8") as f:
        json.dump(result, f, indent=2, ensure_ascii=False)
        f.write("\n")

    # 7. Print summary
    print(f"\n--- Experiment Summary ---")
    print(f"  returncode: {returncode}")
    print(f"  elapsed:    {elapsed_sec}s")
    if timed_out:
        print(f"  TIMED OUT after {timeout}s")
    if metrics:
        print(f"  metrics:    {len(metrics)} found")
        for k, v in metrics.items():
            print(f"    {k}: {v}")
    else:
        print(f"  metrics:    (none found)")
    print(f"  result:     {result_path}")


def _title_similarity(a: str, b: str) -> float:
    """Compute word-overlap similarity between two titles (0.0 to 1.0)."""
    words_a = set(a.lower().split())
    words_b = set(b.lower().split())
    if not words_a or not words_b:
        return 0.0
    return len(words_a & words_b) / max(len(words_a), len(words_b))


def _parse_bib_file(bib_path: str) -> List[Dict[str, str]]:
    """Parse a .bib file and extract cite_key and title from each entry."""
    with open(bib_path, "r", encoding="utf-8") as f:
        content = f.read()

    entries: List[Dict[str, str]] = []
    # Match entry headers like @article{key, or @inproceedings{key,
    entry_pattern = re.compile(r"@\w+\{([^,]+),", re.IGNORECASE)
    title_pattern = re.compile(r"title\s*=\s*[{\"](.+?)[}\"]", re.IGNORECASE)

    # Split on entry boundaries
    entry_starts = list(entry_pattern.finditer(content))
    for i, match in enumerate(entry_starts):
        cite_key = match.group(1).strip()
        # Get the text block for this entry (up to the next entry or end)
        start = match.start()
        end = entry_starts[i + 1].start() if i + 1 < len(entry_starts) else len(content)
        block = content[start:end]

        title_match = title_pattern.search(block)
        title = title_match.group(1).strip() if title_match else ""

        if title:
            entries.append({"cite_key": cite_key, "title": title})
        else:
            # Include entries even without a title so they show in the report
            entries.append({"cite_key": cite_key, "title": ""})

    return entries


def _verify_via_semantic_scholar(title: str) -> Optional[Dict[str, str]]:
    """Try to verify a title via Semantic Scholar. Returns match info or None."""
    params = urllib.parse.urlencode({
        "query": title,
        "limit": 3,
        "fields": "title,year",
    })
    url = f"{SEMANTIC_SCHOLAR_API}?{params}"

    try:
        data = _make_request(url)
    except (urllib.error.URLError, OSError) as exc:
        print(f"  [WARN] Semantic Scholar request failed: {exc}", file=sys.stderr)
        return None

    try:
        body = json.loads(data)
    except json.JSONDecodeError:
        return None

    for item in body.get("data") or []:
        candidate_title = (item.get("title") or "").strip()
        if candidate_title and _title_similarity(title, candidate_title) > 0.8:
            return {
                "matched_source": "semantic_scholar",
                "matched_title": candidate_title,
            }

    return None


def _verify_via_arxiv(title: str) -> Optional[Dict[str, str]]:
    """Try to verify a title via arXiv search. Returns match info or None."""
    params = urllib.parse.urlencode({
        "search_query": f"ti:{title}",
        "max_results": 3,
    })
    url = f"{ARXIV_API}?{params}"

    try:
        data = _make_request(url)
    except (urllib.error.URLError, OSError) as exc:
        print(f"  [WARN] arXiv request failed: {exc}", file=sys.stderr)
        return None

    try:
        root = ET.fromstring(data)
    except ET.ParseError:
        return None

    ns = {"atom": "http://www.w3.org/2005/Atom"}
    for entry in root.findall("atom:entry", ns):
        title_el = entry.find("atom:title", ns)
        if title_el is not None and title_el.text:
            candidate_title = title_el.text.strip().replace("\n", " ")
            if _title_similarity(title, candidate_title) > 0.8:
                return {
                    "matched_source": "arxiv",
                    "matched_title": candidate_title,
                }

    return None


def cmd_verify_citations(args: argparse.Namespace) -> None:
    """Handler for the verify-citations sub-command.

    Parses a .bib file, verifies each entry against Semantic Scholar and arXiv,
    and outputs a JSON report.
    """
    bib_path: str = args.bib
    output: Optional[str] = args.output

    if not os.path.isfile(bib_path):
        print(f"[ERROR] .bib file not found: {bib_path}", file=sys.stderr)
        sys.exit(1)

    entries = _parse_bib_file(bib_path)
    print(f"Parsed {len(entries)} entries from {bib_path}")

    results: List[Dict[str, Any]] = []

    for i, entry in enumerate(entries):
        cite_key = entry["cite_key"]
        title = entry["title"]

        print(f"  [{i + 1}/{len(entries)}] Verifying: {cite_key}", end="", flush=True)

        if not title:
            print(" ... no title, skipping")
            results.append({
                "cite_key": cite_key,
                "title": title,
                "status": "not_found",
                "matched_source": None,
                "matched_title": None,
            })
            continue

        # Try Semantic Scholar first
        match = _verify_via_semantic_scholar(title)
        if match is None:
            # Rate limit between API calls
            time.sleep(1)
            # Try arXiv
            match = _verify_via_arxiv(title)

        if match is not None:
            print(f" ... verified ({match['matched_source']})")
            results.append({
                "cite_key": cite_key,
                "title": title,
                "status": "verified",
                "matched_source": match["matched_source"],
                "matched_title": match["matched_title"],
            })
        else:
            print(" ... not found")
            results.append({
                "cite_key": cite_key,
                "title": title,
                "status": "not_found",
                "matched_source": None,
                "matched_title": None,
            })

        # Rate limit between entries
        if i < len(entries) - 1:
            time.sleep(1)

    # Summary
    verified_count = sum(1 for r in results if r["status"] == "verified")
    print(f"\nDone. {verified_count}/{len(results)} citations verified.")

    # Write output
    output_json = json.dumps(results, indent=2, ensure_ascii=False)
    if output:
        with open(output, "w", encoding="utf-8") as f:
            f.write(output_json)
            f.write("\n")
        print(f"Report written to {output}")
    else:
        print(output_json)


# ---------------------------------------------------------------------------
# Argument parser
# ---------------------------------------------------------------------------


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="research_tools.py",
        description="CLI toolkit for academic research tasks (stdlib-only).",
    )
    subparsers = parser.add_subparsers(dest="command", help="Available sub-commands")

    # --- search-papers ---
    sp = subparsers.add_parser(
        "search-papers",
        help="Search arXiv, Semantic Scholar, and OpenAlex for papers",
    )
    sp.add_argument(
        "--query", "-q", required=True, help="Search query string"
    )
    sp.add_argument(
        "--max-results", "-n", type=int, default=20,
        help="Maximum results per API (default: 20)",
    )
    sp.add_argument(
        "--year-min", type=int, default=None,
        help="Filter out papers published before this year",
    )
    sp.add_argument(
        "--output", "-o", default=None,
        help="Output JSON file path (default: print to stdout)",
    )
    sp.set_defaults(func=cmd_search_papers)

    # --- search-repos ---
    sr = subparsers.add_parser(
        "search-repos",
        help="Search GitHub for relevant repositories",
    )
    sr.add_argument(
        "--query", "-q", required=True, help="Search query string"
    )
    sr.add_argument(
        "--max-results", "-n", type=int, default=10,
        help="Maximum number of results (default: 10)",
    )
    sr.add_argument(
        "--github-token", default=None,
        help="GitHub personal access token (optional, for higher rate limits)",
    )
    sr.add_argument(
        "--output", "-o", default=None,
        help="Output JSON file path (default: print to stdout)",
    )
    sr.set_defaults(func=cmd_search_repos)

    # --- run-experiment ---
    re_ = subparsers.add_parser(
        "run-experiment",
        help="Run an experiment command and capture results",
    )
    re_.add_argument(
        "--workdir", required=True,
        help="Working directory to run the command in",
    )
    re_.add_argument(
        "--cmd", required=True,
        help="Command to execute (e.g. 'python src/run.py --task ft_cls')",
    )
    re_.add_argument(
        "--gpu", default=None,
        help="GPU device IDs (e.g. '1,4') — sets CUDA_VISIBLE_DEVICES",
    )
    re_.add_argument(
        "--timeout", type=int, default=3600,
        help="Max seconds before killing the process (default: 3600)",
    )
    re_.add_argument(
        "--output-dir", required=True,
        help="Directory to save result.json",
    )
    re_.set_defaults(func=cmd_run_experiment)

    # --- verify-citations ---
    vc = subparsers.add_parser(
        "verify-citations",
        help="Verify citation validity against Semantic Scholar and arXiv",
    )
    vc.add_argument(
        "--bib", required=True,
        help="Path to a .bib file to verify",
    )
    vc.add_argument(
        "--output", "-o", default=None,
        help="Output JSON file path (default: print to stdout)",
    )
    vc.set_defaults(func=cmd_verify_citations)

    return parser


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------


def main() -> None:
    parser = build_parser()
    args = parser.parse_args()

    if args.command is None:
        parser.print_help()
        sys.exit(1)

    args.func(args)


if __name__ == "__main__":
    main()
