# cogs/sports_scores.py
import aiohttp
import json
from datetime import datetime
from zoneinfo import ZoneInfo
from discord import app_commands, Interaction, ui, ButtonStyle
from discord.ext import commands
from typing import Optional, List, Any, Dict

# Constants / mapping
SPORTS = {
    "MLB": {"sport": "baseball", "league": "mlb"},
    "NFL": {"sport": "football", "league": "nfl"},
    "NBA": {"sport": "basketball", "league": "nba"},
    "NHL": {"sport": "hockey", "league": "nhl"},
    "NCAAF": {"sport": "football", "league": "college-football"},
}
STATUS_TEMPLATES = {
    "MLB": lambda d: f"{d.get('inning_state','')}".strip() + f" · {d.get('outs',0)} out{'s' if d.get('outs',0)!=1 else ''}",
    "NFL": lambda d: f"{ordinal(d.get('quarter',0))} QTR · {d.get('clock','')} · {d.get('down_distance','')}".strip(" · "),
    "NCAAF": lambda d: f"{ordinal(d.get('quarter',0))} QTR · {d.get('clock','')} · {d.get('down_distance','')}".strip(" · "),
    "NBA": lambda d: f"{ordinal(d.get('quarter',''))} QTR · {d.get('clock','')}".strip(" · "),
    "NHL": lambda d: f"{ordinal(d.get('period',''))} PER · {d.get('clock','')} · {'PP' if d.get('power_play') else ''}".strip(" · ")
}

# Load team emoji map (optional file, keep fallback behavior)
try:
    with open("all_teams.json", encoding="utf-8") as f:
        TEAM_EMOJIS = json.load(f)
except Exception:
    TEAM_EMOJIS = {}

AUTO_FETCH_TIMEOUT = 10  # seconds
QUEUE_HISTORY_LIMIT = 200

