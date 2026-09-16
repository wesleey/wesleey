"""GitHub-style repo card SVG generator (light + dark themes).

Reads repository URLs from repositories.txt (one per line), fetches each
repo's data from the GitHub API, and generates a light + dark SVG card
for each one.
"""

import json
import os
import re
import urllib.error
import urllib.request

LANGUAGE_COLORS = {
    "Python": "#3572a5",
    "TypeScript": "#3178c6",
    "JavaScript": "#f1e05a",
    "C#": "#7355dd",
    "Java": "#b07219",
    "Go": "#00add8",
    "Rust": "#dea584",
    "Ruby": "#701516",
    "PHP": "#4f5d95",
    "C++": "#f34b7d",
    "C": "#555555",
    "Kotlin": "#a97bff",
    "Swift": "#f05138",
    "HTML": "#e34c26",
    "CSS": "#563d7c",
    "Shell": "#89e051",
    "Dart": "#00b4ab",
    "Vue": "#41b883",
}
DEFAULT_LANGUAGE_COLOR = "#8b949e"

DESCRIPTION_WIDTH_BUDGET = 445  # approximate pixel width per line
DESCRIPTION_MAX_LINES = 2

# Rough per-character pixel-width weights (Segoe UI, 15px), used to word-wrap
# descriptions the same way GitHub's own card renderer does: by approximate
# rendered width rather than a fixed character count.
_NARROW_LOWER = set("ijltf")
_WIDE_UPPER = set("MW")
_PUNCTUATION = set(",.;:!'\"-")


def _char_width(c):
    if c == " " or c in _PUNCTUATION:
        return 4
    if c.isdigit():
        return 7
    if c.isupper():
        return 11 if c in _WIDE_UPPER else 9
    if c.islower():
        return 4 if c in _NARROW_LOWER else 7
    return 7


def _text_width(s):
    return sum(_char_width(c) for c in s)

THEMES = {
    "light": {"header": "#0969da", "text": "#59636e", "stroke": "#d1d9e0"},
    "dark": {"header": "#4493f8", "text": "#9198a1", "stroke": "#3d444d"},
}

STAR_PATH = ("M8 .25a.75.75 0 01.673.418l1.882 3.815 4.21.612a.75.75 0 01.416 1.279l-3.046 2.97.719 4.192a.75.75 "
             "0 01-1.088.791L8 12.347l-3.766 1.98a.75.75 0 01-1.088-.79l.72-4.194L.818 6.374a.75.75 0 01.416-1.28l"
             "4.21-.611L7.327.668A.75.75 0 018 .25zm0 2.445L6.615 5.5a.75.75 0 01-.564.41l-3.097.45 2.24 2.184a.75."
             "75 0 01.216.664l-.528 3.084 2.769-1.456a.75.75 0 01.698 0l2.77 1.456-.53-3.084a.75.75 0 01.216-.664l"
             "2.24-2.183-3.096-.45a.75.75 0 01-.564-.41L8 2.694v.001z")
FORK_PATH = ("M5 3.25a.75.75 0 11-1.5 0 .75.75 0 011.5 0zm0 2.122a2.25 2.25 0 10-1.5 0v.878A2.25 2.25 0 005.75 8.5"
             "h1.5v2.128a2.251 2.251 0 101.5 0V8.5h1.5a2.25 2.25 0 002.25-2.25v-.878a2.25 2.25 0 10-1.5 0v.878a.75"
             ".75 0 01-.75.75h-4.5A.75.75 0 015 6.25v-.878zm3.75 7.378a.75.75 0 11-1.5 0 .75.75 0 011.5 0zm3-8.75a."
             "75.75 0 100-1.5.75.75 0 000 1.5z")
BOOK_PATH = ("M2 2.5A2.5 2.5 0 014.5 0h8.75a.75.75 0 01.75.75v12.5a.75.75 0 01-.75.75h-2.5a.75.75 0 110-1.5h1.75v-"
             "2h-8a1 1 0 00-.714 1.7.75.75 0 01-1.072 1.05A2.495 2.495 0 012 11.5v-9zm10.5-1V9h-8c-.356 0-.694.074"
             "-1 .208V2.5a1 1 0 011-1h8zM5 12.25v3.25a.25.25 0 00.4.2l1.45-1.087a.25.25 0 01.3 0L8.6 15.7a.25.25 0 "
             "00.4-.2v-3.25a.25.25 0 00-.25-.25h-3.5a.25.25 0 00-.25.25z")


def num(x):
    """Format a number, dropping a trailing '.0' for whole values."""
    x = round(x, 2)
    return str(int(x)) if x == int(x) else str(x)


def num1(x):
    """Format a number with exactly one decimal place, never dropped."""
    return str(round(x, 1))


def wrap_description(text, budget=DESCRIPTION_WIDTH_BUDGET, max_lines=DESCRIPTION_MAX_LINES):
    """Word-wrap a description to fit the card's rendered width, truncating
    the last allowed line with '...' if it still doesn't fit."""
    if not text:
        return [""]

    words = text.split()
    lines = []
    current = ""

    for i, word in enumerate(words):
        candidate = f"{current} {word}" if current else word
        if _text_width(candidate) <= budget:
            current = candidate
            continue

        lines.append(current)
        if len(lines) == max_lines - 1:
            remaining = " ".join(words[i:])
            if _text_width(remaining) > budget:
                truncated = remaining
                while truncated and _text_width(truncated + "...") > budget:
                    truncated = truncated[:-1]
                remaining = truncated.rstrip() + "..."
            lines.append(remaining)
            return lines
        current = word

    if current:
        lines.append(current)
    return lines or [""]


