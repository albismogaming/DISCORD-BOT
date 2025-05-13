import discord
from discord.ext import commands
import random

# Store ongoing games per user
active_games = {}

def deal_card():
    return random.choice(["A", "2", "3", "4", "5", "6", "7", "8", "9", "10", "J", "Q", "K"])

def hand_value(hand):
    total = 0
    aces = hand.count("A")
    for card in hand:
        if card in ["J", "Q", "K"]:
            total += 10
        elif card == "A":
            total += 11
        else:
            total += int(card)
    while total > 21 and aces:
        total -= 10
        aces -= 1
    return total

class Blackjack(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    @commands.command()
    async def blackjack(self, ctx):
        if ctx.author.id in active_games:
            await ctx.send("You're already in a game! Use `!hit` or `!stand`.")
            return

        player_hand = [deal_card(), deal_card()]
        dealer_hand = [deal_card(), deal_card()]

        active_games[ctx.author.id] = {
            "player": player_hand,
            "dealer": dealer_hand,
            "channel": ctx.channel.id
        }

        await ctx.send(f"🃏 YOUR HAND: {', '.join(player_hand)} (Total: {hand_value(player_hand)})\n"
                       f"DEALER SHOWS: {dealer_hand[0]}")

    @commands.command()
    async def hit(self, ctx):
        game = active_games.get(ctx.author.id)
        if not game:
            await ctx.send("You're not in a game. Start one with `!blackjack`.")
            return

        player_hand = game["player"]
        player_hand.append(deal_card())
        value = hand_value(player_hand)

        if value > 21:
            await ctx.send(f"💥 YOU BUSTED! YOUR HAND: {', '.join(player_hand)} (TOTAL: {value})")
            del active_games[ctx.author.id]
        else:
            await ctx.send(f"🃏 YOUR HAND: {', '.join(player_hand)} (TOTAL: {value})")

    @commands.command()
    async def stand(self, ctx):
        game = active_games.get(ctx.author.id)
        if not game:
            await ctx.send("You're not in a game. Start one with `!blackjack`.")
            return

        dealer_hand = game["dealer"]
        player_hand = game["player"]

        while hand_value(dealer_hand) < 17:
            dealer_hand.append(deal_card())

        player_score = hand_value(player_hand)
        dealer_score = hand_value(dealer_hand)

        result = ""
        if dealer_score > 21 or player_score > dealer_score:
            result = "🎉 YOU WIN!"
        elif dealer_score > player_score:
            result = "😞 DEALER WINS!."
        else:
            result = "🤝 ITS A TIE!"

        await ctx.send(f"🃏 FINAL HANDS:\n"
                       f"PLAYER: {', '.join(player_hand)} (TOTAL: {player_score})\n"
                       f"DEALER: {', '.join(dealer_hand)} (TOTAL: {dealer_score})\n"
                       f"{result}")

        del active_games[ctx.author.id]

async def setup(bot):
    await bot.add_cog(Blackjack(bot))