# ---------- helpers ----------
def ordinal(n: int) -> str:
    return "%d%s" % (n, "TSNRHTDD"[(n//10%10!=1)*(n%10<4)*n%10::4])

def emoji_for(sport: str, abbr: str, bot: commands.Bot):
    """
    Return a discord.Emoji object for a team in a specific sport.
    If no emoji is found, return a fallback string like 'NFL_PHI'.
    """
    if not abbr:
        return abbr.upper()

    key = f"{sport.upper()}_{abbr.upper()}"  # e.g., 'NFL_PHI' or 'NBA_PHI'
    eid = TEAM_EMOJIS.get(key)

    if eid:
        try:
            return bot.get_emoji(int(eid)) or key
        except Exception:
            return key
    return key

def get_scoreboard_url(user_input: str) -> str:
    key = user_input.upper()
    if key not in SPORTS:
        raise ValueError(f"Unknown sport/league: {user_input}")
    data = SPORTS[key]
    return f"https://site.api.espn.com/apis/site/v2/sports/{data['sport']}/{data['league']}/scoreboard"

def _iso_to_short(iso_str: Optional[str]) -> str:
    if not iso_str:
        return "TBD"
    try:
        dt_utc = datetime.fromisoformat(iso_str.replace("Z", "+00:00"))
        dt_cst = dt_utc.astimezone(ZoneInfo("America/Chicago"))

        return dt_cst.strftime("%b %d, %I:%M %p")
    except Exception:
        return iso_str

def extract_record(team):
    records = team.get("records", [])
    # take first record summary if available
    if records and isinstance(records, list):
        return records[0].get("summary", "")
    return ""

def format_game_status(sport: str, game: Dict[str, Any]) -> str:
    """
    Return a human-friendly status string depending on sport and game content.
    """
    if game["status_type"] == "in_progress":
        template = STATUS_TEMPLATES.get(sport.upper())
        return template(game.get("detail", {})) if template else game.get("raw_status") or "In Progress"
    if game["status_type"] == "final":
        return "Final"
    # Scheduled / pregame
    return _iso_to_short(game.get("start_time"))

def detect_status_type(raw_status: str, status_name: str) -> str:
    raw_lower = (raw_status or "").lower()
    status_name = (status_name or "").lower()
    if any(x in raw_lower for x in ("in progress", "live", "underway")) or "in progress" in status_name:
        return "in_progress"
    if "final" in raw_lower or "final" in status_name:
        return "final"
    if "scheduled" in raw_lower or status_name in ("scheduled", "pre", "preview"):
        return "scheduled"
    return "other"

# ---------- async fetcher (uses aiohttp) ----------
async def get_sport_scores(url: str, sport: str) -> List[Dict[str, Any]]:
    """
    Async fetch scoreboard JSON (from ESPN) and return a list of game dicts.
    Each dict contains:
      - away_abbr, away_score, away_record
      - home_abbr, home_score, home_record
      - raw_status, status_type
      - period, clock, start_time
      - detail (sport-specific fields)
      - _comp, _status_obj for full data inspection
    """
    games: List[Dict[str, Any]] = []
    timeout = aiohttp.ClientTimeout(total=AUTO_FETCH_TIMEOUT)

    async with aiohttp.ClientSession(timeout=timeout) as session:
        async with session.get(url) as resp:
            resp.raise_for_status()
            data = await resp.json()

    for event in data.get("events", []):
        comp = event.get("competitions", [None])[0]
        if not comp:
            continue

        status_obj = comp.get("status") or {}
        raw_status = (
            status_obj.get("type", {}).get("description") or
            status_obj.get("type", {}).get("name") or
            status_obj.get("detail") or ""
        )
        status_name = status_obj.get("type", {}).get("name", "")
        status_type = detect_status_type(raw_status, status_name)

        teams = comp.get("competitors", [])
        try:
            home = next(t for t in teams if t.get("homeAway") == "home")
            away = next(t for t in teams if t.get("homeAway") == "away")
        except StopIteration:
            continue

        # Common fields
        home_team = home.get("team", {}) or {}
        away_team = away.get("team", {}) or {}
        period = status_obj.get("period")
        clock = status_obj.get("displayClock") or status_obj.get("clock") or ""

        # Sport-specific detail extraction
        detail: Dict[str, Any] = {}
        s = sport.upper()
        if s == "MLB":
            situation = comp.get("situation", {}) or {}
            detail.update({
                "inning_state": situation.get("inningState") or status_obj.get("inningState")
                                or status_obj.get("type", {}).get("shortDetail"),
                "outs": situation.get("outs") or status_obj.get("outs") or 0
            })
        elif s in ("NFL", "NCAAF", "CFL"):
            down_distance = comp.get("situation", {}).get("downDistanceText") or status_obj.get("shortDetail")
            detail.update({
                "quarter": period,
                "clock": clock,
                "down_distance": down_distance
            })
        elif s in ("NBA", "NCAAMB", "NCAAWB"):
            detail.update({
                "quarter": period,
                "clock": clock
            })
        elif s == "NHL":
            detail.update({
                "period": period,
                "clock": clock,
                "power_play": comp.get("situation", {}).get("powerPlay")
            })
        else:
            detail.update({
                "period": period,
                "clock": clock
            })

        # Append game dict
        games.append({
            "away_abbr": away_team.get("abbreviation") or away_team.get("shortName") or "",
            "away_score": away.get("score") or "0",
            "away_record": extract_record(away),
            "home_abbr": home_team.get("abbreviation") or home_team.get("shortName") or "",
            "home_score": home.get("score") or "0",
            "home_record": extract_record(home),
            "raw_status": raw_status,
            "status_type": status_type,
            "period": period,
            "clock": clock,
            "start_time": event.get("date"),
            "detail": detail,
            "_comp": comp,
            "_status_obj": status_obj
        })

    return games

# ---------- Cog ----------
class SportsBook(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot

    @app_commands.command(
        name="scoreboard",
        description="Fetches the latest scoreboard for a given professional league"
    )
    @app_commands.describe(
        league="Select the professional league (MLB, NFL, NBA, NHL, NCAAF)",
        teams="Optional: comma-separated team abbreviations to filter (e.g. 'LAC,MIA'). Omit to show all games."
    )
    @app_commands.choices(league=[
        app_commands.Choice(name="MLB", value="MLB"),
        app_commands.Choice(name="NFL", value="NFL"),
        app_commands.Choice(name="NBA", value="NBA"),
        app_commands.Choice(name="NHL", value="NHL"),
        app_commands.Choice(name="NCAAF", value="NCAAF"),
    ])
    
    async def scoreboard(self, interaction: Interaction, league: app_commands.Choice[str], teams: Optional[str] = None):
        await interaction.response.defer()

        try:
            url = get_scoreboard_url(league.value)
            games = await get_sport_scores(url, league.value)
        except ValueError as e:
            return await interaction.followup.send(str(e), ephemeral=True)
        except Exception as e:
            return await interaction.followup.send(f"Failed to fetch scoreboard: {e}", ephemeral=True)

        if not games:
            return await interaction.followup.send(f"No games currently found for {league.value}", ephemeral=True)

        # Parse optional teams filter (comma or space separated)
        team_filter: Optional[set] = None
        if teams:
            # allow comma or space separated input and normalize to uppercase
            tokens = [t.strip().upper() for part in teams.split(",") for t in part.split() if t.strip()]
            if tokens:
                team_filter = set(tokens)

        # If a filter was provided, keep only games that involve any of the requested teams
        filtered_games = games
        if team_filter:
            filtered_games = []
            for g in games:
                away = (g.get("away_abbr") or "").upper()
                home = (g.get("home_abbr") or "").upper()
                if away in team_filter or home in team_filter:
                    filtered_games.append(g)

            if not filtered_games:
                return await interaction.followup.send(
                    f"No games found for the requested teams: {', '.join(sorted(team_filter))}",
                    ephemeral=True
                )

        lines: List[str] = []
        for g in filtered_games:
            away_emoji = emoji_for(league.value, g["away_abbr"], self.bot)
            home_emoji = emoji_for(league.value, g["home_abbr"], self.bot)

            # Format status according to requested rules
            status_str = format_game_status(league.value, g)

            # Render emoji (discord.Emoji) or fallback string
            away_disp = f"{away_emoji}" if hasattr(away_emoji, "id") or isinstance(away_emoji, str) else str(away_emoji)
            home_disp = f"{home_emoji}" if hasattr(home_emoji, "id") or isinstance(home_emoji, str) else str(home_emoji)

            line = (
                f"{away_disp} vs {home_disp}\n"
                f"{status_str}\n"
                f"```"
                f"{g['away_abbr']:4} {g['away_record']:7} | {g['away_score']:2}\n"
                f"{g['home_abbr']:4} {g['home_record']:7} | {g['home_score']:2}"
                f"```"
            )

            lines.append(line)

        message_text = "\n".join(lines)
        # send message (non-ephemeral so users can see), optionally make ephemeral=True if you prefer
        await interaction.followup.send(f"**{league.value} Scoreboard:**\n\n{message_text}")

# setup
async def setup(bot: commands.Bot):
    await bot.add_cog(SportsBook(bot))