def fork_block(x1, x2, forks):
    """Forks icon + count, commented out when there are no forks."""
    active = (f'  <path class="icon" transform="translate({num1(x1)}, 106) scale(1.2)" '
              f'fill-rule="evenodd" d="{FORK_PATH}" />\n'
              f'  <text class="gray" x="{num1(x2)}" y="120">{forks}</text>')
    if int(forks) > 0:
        return active
    inner = (f'<path class="icon" transform="translate({num1(x1)}, 106) scale(1.2)" '
             f'fill-rule="evenodd" d="{FORK_PATH}" />\n'
             f'  <text class="gray" x="{num1(x2)}" y="120">{forks}</text>')
    return f"  <!-- {inner} -->"


def build_card(theme, repo, description, stars, forks, language):
    colors = THEMES[theme]
    lang_name = language or "Unknown"
    lang_color = LANGUAGE_COLORS.get(lang_name, DEFAULT_LANGUAGE_COLOR)
    lines = wrap_description(description)
    tspans = "\n".join(f'    <tspan x="0" dy="1.2em">{line}</tspan>' for line in lines)

    badge_x = 26 + len(repo) * 7.84 + 18
    badge_label_x = badge_x + 29
    lang_end = 20 + len(lang_name) * 7.4
    star_icon_x = lang_end + 18
    star_label_x = star_icon_x + 24
    fork_icon_x = star_label_x + len(stars) * 7.4 + 18
    fork_label_x = fork_icon_x + 24

    return f"""<svg xmlns="http://www.w3.org/2000/svg" width="445" height="130" viewBox="0 0 445 130">
  <style>
    .header {{ font: 600 17px 'Segoe UI', sans-serif; fill: {colors['header']}; }}
    .badge {{ font: 400 15px 'Segoe UI', sans-serif; fill: {colors['text']}; }}
    .description {{ font: 400 15px 'Segoe UI', sans-serif; fill: {colors['text']}; }}
    .gray {{ font: 400 15px 'Segoe UI', sans-serif; fill: {colors['text']}; }}
    .icon {{ fill: {colors['text']}; }}
    .language {{ fill: {lang_color}; }}
  </style>

  <rect x="0.5" y="0.5" rx="4.5" height="99%" width="99%" fill="transparent" />

  <!-- Book -->
  <path class="icon" transform="translate(0, 20) scale(1.25)" fill-rule="evenodd" d="{BOOK_PATH}" />

  <!-- Header -->
  <text x="26" y="35" class="header">{repo}</text>

  <!-- Badge -->
  <rect x="{num(badge_x)}" y="17" width="58" height="23.5" rx="10" fill="none" stroke="{colors['stroke']}" stroke-width="1" />
  <text x="{num(badge_label_x)}" y="34" text-anchor="middle" class="badge">Public</text>

  <!-- Description -->
  <text class="description" x="0" y="50">
{tspans}
  </text>

  <!-- Language -->
  <circle cx="8" cy="114" r="8" class="language" />
  <text class="gray" x="20" y="120">{lang_name}</text>

  <!-- Stars -->
  <path class="icon" transform="translate({num1(star_icon_x)}, 106) scale(1.2)" fill-rule="evenodd" d="{STAR_PATH}" />
  <text class="gray" x="{num(star_label_x)}" y="120">{stars}</text>

  <!-- Forks -->
{fork_block(fork_icon_x, fork_label_x, forks)}
</svg>
"""


GITHUB_URL_RE = re.compile(r"github\.com/([^/\s]+)/([^/\s]+?)/?$")


def read_repo_urls(path):
    with open(path, encoding="utf-8") as f:
        return [line.strip() for line in f if line.strip()]


def parse_owner_repo(url):
    match = GITHUB_URL_RE.search(url)
    if not match:
        raise ValueError(f"Not a valid GitHub repo URL: {url}")
    owner, repo = match.groups()
    return owner, repo.removesuffix(".git")


def fetch_repo(owner, repo):
    """Fetch repo data from the GitHub API. Set GITHUB_TOKEN to raise rate limits."""
    url = f"https://api.github.com/repos/{owner}/{repo}"
    headers = {"User-Agent": "repo-card-generator", "Accept": "application/vnd.github+json"}
    token = os.environ.get("GITHUB_TOKEN")
    if token:
        headers["Authorization"] = f"Bearer {token}"

    request = urllib.request.Request(url, headers=headers)
    with urllib.request.urlopen(request) as response:
        data = json.load(response)

    return {
        "name": data["name"],
        "description": data.get("description") or "",
        "stars": str(data.get("stargazers_count", 0)),
        "forks": str(data.get("forks_count", 0)),
        "language": data.get("language"),
    }


def main(repositories_file="repositories.txt", output_dir="repositories"):
    os.makedirs(output_dir, exist_ok=True)
    urls = read_repo_urls(repositories_file)

    for url in urls:
        try:
            owner, repo = parse_owner_repo(url)
            info = fetch_repo(owner, repo)
        except ValueError as e:
            print(f"Skipping '{url}': {e}")
            continue
        except urllib.error.HTTPError as e:
            if e.code == 404:
                print(f"Skipping '{url}': repository not found.")
            elif e.code == 403:
                print(f"Skipping '{url}': GitHub API rate limit exceeded "
                      f"(set the GITHUB_TOKEN env var to raise the limit).")
            else:
                print(f"Skipping '{url}': GitHub API error {e.code}.")
            continue

        for theme in THEMES:
            svg = build_card(theme, info["name"], info["description"],
                              info["stars"], info["forks"], info["language"])
            filename = os.path.join(output_dir, f"{info['name']}-{theme}.svg")
            with open(filename, "w", encoding="utf-8") as f:
                f.write(svg)
            print(f"Saved: {filename}")


if __name__ == "__main__":
    main()
