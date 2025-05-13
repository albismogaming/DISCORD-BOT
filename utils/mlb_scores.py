import requests

def get_mlb_scores():
    url = "https://site.api.espn.com/apis/site/v2/sports/baseball/mlb/scoreboard"
    response = requests.get(url)
    data = response.json()

    scores = []
    for event in data["events"]:
        competition = event["competitions"][0]
        status = competition["status"]["type"]["description"]

        teams = competition["competitors"]
        home = next(t for t in teams if t["homeAway"] == "home")
        away = next(t for t in teams if t["homeAway"] == "away")

        home_team = home["team"]["abbreviation"]
        away_team = away["team"]["abbreviation"]
        home_score = home["score"]
        away_score = away["score"]

        # Get situation (outs, inning)
        situation = competition.get("situation", {})
        outs = situation.get("outs")
        inning = competition.get("status", {}).get("type", {}).get("shortDetail")

        line = f"⚾ {away_team:3} {away_score:2} - {home_score:2} {home_team:3} "
        if status == "In Progress":
            line += f"| {inning.upper():7} "
            if outs is not None:
                line += f"| OUTS: {outs}"
        else:
            line += f"| {status}"

        scores.append(line)

    return scores